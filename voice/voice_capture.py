import asyncio
import logging
import threading
import time
import wave
from pathlib import Path

from .audio_utils import build_ffmpeg_command


logger = logging.getLogger(__name__)

try:
    from discord.ext import voice_recv
except Exception:  # pragma: no cover - optional runtime dependency guard
    voice_recv = None


DISCORD_PCM_SAMPLE_RATE = 48000
DISCORD_PCM_CHANNELS = 2
DISCORD_PCM_SAMPLE_WIDTH = 2


def _slugify_voice_label(value: str | None) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in (value or "unknown"))
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "unknown"


class _DiscordStreamChunkRecorder:
    def __init__(self, audio_files_path: Path) -> None:
        self.audio_files_path = audio_files_path
        self._lock = threading.Lock()
        self._window_started_at = time.monotonic()
        self._current_window_index = 0
        self._writers: dict[int, wave.Wave_write] = {}
        self._files: dict[int, dict] = {}

    def start_window(self, *, window_index: int) -> None:
        with self._lock:
            self._window_started_at = time.monotonic()
            self._current_window_index = window_index
            self._writers = {}
            self._files = {}

    def write(self, user, data) -> None:
        if not data or not getattr(data, "pcm", b""):
            return
        source_user = user or getattr(data, "source", None)
        user_id = int(getattr(source_user, "id", 0) or 0)
        display_name = (
            getattr(source_user, "display_name", None)
            or getattr(source_user, "global_name", None)
            or getattr(source_user, "name", None)
            or "Unknown"
        )

        with self._lock:
            if user_id not in self._writers:
                slug = _slugify_voice_label(display_name)
                file_path = self.audio_files_path / f"audio_recording_{self._current_window_index:03d}_{slug}_{user_id or 'unknown'}.wav"
                wav_handle = wave.open(str(file_path), "wb")
                wav_handle.setnchannels(DISCORD_PCM_CHANNELS)
                wav_handle.setsampwidth(DISCORD_PCM_SAMPLE_WIDTH)
                wav_handle.setframerate(DISCORD_PCM_SAMPLE_RATE)
                self._writers[user_id] = wav_handle
                self._files[user_id] = {
                    "path": file_path,
                    "source_user_id": user_id or None,
                    "source_user_name": display_name,
                }

            self._writers[user_id].writeframesraw(data.pcm)

    def rotate_window(self) -> tuple[int, list[dict]]:
        with self._lock:
            actual_duration = max(1, int(round(time.monotonic() - self._window_started_at)))
            finished_files = list(self._files.values())
            for writer in self._writers.values():
                writer.close()
            self._writers = {}
            self._files = {}
            self._window_started_at = time.monotonic()
            return actual_duration, finished_files


class VoiceCaptureService:
    def __init__(self, audio_files_path: Path) -> None:
        self.audio_files_path = audio_files_path

    async def process_pending_transcriptions(self, recorder) -> None:
        logger.info("Processing any recorded chunks that are still pending transcription...")
        pending_chunks = [
            chunk
            for chunk in recorder.manifest_store.pending_recorded_chunks()
            if Path(chunk.get("audio_file", "")).exists()
        ]

        for chunk in pending_chunks:
            audio_file = Path(chunk["audio_file"])
            logger.info("Transcribing pending file: %s", audio_file.name)
            await recorder.send_to_openai(audio_file, chunk)

        logger.info("Final transcription processing completed.")

    async def _register_and_transcribe_stream_files(
        self,
        recorder,
        *,
        window_files: list[dict],
        start_offset_seconds: int,
        duration: int,
    ) -> None:
        for file_info in window_files:
            audio_file = Path(file_info["path"])
            if not audio_file.exists() or audio_file.stat().st_size <= 44:
                continue
            chunk_info = await recorder.register_external_chunk(
                audio_file,
                duration,
                start_offset_seconds,
                source_user_id=file_info.get("source_user_id"),
                source_user_name=file_info.get("source_user_name"),
                capture_mode="discord_stream",
            )
            task = asyncio.create_task(recorder.send_to_openai(audio_file, chunk_info))
            recorder.transcription_tasks.append(task)
            task.add_done_callback(lambda t: recorder.transcription_tasks.remove(t))

    async def capture_discord_streams(self, recorder, voice_client, duration: int) -> None:
        if voice_recv is None:
            raise RuntimeError("discord-ext-voice-recv is not installed, so Discord stream capture is unavailable.")

        recorder.voice_client = voice_client
        await recorder.initialize_session_files(duration)
        logger.info("Starting Discord per-user audio capture...")

        stream_recorder = _DiscordStreamChunkRecorder(self.audio_files_path)
        stream_recorder.start_window(window_index=1)
        current_offset = 0
        current_window_index = 1

        sink = voice_recv.BasicSink(stream_recorder.write, decode=True)
        voice_client.listen(sink)

        try:
            while True:
                if recorder.voice_client and recorder.voice_client.is_connected():
                    members_count = len(recorder.voice_client.channel.members)
                    logger.info("Current members in voice channel: %s", members_count)

                    if members_count <= 1:
                        logger.info("No members left in the voice channel. Preparing to finalize recording...")
                        await asyncio.sleep(5)
                        if len(recorder.voice_client.channel.members) == 1:
                            logger.info("No members have joined within the timeout period. Proceeding to finalize...")
                            actual_duration, window_files = stream_recorder.rotate_window()
                            await self._register_and_transcribe_stream_files(
                                recorder,
                                window_files=window_files,
                                start_offset_seconds=current_offset,
                                duration=actual_duration,
                            )
                            if voice_client.is_listening():
                                voice_client.stop_listening()
                            await recorder.orchestrator.finalize_voice_session(recorder)
                            break

                    await asyncio.sleep(duration)
                    actual_duration, window_files = stream_recorder.rotate_window()
                    await self._register_and_transcribe_stream_files(
                        recorder,
                        window_files=window_files,
                        start_offset_seconds=current_offset,
                        duration=actual_duration,
                    )
                    current_offset += actual_duration
                    current_window_index += 1
                    stream_recorder.start_window(window_index=current_window_index)
                else:
                    logger.info("Voice client not connected. Exiting recording loop.")
                    break
        finally:
            if hasattr(voice_client, "is_listening") and voice_client.is_listening():
                voice_client.stop_listening()

    async def capture_audio(self, recorder, voice_client, duration: int) -> None:
        recorder.voice_client = voice_client
        await recorder.initialize_session_files(duration)
        logger.info("Starting continuous audio capture...")

        while True:
            if recorder.voice_client and recorder.voice_client.is_connected():
                members_count = len(recorder.voice_client.channel.members)
                logger.info("Current members in voice channel: %s", members_count)

                if members_count <= 1:
                    logger.info("No members left in the voice channel. Preparing to finalize recording...")
                    await asyncio.sleep(5)
                    if len(recorder.voice_client.channel.members) == 1:
                        logger.info("No members have joined within the timeout period. Proceeding to finalize...")
                        await recorder.orchestrator.finalize_voice_session(recorder)
                        break

                chunk_number = recorder.manifest_store.chunk_counter + 1
                audio_filename = self.audio_files_path / f"audio_recording_{chunk_number:03d}.mp3"

                try:
                    logger.info("Recording for %s seconds... Saving to %s", duration, audio_filename)
                    proc = await asyncio.create_subprocess_exec(
                        *build_ffmpeg_command(audio_filename, duration),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr = await proc.communicate()
                    ffmpeg_error = stderr.decode("utf-8", errors="ignore").strip()
                    logger.info("Audio recording completed and saved as %s", audio_filename)

                    if audio_filename.exists() and audio_filename.stat().st_size > 0:
                        chunk_info = await recorder.register_chunk(audio_filename, duration)
                        task = asyncio.create_task(recorder.send_to_openai(audio_filename, chunk_info))
                        recorder.transcription_tasks.append(task)
                        task.add_done_callback(lambda t: recorder.transcription_tasks.remove(t))
                    else:
                        logger.error(
                            "Audio file %s does not exist or is empty after recording. %s",
                            audio_filename,
                            ffmpeg_error,
                        )
                except Exception as exc:
                    logger.error("Failed during audio recording: %s", exc)
                    break

                await asyncio.sleep(0.2)
            else:
                logger.info("Voice client not connected. Exiting recording loop.")
                break
