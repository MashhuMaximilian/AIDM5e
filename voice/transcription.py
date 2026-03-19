import asyncio
import io
import json
import logging
from datetime import datetime
from pathlib import Path

import discord

from ai_services.context_compiler import (
    CompiledContextPacket,
    compile_context_packet_from_category,
    compile_context_packet_from_category_id,
)
from ai_services.gemini_client import gemini_client
from ai_services.scene_pipeline import scene_pipeline
from .audio_utils import get_category_id_voice, probe_audio_duration, split_audio_file_for_offline
from .context_support import build_context_block
from .orchestrator import VoiceSessionOrchestrator
from config import (
    AUDIO_CHUNK_SECONDS,
    AUDIO_FILES_PATH,
    TRANSCRIPT_MANIFEST_PATH,
    TRANSCRIPT_PATH,
    VOICE_INCLUDE_DM_CONTEXT,
)
from data_store.db_repository import get_campaign_image_settings
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
        self.context_packet = None
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
        self.context_packet = packet
        self.context_block = packet.text_block

    async def _generate_and_post_session_images(
        self,
        *,
        category: discord.CategoryChannel | None,
        objective_summary: str | None,
        narrative_summary: str | None,
        default_channel: discord.TextChannel | None,
    ) -> None:
        if category is None:
            return

        settings = await asyncio.to_thread(get_campaign_image_settings, category.id)
        if settings.session_image_mode != "auto":
            return

        if not objective_summary and not narrative_summary:
            logging.info("Skipping session image generation because no summaries were available.")
            return

        context_packet = await compile_context_packet_from_category(
            category,
            include_dm_context=settings.session_image_include_dm_context,
        )

        target_channel = default_channel
        if settings.session_image_post_channel_id:
            resolved = category.guild.get_channel(settings.session_image_post_channel_id)
            if isinstance(resolved, discord.TextChannel):
                target_channel = resolved
        if target_channel is None:
            logging.warning("No target channel available for session image generation in category %s.", category.id)
            return

        await target_channel.send("Generating session images from the summaries...")
        candidates = await scene_pipeline.extract_scene_candidates(
            objective_summary=objective_summary or "",
            narrative_summary=narrative_summary or "",
            context_packet=context_packet,
            max_scenes_cap=settings.session_image_max_scenes,
        )
        selected_scenes, rationale = await scene_pipeline.select_final_scenes(
            candidates,
            context_packet=context_packet,
            max_scenes_cap=settings.session_image_max_scenes,
        )

        if rationale:
            await send_response_in_chunks(target_channel, f"**Scene selection rationale**\n{rationale}")

        for index, scene in enumerate(selected_scenes, start=1):
            request = scene_pipeline.prepare_scene_image_request(
                scene,
                context_packet=context_packet,
                quality_mode=settings.session_image_quality,
            )
            images = gemini_client.generate_image(
                request.prompt,
                model_name=request.model_name,
                aspect_ratio=request.aspect_ratio,
                reference_images=request.reference_assets,
            )
            if not images:
                await target_channel.send(f"Skipping `{scene.title}` because Gemini returned no image.")
                continue

            image = images[0]
            extension = ".png" if image["mime_type"] == "image/png" else ".jpg"
            filename = f"session_scene_{index:02d}{extension}"
            file = discord.File(io.BytesIO(image["image_bytes"]), filename=filename)
            caption = (
                f"**{scene.title}**\n"
                f"• Focus: {scene.subject_focus or 'mixed'}\n"
                f"• Location: {scene.location or 'unspecified'}\n"
                f"• Aspect ratio: `{request.aspect_ratio}`\n"
                f"• Model: `{request.model_name}`"
            )
            await target_channel.send(caption, file=file)

    async def process_existing_audio_files(
        self,
        file_paths: list[str],
        output_dir: str | None = None,
        *,
        public_context_path: str | None = None,
        session_context_path: str | None = None,
        dm_context_path: str | None = None,
        include_dm_context: bool | None = None,
        discord_category_id: int | None = None,
        generate_images: bool = False,
        image_quality: str = "auto",
        image_aspect_ratio: str | None = None,
        image_max_scenes: int | None = None,
        image_reference_paths: list[str] | None = None,
    ) -> dict:
        resolved_paths = [Path(path).expanduser() for path in file_paths]
        for path in resolved_paths:
            if not path.exists():
                raise FileNotFoundError(f"Audio file not found: {path}")
        offline_context_packet = (
            await compile_context_packet_from_category_id(discord_category_id, include_dm_context=bool(include_dm_context))
            if discord_category_id
            else CompiledContextPacket()
        )
        if public_context_path:
            public_text = Path(public_context_path).expanduser().read_text(encoding="utf-8").strip()
            if public_text:
                offline_context_packet.public_text = "\n\n".join(
                    part for part in [offline_context_packet.public_text, public_text] if part
                )
        if session_context_path:
            session_text = Path(session_context_path).expanduser().read_text(encoding="utf-8").strip()
            if session_text:
                offline_context_packet.session_text = "\n\n".join(
                    part for part in [offline_context_packet.session_text, session_text] if part
                )
        if dm_context_path and include_dm_context:
            dm_text = Path(dm_context_path).expanduser().read_text(encoding="utf-8").strip()
            if dm_text:
                offline_context_packet.dm_text = "\n\n".join(
                    part for part in [offline_context_packet.dm_text, dm_text] if part
                )
        offline_context_packet.text_block = build_context_block(
            public_text=offline_context_packet.public_text,
            session_text=offline_context_packet.session_text,
            dm_text=offline_context_packet.dm_text,
        )
        self.context_block = offline_context_packet.text_block

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

            image_outputs: list[str] = []
            scene_manifest_output_path = None
            if generate_images and (objective_summary or narrative_summary):
                candidates = await scene_pipeline.extract_scene_candidates(
                    objective_summary=objective_summary or "",
                    narrative_summary=narrative_summary or "",
                    context_packet=offline_context_packet,
                    max_scenes_cap=image_max_scenes,
                )
                selected_scenes, rationale = await scene_pipeline.select_final_scenes(
                    candidates,
                    context_packet=offline_context_packet,
                    max_scenes_cap=image_max_scenes,
                )
                scene_manifest_output_path = output_root / f"scene_manifest_{session_label}.json"
                scene_manifest_output_path.write_text(
                    json.dumps(
                        {
                            "selection_rationale": rationale,
                            "selected_scenes": [scene.__dict__ for scene in selected_scenes],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                for index, scene in enumerate(selected_scenes, start=1):
                    request = scene_pipeline.prepare_scene_image_request(
                        scene,
                        context_packet=offline_context_packet,
                        quality_mode=image_quality,
                        aspect_ratio_override=image_aspect_ratio,
                    )
                    images = gemini_client.generate_image(
                        request.prompt,
                        model_name=request.model_name,
                        aspect_ratio=request.aspect_ratio,
                        reference_images=[
                            *[asset for asset in request.reference_assets if asset.is_image],
                            *[Path(path).expanduser() for path in (image_reference_paths or [])],
                        ],
                    )
                    for image_index, image in enumerate(images, start=1):
                        extension = ".png" if image["mime_type"] == "image/png" else ".jpg"
                        image_path = output_root / f"scene_{index:02d}_image_{image_index:02d}{extension}"
                        image_path.write_bytes(image["image_bytes"])
                        image_outputs.append(str(image_path))

            return {
                "transcript_path": str(transcript_output_path),
                "objective_summary_path": str(objective_output_path),
                "narrative_summary_path": str(narrative_output_path),
                "manifest_path": str(manifest_output_path),
                "segment_dir": str(segment_output_root),
                "scene_manifest_path": str(scene_manifest_output_path) if scene_manifest_output_path else None,
                "image_paths": image_outputs,
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

        try:
            await self._generate_and_post_session_images(
                category=getattr(self.voice_client.channel, "category", None),
                objective_summary=objective_summary,
                narrative_summary=narrative_summary,
                default_channel=summary_channel,
            )
        except Exception as exc:
            logging.error("Error generating session images: %s", exc)
            await summary_channel.send(f"Error generating session images: {exc}")

        logging.info("Audio-native transcript summarization completed.")
