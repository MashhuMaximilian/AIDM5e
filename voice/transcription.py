import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import discord

from ai_services.context_compiler import compile_context_packet_from_category
from .audio_utils import get_category_id_voice, probe_audio_duration, split_audio_file_for_offline
from .context_support import load_voice_context
from .orchestrator import VoiceSessionOrchestrator
from config import (
    AUDIO_CHUNK_SECONDS,
    AUDIO_FILES_PATH,
    TRANSCRIPT_MANIFEST_PATH,
    TRANSCRIPT_PATH,
    VOICE_INCLUDE_DM_CONTEXT,
)
from discord_app.shared_functions import send_response_in_chunks
from .summary_pipeline import AudioSummaryService
from .transcript_manifest import TranscriptManifestStore
from .transcript_outputs import TranscriptOutputService
from .transcript_pipeline import TranscriptService
from .voice_capture import VoiceCaptureService


recording_duration = AUDIO_CHUNK_SECONDS
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

audio_files_path = Path(AUDIO_FILES_PATH)
audio_files_path.mkdir(exist_ok=True)


class VoiceRecorder:
    def __init__(self):
        self.voice_client = None
        self.transcription_tasks = []
        self.transcript_path = Path(TRANSCRIPT_PATH)
        self.transcript_manifest_path = Path(TRANSCRIPT_MANIFEST_PATH)
        self.session_chunk_seconds = recording_duration
        self.manifest_store = TranscriptManifestStore(
            self.transcript_path,
            self.transcript_manifest_path,
            self.session_chunk_seconds,
        )
        self.transcript_service = TranscriptService(self.transcript_path)
        self.summary_service = AudioSummaryService(self.transcript_service)
        self.output_service = TranscriptOutputService(
            self.transcript_path,
            self.transcript_manifest_path,
            audio_files_path,
        )
        self.context_block = None
        self.capture_service = VoiceCaptureService(audio_files_path)
        self.orchestrator = VoiceSessionOrchestrator()

    async def initialize_session_files(self, duration: int) -> None:
        self.session_chunk_seconds = duration
        await self.manifest_store.initialize_session_files(duration)

    async def persist_manifest(self) -> None:
        await self.manifest_store.persist()

    async def register_chunk(self, audio_filename: Path, duration: int) -> dict:
        return await self.manifest_store.register_chunk(audio_filename, duration)

    async def register_external_chunk(self, audio_filename: Path, duration: int, start_offset_seconds: int) -> dict:
        return await self.manifest_store.register_external_chunk(audio_filename, duration, start_offset_seconds)

    async def update_chunk_result(self, chunk_index: int, **kwargs) -> None:
        await self.manifest_store.update_chunk_result(chunk_index, **kwargs)

    def _format_timestamp(self, total_seconds: int) -> str:
        return self.transcript_service.format_timestamp(total_seconds)

    def _extract_json_payload(self, response_text: str) -> dict:
        return self.transcript_service.extract_json_payload(response_text)

    async def rebuild_transcript_from_manifest(self) -> str:
        return await self.transcript_service.rebuild_transcript_from_manifest(self.manifest_store)

    async def reset_session_artifacts(self) -> None:
        await self.manifest_store.clear_transcript_artifacts()

    async def build_audio_summary_windows(self) -> list[dict]:
        return await self.summary_service.build_audio_summary_windows(self.manifest_store)

    async def summarize_audio_windows(self) -> list[dict]:
        return await self.summary_service.summarize_audio_windows(self.manifest_store, self.context_block)

    def _format_audio_summary_notes(self, window_summaries: list[dict]) -> str:
        return self.summary_service.format_audio_summary_notes(window_summaries)

    def probe_audio_duration(self, audio_file: Path) -> int:
        return probe_audio_duration(audio_file, self.session_chunk_seconds)

    def split_audio_file_for_offline(self, audio_file: Path, output_dir: Path) -> list[Path]:
        return split_audio_file_for_offline(audio_file, output_dir, self.session_chunk_seconds)

    async def build_final_summaries_from_windows(self, window_summaries: list[dict]) -> tuple[str | None, str | None]:
        return await self.summary_service.build_final_summaries_from_windows(window_summaries, self.context_block)

    async def refresh_context_from_category(self, category: discord.CategoryChannel | None) -> None:
        packet = await compile_context_packet_from_category(
            category,
            include_dm_context=VOICE_INCLUDE_DM_CONTEXT,
        )
        self.context_block = packet.text_block

    async def process_existing_audio_files(
        self,
        file_paths: list[str],
        output_dir: str | None = None,
        *,
        public_context_path: str | None = None,
        session_context_path: str | None = None,
        dm_context_path: str | None = None,
        include_dm_context: bool | None = None,
    ) -> dict:
        resolved_paths = [Path(path).expanduser() for path in file_paths]
        for path in resolved_paths:
            if not path.exists():
                raise FileNotFoundError(f"Audio file not found: {path}")
        self.context_block = load_voice_context(
            public_context_path=public_context_path,
            session_context_path=session_context_path,
            dm_context_path=dm_context_path,
            include_dm_context=include_dm_context,
        )

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
                    self.manifest_store.build_manifest_payload(window_summaries=window_summaries),
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
            self.output_service.cleanup_offline_segments(segment_output_root)

    async def capture_audio(self, voice_client, duration=recording_duration):
        await self.refresh_context_from_category(getattr(voice_client.channel, "category", None))
        await self.capture_service.capture_audio(self, voice_client, duration)

    async def process_final_transcription(self):
        await self.capture_service.process_pending_transcriptions(self)

    async def archive_transcript(self, content):
        await self.output_service.archive_transcript(content)

    async def cleanup_files(self):
        logging.info("Cleaning up transcript and audio files...")
        category_id = get_category_id_voice(self.voice_client.channel)
        guild = self.voice_client.guild
        summary_channel = discord.utils.get(guild.text_channels, name="session-summary", category_id=category_id)
        if not summary_channel:
            logging.error("Could not find 'session-summary' channel in category %s.", category_id)
            return

        await self.output_service.post_transcript_to_channel(summary_channel)
        await self.output_service.cleanup_live_artifacts(self.voice_client, self.reset_session_artifacts)

    async def send_to_openai(self, audio_filename, chunk_info):
        await self.transcript_service.transcribe_chunk(
            Path(audio_filename),
            chunk_info,
            self.manifest_store,
            self.context_block,
        )

    async def summarize_transcript(self, category_id):
        logging.info("Starting audio-native session summarization...")

        if not self.voice_client:
            logging.error("Voice client is not connected. Cannot summarize transcript.")
            return

        await self.refresh_context_from_category(getattr(self.voice_client.channel, "category", None))

        guild = self.voice_client.guild
        summary_channel = discord.utils.get(guild.text_channels, name="session-summary", category_id=category_id)
        if not summary_channel:
            logging.error("Could not find 'session-summary' channel in category %s.", category_id)
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
