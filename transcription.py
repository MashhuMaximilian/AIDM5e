import discord
import os
import asyncio
import logging
import json
import subprocess
from datetime import datetime
from config import (
    AUDIO_BITRATE,
    AUDIO_CHANNELS,
    AUDIO_CHUNK_SECONDS,
    AUDIO_FILES_PATH,
    AUDIO_PROMPT,
    AUDIO_SAMPLE_RATE,
    AUDIO_SUMMARY_WINDOW_CHUNKS,
    FFMPEG_INPUT_DEVICE,
    FFMPEG_INPUT_FORMAT,
    KEEP_AUDIO_FILES,
    KEEP_TRANSCRIPT_FILES,
    TRANSCRIPT_MANIFEST_PATH,
    TRANSCRIPT_PATH,
)
from assistant_interactions import get_assistant_response
from config import GEMINI_SUMMARY_MODEL
from memory_management import get_assigned_memory
from pathlib import Path
from prompts.transcription_prompts import (
    build_audio_narrative_summary_prompt,
    build_audio_objective_summary_prompt,
    build_audio_summary_chunk_prompt,
    build_transcript_capture_prompt,
)
from shared_functions import send_response_in_chunks
from gemini_client import gemini_client

# CHANGE Recording duration TO | 550 | FOR REAL DEAL
recording_duration = AUDIO_CHUNK_SECONDS
# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Create the folder to save audio files if it doesn't exist
audio_files_path = Path(AUDIO_FILES_PATH)
audio_files_path.mkdir(exist_ok=True)

def get_category_id_voice(voice_channel):
    """Retrieve the category ID of the given voice channel."""
    if voice_channel and voice_channel.category:
        return voice_channel.category.id
    return None

class VoiceRecorder:
    def __init__(self):
        self.voice_client = None
        self.transcription_tasks = []  # Keep track of ongoing transcription tasks
        self.transcript_path = Path(TRANSCRIPT_PATH)
        self.transcript_manifest_path = Path(TRANSCRIPT_MANIFEST_PATH)
        self.chunk_manifest = []
        self.chunk_counter = 0
        self.session_started_at = None
        self.session_chunk_seconds = recording_duration
        self.manifest_lock = asyncio.Lock()

    def _build_ffmpeg_command(self, audio_filename: Path, duration: int) -> list[str]:
        if not FFMPEG_INPUT_FORMAT or not FFMPEG_INPUT_DEVICE:
            raise RuntimeError(
                "FFmpeg input source is not configured for this platform. "
                "Set FFMPEG_INPUT_FORMAT and FFMPEG_INPUT_DEVICE in .env."
            )
        return [
            'ffmpeg',
            '-f', FFMPEG_INPUT_FORMAT,
            '-i', FFMPEG_INPUT_DEVICE,
            '-t', str(duration),
            '-acodec', 'libmp3lame',
            '-ar', str(AUDIO_SAMPLE_RATE),
            '-ac', str(AUDIO_CHANNELS),
            '-b:a', AUDIO_BITRATE,
            str(audio_filename),
        ]

    async def initialize_session_files(self, duration: int) -> None:
        self.chunk_manifest = []
        self.chunk_counter = 0
        self.session_started_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self.session_chunk_seconds = duration

        try:
            self.transcript_path.write_text("", encoding="utf-8")
            self.transcript_manifest_path.write_text("", encoding="utf-8")
        except Exception as exc:
            logging.error("Failed to initialize transcript artifacts: %s", exc)

        await self.persist_manifest()

    async def persist_manifest(self) -> None:
        manifest = {
            "session_started_at": self.session_started_at,
            "recording_chunk_seconds": self.session_chunk_seconds,
            "chunks": self.chunk_manifest,
        }
        await asyncio.to_thread(
            self.transcript_manifest_path.write_text,
            json.dumps(manifest, ensure_ascii=False, indent=2),
            "utf-8",
        )

    async def register_chunk(self, audio_filename: Path, duration: int) -> dict:
        return await self.register_external_chunk(audio_filename, duration, self.chunk_counter * duration)

    async def register_external_chunk(self, audio_filename: Path, duration: int, start_offset_seconds: int) -> dict:
        async with self.manifest_lock:
            self.chunk_counter += 1
            chunk = {
                "chunk_index": self.chunk_counter,
                "audio_file": str(audio_filename),
                "start_offset_seconds": start_offset_seconds,
                "duration_seconds": duration,
                "status": "recorded",
                "notes": [],
                "segments": [],
            }
            self.chunk_manifest.append(chunk)
            await self.persist_manifest()
            return chunk

    async def update_chunk_result(
        self,
        chunk_index: int,
        *,
        status: str,
        notes: list[str] | None = None,
        segments: list[dict] | None = None,
        error: str | None = None,
    ) -> None:
        async with self.manifest_lock:
            chunk = next((item for item in self.chunk_manifest if item["chunk_index"] == chunk_index), None)
            if chunk is None:
                logging.warning("Chunk %s missing from manifest during update.", chunk_index)
                return
            chunk["status"] = status
            if notes is not None:
                chunk["notes"] = notes
            if segments is not None:
                chunk["segments"] = segments
            if error:
                chunk["error"] = error
            await self.persist_manifest()

    def _format_timestamp(self, total_seconds: int) -> str:
        hours, remainder = divmod(max(0, int(total_seconds)), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _extract_json_payload(self, response_text: str) -> dict:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        if not cleaned.startswith("{"):
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start:end + 1]
        return json.loads(cleaned)

    async def rebuild_transcript_from_manifest(self) -> str:
        warnings = []
        lines = []
        sorted_chunks = sorted(self.chunk_manifest, key=lambda item: item["chunk_index"])

        for chunk in sorted_chunks:
            chunk_index = chunk["chunk_index"]
            if chunk.get("status") != "transcribed":
                error_message = chunk.get("error") or "Chunk transcription unavailable."
                warnings.append(f"Chunk {chunk_index}: {error_message}")
                continue

            for segment in chunk.get("segments", []):
                absolute_seconds = chunk["start_offset_seconds"] + int(segment.get("offset_seconds", 0))
                timestamp = self._format_timestamp(absolute_seconds)
                mode = segment.get("mode", "UNCLEAR")
                speaker = segment.get("speaker") or "Unknown"
                character = segment.get("character")
                lang = segment.get("lang") or "RO+EN"
                header = f"[{timestamp}][{mode}][Speaker: {speaker}]"
                if character:
                    header += f"[Character: {character}]"
                header += f"[Lang: {lang}]"
                text = (segment.get("text") or "").strip()
                if text:
                    lines.append(f"{header} {text}")

        transcript_parts = []
        if self.session_started_at:
            transcript_parts.append(f"Session started: {self.session_started_at}")
        transcript_parts.append(f"Recording chunk seconds: {self.session_chunk_seconds}")

        manifest_notes = []
        for chunk in sorted_chunks:
            for note in chunk.get("notes", []):
                manifest_notes.append(f"Chunk {chunk['chunk_index']}: {note}")

        all_warnings = warnings + manifest_notes
        if all_warnings:
            transcript_parts.append("\n=== TRANSCRIPTION NOTES ===")
            transcript_parts.extend(f"- {warning}" for warning in all_warnings)

        transcript_parts.append("\n=== SESSION TRANSCRIPT ===")
        transcript_parts.extend(lines or ["[00:00:00][UNCLEAR][Speaker: Unknown][Lang: RO+EN] No transcript content captured."])

        transcript_content = "\n".join(transcript_parts).strip() + "\n"
        await asyncio.to_thread(self.transcript_path.write_text, transcript_content, "utf-8")
        return transcript_content

    async def reset_session_artifacts(self) -> None:
        try:
            self.transcript_path.write_text("", encoding="utf-8")
        except Exception as exc:
            logging.error("Error clearing transcript file: %s", exc)

        try:
            self.transcript_manifest_path.write_text("", encoding="utf-8")
        except Exception as exc:
            logging.error("Error clearing transcript manifest file: %s", exc)

    async def build_audio_summary_windows(self) -> list[dict]:
        windows = []
        transcribed_chunks = [chunk for chunk in sorted(self.chunk_manifest, key=lambda item: item["chunk_index"]) if chunk.get("audio_file")]
        if not transcribed_chunks:
            return windows

        step = max(1, AUDIO_SUMMARY_WINDOW_CHUNKS)
        window_index = 0
        for i in range(0, len(transcribed_chunks), step):
            subset = transcribed_chunks[i:i + step]
            if not subset:
                continue
            window_index += 1
            windows.append(
                {
                    "window_index": window_index,
                    "start_offset_seconds": subset[0]["start_offset_seconds"],
                    "end_offset_seconds": subset[-1]["start_offset_seconds"] + subset[-1]["duration_seconds"],
                    "file_paths": [chunk["audio_file"] for chunk in subset if Path(chunk["audio_file"]).exists()],
                    "chunk_indexes": [chunk["chunk_index"] for chunk in subset],
                }
            )
        return windows

    async def summarize_audio_windows(self) -> list[dict]:
        window_summaries = []
        windows = await self.build_audio_summary_windows()
        for window in windows:
            if not window["file_paths"]:
                continue
            prompt = build_audio_summary_chunk_prompt(
                window["window_index"],
                window["start_offset_seconds"],
                window["end_offset_seconds"],
            )
            try:
                result = await asyncio.to_thread(
                    gemini_client.generate_text_from_files,
                    window["file_paths"],
                    prompt,
                    GEMINI_SUMMARY_MODEL,
                )
                payload = self._extract_json_payload(result)
                payload.setdefault("window_index", window["window_index"])
                payload.setdefault("start_offset_seconds", window["start_offset_seconds"])
                payload.setdefault("end_offset_seconds", window["end_offset_seconds"])
                window_summaries.append(payload)
            except Exception as exc:
                logging.error("Audio summary window %s failed: %s", window["window_index"], exc)
                window_summaries.append(
                    {
                        "window_index": window["window_index"],
                        "start_offset_seconds": window["start_offset_seconds"],
                        "end_offset_seconds": window["end_offset_seconds"],
                        "objective_notes": [],
                        "narrative_notes": [],
                        "notable_cues": [],
                        "uncertainties": [f"Window summary failed: {exc}"],
                    }
                )
        return window_summaries

    def _format_audio_summary_notes(self, window_summaries: list[dict]) -> str:
        sections = []
        for window in window_summaries:
            start_time = self._format_timestamp(window.get("start_offset_seconds", 0))
            end_time = self._format_timestamp(window.get("end_offset_seconds", 0))
            sections.append(f"=== AUDIO WINDOW {window.get('window_index', '?')} [{start_time} - {end_time}] ===")
            objective_notes = window.get("objective_notes", [])
            narrative_notes = window.get("narrative_notes", [])
            notable_cues = window.get("notable_cues", [])
            uncertainties = window.get("uncertainties", [])
            sections.append("Objective notes:")
            sections.extend(f"- {note}" for note in objective_notes or ["None"])
            sections.append("Narrative notes:")
            sections.extend(f"- {note}" for note in narrative_notes or ["None"])
            sections.append("Notable cues:")
            sections.extend(f"- {note}" for note in notable_cues or ["None"])
            sections.append("Uncertainties:")
            sections.extend(f"- {note}" for note in uncertainties or ["None"])
            sections.append("")
        return "\n".join(sections).strip()

    def probe_audio_duration(self, audio_file: Path) -> int:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(audio_file),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return max(1, int(round(float(result.stdout.strip()))))
        except Exception as exc:
            logging.warning("Could not determine duration for %s via ffprobe: %s", audio_file, exc)
            return self.session_chunk_seconds

    def split_audio_file_for_offline(self, audio_file: Path, output_dir: Path) -> list[Path]:
        duration = self.probe_audio_duration(audio_file)
        if duration <= self.session_chunk_seconds:
            return [audio_file]

        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = audio_file.suffix or ".mp3"
        output_pattern = output_dir / f"{audio_file.stem}_part_%03d{suffix}"
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(audio_file),
                    "-f",
                    "segment",
                    "-segment_time",
                    str(self.session_chunk_seconds),
                    "-reset_timestamps",
                    "1",
                    "-c",
                    "copy",
                    str(output_pattern),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except Exception as exc:
            logging.warning(
                "Failed to split %s into %s-second segments, falling back to original file: %s",
                audio_file,
                self.session_chunk_seconds,
                exc,
            )
            return [audio_file]

        segment_paths = sorted(output_dir.glob(f"{audio_file.stem}_part_*{suffix}"))
        if not segment_paths:
            logging.warning("No offline segments were produced for %s; using original file.", audio_file)
            return [audio_file]
        return segment_paths

    async def build_final_summaries_from_windows(self, window_summaries: list[dict]) -> tuple[str | None, str | None]:
        if not window_summaries:
            return None, None

        notes_text = self._format_audio_summary_notes(window_summaries)
        objective_prompt = build_audio_objective_summary_prompt(notes_text)
        narrative_prompt = build_audio_narrative_summary_prompt(notes_text)

        objective_summary = await asyncio.to_thread(
            gemini_client.generate_summary_text,
            objective_prompt,
            None,
        )
        narrative_summary = await asyncio.to_thread(
            gemini_client.generate_summary_text,
            narrative_prompt,
            None,
        )
        return objective_summary, narrative_summary

    async def process_existing_audio_files(self, file_paths: list[str], output_dir: str | None = None) -> dict:
        resolved_paths = [Path(path).expanduser() for path in file_paths]
        for path in resolved_paths:
            if not path.exists():
                raise FileNotFoundError(f"Audio file not found: {path}")

        output_root = Path(output_dir).expanduser() if output_dir else Path(__file__).parent / "offline_test_outputs"
        output_root.mkdir(parents=True, exist_ok=True)

        session_label = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        transcript_output_path = output_root / f"transcript_{session_label}.txt"
        objective_output_path = output_root / f"objective_summary_{session_label}.md"
        narrative_output_path = output_root / f"narrative_summary_{session_label}.md"
        manifest_output_path = output_root / f"manifest_{session_label}.json"
        segment_output_root = output_root / f"_segments_{session_label}"

        await self.initialize_session_files(self.session_chunk_seconds)

        running_offset = 0
        split_file_paths: list[Path] = []
        for file_index, file_path in enumerate(resolved_paths, start=1):
            split_dir = segment_output_root / f"input_{file_index:03d}"
            split_file_paths.extend(self.split_audio_file_for_offline(file_path, split_dir))

        try:
            for file_path in split_file_paths:
                duration = self.probe_audio_duration(file_path)
                chunk_info = await self.register_external_chunk(file_path, duration, running_offset)
                await self.send_to_openai(file_path, chunk_info)
                running_offset += duration

            transcript_text = await self.rebuild_transcript_from_manifest()
            window_summaries = await self.summarize_audio_windows()
            objective_summary, narrative_summary = await self.build_final_summaries_from_windows(window_summaries)

            transcript_output_path.write_text(transcript_text, encoding="utf-8")
            manifest_output_path.write_text(
                json.dumps(
                    {
                        "window_summaries": window_summaries,
                        "chunks": self.chunk_manifest,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            if objective_summary:
                objective_output_path.write_text(objective_summary, encoding="utf-8")
            if narrative_summary:
                narrative_output_path.write_text(narrative_summary, encoding="utf-8")

            return {
                "transcript_path": str(transcript_output_path),
                "objective_summary_path": str(objective_output_path),
                "narrative_summary_path": str(narrative_output_path),
                "manifest_path": str(manifest_output_path),
                "segment_dir": str(segment_output_root),
            }
        finally:
            if segment_output_root.exists() and not KEEP_AUDIO_FILES:
                for segment_file in sorted(segment_output_root.rglob("*"), reverse=True):
                    try:
                        if segment_file.is_file():
                            segment_file.unlink()
                        else:
                            segment_file.rmdir()
                    except OSError:
                        pass

    async def capture_audio(self, voice_client, duration=recording_duration): #120 seconds or 5-10 for testing.
        self.voice_client = voice_client
        await self.initialize_session_files(duration)
        logging.info("Starting continuous audio capture...")

        while True:
            if self.voice_client and self.voice_client.is_connected():
                members_count = len(self.voice_client.channel.members)
                logging.info(f"Current members in voice channel: {members_count}")

                if members_count <= 1:  # Check if only the bot is left
                    logging.info("No members left in the voice channel. Preparing to finalize recording...")
                    await asyncio.sleep(5)  # Wait for a minute to see if anyone rejoins
                    if len(self.voice_client.channel.members) == 1:  # Confirm no one has joined
                        logging.info("No members have joined within the timeout period. Proceeding to finalize...")

                        # Wait for all transcription tasks to complete
                        if self.transcription_tasks:
                            await asyncio.gather(*self.transcription_tasks)

                        category_id = get_category_id_voice(self.voice_client.channel)
                        logging.info(f"Retrieved category ID: {category_id}")
                        await self.rebuild_transcript_from_manifest()
                        # Call the summarize function
                        await self.summarize_transcript(category_id)

                        # Proceed to clean up files after summarization
                        await self.cleanup_files()
                        
                        # Leave the voice channel after everything is done
                        await self.voice_client.disconnect()  
                        logging.info("Disconnected from voice channel.")
                        break  # Exit the recording loop

                chunk_number = self.chunk_counter + 1
                audio_filename = audio_files_path / f'audio_recording_{chunk_number:03d}.mp3'
                
                try:
                    logging.info(f"Recording for {duration} seconds... Saving to {audio_filename}")
                    proc = await asyncio.create_subprocess_exec(
                        *self._build_ffmpeg_command(audio_filename, duration),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    _, stderr = await proc.communicate()
                    ffmpeg_error = stderr.decode('utf-8', errors='ignore').strip()
                    logging.info(f"Audio recording completed and saved as {audio_filename}")

                    if audio_filename.exists() and audio_filename.stat().st_size > 0:
                        chunk_info = await self.register_chunk(audio_filename, duration)
                        # Send the audio file for transcription as a background task
                        task = asyncio.create_task(self.send_to_openai(audio_filename, chunk_info))
                        self.transcription_tasks.append(task)  # Track the task
                        task.add_done_callback(lambda t: self.transcription_tasks.remove(t))  # Remove task after completion
                    else:
                        logging.error(f"Audio file {audio_filename} does not exist or is empty after recording. %s", ffmpeg_error)
                except Exception as e:
                    logging.error(f"Failed during audio recording: {e}")
                    break

                await asyncio.sleep(0.2)
            else:
                logging.info("Voice client not connected. Exiting recording loop.")
                break

    async def process_final_transcription(self):
        logging.info("Processing any recorded chunks that are still pending transcription...")
        pending_chunks = [
            chunk for chunk in self.chunk_manifest
            if chunk.get("status") == "recorded" and Path(chunk.get("audio_file", "")).exists()
        ]

        for chunk in pending_chunks:
            audio_file = Path(chunk["audio_file"])
            logging.info("Transcribing pending file: %s", audio_file.name)
            await self.send_to_openai(audio_file, chunk)

        logging.info("Final transcription processing completed.")

    async def archive_transcript(self, content):
        """Append the transcript content to the archive with formatting."""
        archive_path = Path(__file__).parent / 'transcript_archive.txt'
        try:
            with open(archive_path, 'a', encoding='utf-8') as archive_file:  # <- This is the critical line
                # Write the separator and headers
                archive_file.write("\n\n\n")
                archive_file.write("_______________________________________________________________________\n")
                archive_file.write("\n\n")
                archive_file.write("SESSION TRANSCRIPTION\n")
                archive_file.write("_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _\n")
                archive_file.write("\n\n")
                # Write the content
                archive_file.write(content)
                # Add some spacing after the content
                archive_file.write("\n\n")
            logging.info("Transcript archived successfully.")
        except Exception as e:
            logging.error(f"Error archiving transcript: {e}")

    async def cleanup_files(self):
        """Cleanup transcript.txt and audio files."""
        logging.info("Cleaning up transcript and audio files...")
        category_id = get_category_id_voice(self.voice_client.channel)
        guild = self.voice_client.guild
        summary_channel = discord.utils.get(guild.text_channels, name='session-summary', category_id=category_id)
        if not summary_channel:
            logging.error(f"Could not find 'session-summary' channel in category {category_id}.")
            return

        # Read transcript content for archiving
        try:
            with open(self.transcript_path, 'r', encoding='utf-8') as f:
                transcript_content = f.read()
        except Exception as e:
            logging.error(f"Error reading transcript for archiving: {e}")
            transcript_content = ""

        # Archive the transcript
        await self.archive_transcript(transcript_content)

        await summary_channel.send("Full transcript attached:", file=discord.File(self.transcript_path))

        if KEEP_AUDIO_FILES:
            logging.info("KEEP_AUDIO_FILES=true, leaving recorded audio files in place.")
        else:
            for filename in os.listdir(audio_files_path):
                file_path = audio_files_path / filename
                try:
                    os.remove(file_path)
                    logging.info(f"Deleted audio file: {file_path}")
                except Exception as e:
                    logging.error(f"Failed to delete audio file {file_path}: {e}")

        if KEEP_TRANSCRIPT_FILES:
            logging.info("KEEP_TRANSCRIPT_FILES=true, leaving transcript artifacts in place.")
        else:
            await self.reset_session_artifacts()
            logging.info("Transcript artifacts cleared.")

    async def send_to_openai(self, audio_filename, chunk_info):
        """Legacy method name kept for compatibility; uses Gemini for transcription."""
        logging.info("Preparing to send %s to Gemini for transcription...", audio_filename)
        
        if not audio_filename.exists() or audio_filename.stat().st_size == 0:
            logging.error(f"Audio file {audio_filename} does not exist or is empty.")
            return

        try:
            prompt = build_transcript_capture_prompt(
                chunk_info["chunk_index"],
                chunk_info["start_offset_seconds"],
                chunk_info["duration_seconds"],
                AUDIO_PROMPT,
            )
            transcript = await asyncio.to_thread(
                gemini_client.transcribe_audio,
                str(audio_filename),
                prompt,
            )
            logging.info("Received transcription: %s", transcript[:100])
            payload = self._extract_json_payload(transcript)
            await self.update_chunk_result(
                chunk_info["chunk_index"],
                status="transcribed",
                notes=payload.get("notes", []),
                segments=payload.get("segments", []),
            )
        except Exception as e:
            logging.error("Unexpected error during Gemini transcription request: %s", e)
            await self.update_chunk_result(
                chunk_info["chunk_index"],
                status="failed",
                error=str(e),
            )


    async def summarize_transcript(self, category_id):
        logging.info("Starting audio-native session summarization...")

        if not self.voice_client:
            logging.error("Voice client is not connected. Cannot summarize transcript.")
            return

        guild = self.voice_client.guild
        summary_channel = discord.utils.get(guild.text_channels, name='session-summary', category_id=category_id)
        if not summary_channel:
            logging.error(f"Could not find 'session-summary' channel in category {category_id}.")
            return

        window_summaries = await self.summarize_audio_windows()
        if not window_summaries:
            logging.warning("No audio summary windows were produced. No summary generated.")
            return
        await summary_channel.send("Generating session summaries from audio-derived notes...")
        objective_summary = None
        narrative_summary = None
        try:
            objective_summary, narrative_summary = await self.build_final_summaries_from_windows(window_summaries)
            if not objective_summary:
                raise RuntimeError("Objective summary generation returned no content.")
            await summary_channel.send("**Objective Summary**")
            await send_response_in_chunks(summary_channel, objective_summary)
        except Exception as exc:
            logging.error("Error generating objective session summary: %s", exc)
            await summary_channel.send(f"Error generating objective session summary: {exc}")

        try:
            if not narrative_summary:
                raise RuntimeError("Narrative summary generation returned no content.")
            await summary_channel.send("**Narrative Summary**")
            await send_response_in_chunks(summary_channel, narrative_summary)
        except Exception as exc:
            logging.error("Error generating narrative session summary: %s", exc)
            await summary_channel.send(f"Error generating narrative session summary: {exc}")

        logging.info("Audio-native transcript summarization completed.")
        return
