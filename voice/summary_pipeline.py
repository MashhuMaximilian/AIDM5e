import asyncio
import logging
from pathlib import Path

from config import AUDIO_SUMMARY_WINDOW_CHUNKS, GEMINI_SUMMARY_MODEL
from ai_services.gemini_client import gemini_client
from prompts.transcription_prompts import (
    build_audio_narrative_summary_prompt,
    build_audio_objective_summary_prompt,
    build_audio_summary_chunk_prompt,
)
from .transcript_manifest import TranscriptManifestStore
from .transcript_pipeline import TranscriptService


logger = logging.getLogger(__name__)


class AudioSummaryService:
    def __init__(self, transcript_service: TranscriptService) -> None:
        self.transcript_service = transcript_service

    async def build_audio_summary_windows(self, manifest_store: TranscriptManifestStore) -> list[dict]:
        windows = []
        transcribed_chunks = [
            chunk for chunk in manifest_store.sorted_chunks() if chunk.get("audio_file")
        ]
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

    async def summarize_audio_windows(
        self,
        manifest_store: TranscriptManifestStore,
        context_block: str | None = None,
    ) -> list[dict]:
        window_summaries = []
        windows = await self.build_audio_summary_windows(manifest_store)
        for window in windows:
            if not window["file_paths"]:
                continue
            prompt = build_audio_summary_chunk_prompt(
                window["window_index"],
                window["start_offset_seconds"],
                window["end_offset_seconds"],
                context_block,
            )
            try:
                result = await asyncio.to_thread(
                    gemini_client.generate_text_from_files,
                    window["file_paths"],
                    prompt,
                    GEMINI_SUMMARY_MODEL,
                )
                payload = self.transcript_service.extract_json_payload(result)
                payload.setdefault("window_index", window["window_index"])
                payload.setdefault("start_offset_seconds", window["start_offset_seconds"])
                payload.setdefault("end_offset_seconds", window["end_offset_seconds"])
                window_summaries.append(payload)
            except Exception as exc:
                logger.error("Audio summary window %s failed: %s", window["window_index"], exc)
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

    def format_audio_summary_notes(self, window_summaries: list[dict]) -> str:
        sections = []
        for window in window_summaries:
            start_time = self.transcript_service.format_timestamp(window.get("start_offset_seconds", 0))
            end_time = self.transcript_service.format_timestamp(window.get("end_offset_seconds", 0))
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

    async def build_final_summaries_from_windows(
        self,
        window_summaries: list[dict],
        context_block: str | None = None,
    ) -> tuple[str | None, str | None]:
        if not window_summaries:
            return None, None

        notes_text = self.format_audio_summary_notes(window_summaries)
        objective_prompt = build_audio_objective_summary_prompt(notes_text, context_block)
        narrative_prompt = build_audio_narrative_summary_prompt(notes_text, context_block)

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
