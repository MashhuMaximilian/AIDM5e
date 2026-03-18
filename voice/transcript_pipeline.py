import asyncio
import json
import logging
import re
from pathlib import Path

from ai_services.gemini_client import gemini_client
from config import AUDIO_PROMPT
from prompts.transcription_prompts import build_transcript_capture_prompt
from .transcript_manifest import TranscriptManifestStore


logger = logging.getLogger(__name__)


class TranscriptService:
    def __init__(self, transcript_path: Path) -> None:
        self.transcript_path = transcript_path
        self._role_like_character_labels = {
            "father",
            "daughter",
            "mother",
            "son",
            "dm",
            "dungeon master",
            "player",
            "narrator",
            "speaker",
            "unknown",
        }

    def format_timestamp(self, total_seconds: int) -> str:
        hours, remainder = divmod(max(0, int(total_seconds)), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def extract_json_payload(self, response_text: str) -> dict:
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

    def normalize_lang(self, lang: str | None) -> str:
        if not lang:
            return "RO+EN"
        normalized = lang.strip().upper().replace(" ", "")
        if normalized in {"RO", "EN", "RO+EN"}:
            return normalized
        if normalized in {"EN+RO", "RO/EN", "EN/RO", "RO-EN", "EN-RO"}:
            return "RO+EN"
        return "RO+EN"

    def normalize_mode(self, mode: str | None) -> str:
        if not mode:
            return "UNCLEAR"
        normalized = mode.strip().upper()
        aliases = {
            "IN_CHARACTER": "IC",
            "OUT_OF_CHARACTER": "OOC",
            "OUT-OF-CHARACTER": "OOC",
            "OUT OF CHARACTER": "OOC",
            "IN-CHARACTER": "IC",
            "IN CHARACTER": "IC",
            "META": "META",
            "UNCLEAR": "UNCLEAR",
            "RULES": "OOC",
            "COMBAT": "IC",
        }
        return aliases.get(normalized, normalized if normalized in {"IC", "OOC", "META", "UNCLEAR"} else "UNCLEAR")

    def normalize_speaker(self, speaker: str | None) -> str:
        if not speaker:
            return "Unknown"
        cleaned = speaker.strip()
        if not cleaned:
            return "Unknown"
        normalized = cleaned.lower()
        if normalized in {"unknown", "unclear", "speaker", "speaker unknown"}:
            return "Unknown"

        match = re.search(r"(unknown|speaker)\s*[-_:]?\s*(\d+)", normalized)
        if match:
            return f"Unknown {match.group(2)}"

        if normalized.startswith("unknown ") or normalized.startswith("speaker "):
            suffix = cleaned.split(maxsplit=1)[-1]
            if suffix.isdigit():
                return f"Unknown {suffix}"

        return cleaned

    def normalize_character(self, character: str | None) -> str | None:
        if not character:
            return None
        cleaned = character.strip()
        if not cleaned:
            return None
        maybe_prefixes = ("maybe ", "uncertain ", "possibly ", "probably ")
        lowered = cleaned.lower()
        for prefix in maybe_prefixes:
            if lowered.startswith(prefix):
                candidate = cleaned[len(prefix):].strip()
                if not candidate or candidate.lower() in self._role_like_character_labels:
                    return None
                return f"MAYBE {candidate}"
        if lowered in self._role_like_character_labels:
            return None
        return cleaned

    def normalize_segment(self, segment: dict) -> dict:
        normalized = dict(segment)
        normalized["speaker"] = self.normalize_speaker(segment.get("speaker"))
        normalized["character"] = self.normalize_character(segment.get("character"))
        normalized["lang"] = self.normalize_lang(segment.get("lang"))
        normalized["mode"] = self.normalize_mode(segment.get("mode"))
        return normalized

    def normalize_offset_seconds(self, offset_seconds, chunk_start: int, chunk_duration: int) -> int:
        try:
            offset = int(offset_seconds)
        except (TypeError, ValueError):
            return 0

        if offset < 0:
            return 0

        # Gemini sometimes returns absolute session offsets for later chunks even
        # though we ask for chunk-relative offsets. If the value lines up with the
        # chunk's absolute window, convert it back to a relative offset.
        if chunk_start > 0 and offset > chunk_duration + 60 and chunk_start <= offset <= chunk_start + chunk_duration + 60:
            offset -= chunk_start

        if offset < 0:
            return 0
        return offset

    def _offset_candidates(self, raw_offset: int, chunk_start: int, chunk_duration: int) -> list[int]:
        candidates: list[int] = []

        def add(value: int | float | None) -> None:
            if value is None:
                return
            try:
                ivalue = int(value)
            except (TypeError, ValueError):
                return
            if 0 <= ivalue <= max(0, chunk_duration):
                candidates.append(ivalue)

        add(raw_offset)
        if chunk_start > 0:
            add(raw_offset - chunk_start)

        # Gemini sometimes leaks absolute or drifted timestamps. Modulo the
        # chunk duration gives us a chunk-local fallback that often matches the
        # intended offset much better than the raw value.
        if chunk_duration > 0:
            add(raw_offset % chunk_duration)

        # Keep order stable while removing duplicates.
        unique: list[int] = []
        seen = set()
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                unique.append(candidate)
        return unique

    def _choose_best_offset(self, raw_offset: int, chunk_start: int, chunk_duration: int, previous_offset: int | None) -> int:
        candidates = self._offset_candidates(raw_offset, chunk_start, chunk_duration)
        if not candidates:
            return 0 if previous_offset is None else previous_offset

        if previous_offset is None:
            return min(candidates)

        forward = [candidate for candidate in candidates if candidate >= previous_offset]
        if forward:
            return min(forward, key=lambda candidate: (candidate - previous_offset, candidate))

        # If every candidate goes backwards, preserve chronology conservatively.
        return max(previous_offset, min(candidates, key=lambda candidate: abs(candidate - previous_offset)))

    def normalize_segments(self, segments: list[dict], chunk_start: int = 0, chunk_duration: int = 0) -> list[dict]:
        normalized = [self.normalize_segment(segment) for segment in segments]
        previous_offset: int | None = None
        for segment in normalized:
            raw_offset = self.normalize_offset_seconds(
                segment.get("offset_seconds", 0),
                chunk_start,
                chunk_duration,
            )
            chosen_offset = self._choose_best_offset(raw_offset, chunk_start, chunk_duration, previous_offset)
            segment["offset_seconds"] = chosen_offset
            previous_offset = chosen_offset
        speaker_values = [segment.get("speaker") for segment in normalized if segment.get("speaker")]
        has_numbered_unknown = any(re.fullmatch(r"Unknown \d+", speaker or "") for speaker in speaker_values)
        plain_unknown_count = sum(1 for speaker in speaker_values if speaker == "Unknown")
        has_named_speaker = any(
            speaker not in {"Unknown"} and not re.fullmatch(r"Unknown \d+", speaker or "")
            for speaker in speaker_values
        )

        # If the model gave us only plain "Unknown" across a dialogue-heavy chunk,
        # use a conservative alternating fallback so the transcript preserves turn flow
        # better during review. We only do this when there are no named speakers and no
        # numbered unknowns already present.
        if not has_numbered_unknown and not has_named_speaker and plain_unknown_count >= 4:
            unknown_index = 0
            for segment in normalized:
                if segment.get("speaker") == "Unknown":
                    segment["speaker"] = f"Unknown {(unknown_index % 2) + 1}"
                    unknown_index += 1

        return normalized

    async def transcribe_chunk(
        self,
        audio_filename: Path,
        chunk_info: dict,
        manifest_store: TranscriptManifestStore,
        context_block: str | None = None,
    ) -> None:
        logger.info("Preparing to send %s to Gemini for transcription...", audio_filename)

        if not audio_filename.exists() or audio_filename.stat().st_size == 0:
            logger.error("Audio file %s does not exist or is empty.", audio_filename)
            return

        try:
            prompt = build_transcript_capture_prompt(
                chunk_info["chunk_index"],
                chunk_info["start_offset_seconds"],
                chunk_info["duration_seconds"],
                AUDIO_PROMPT,
                context_block,
            )
            transcript = await asyncio.to_thread(
                gemini_client.transcribe_audio,
                str(audio_filename),
                prompt,
            )
            logger.info("Received transcription: %s", transcript[:100])
            payload = self.extract_json_payload(transcript)
            normalized_segments = self.normalize_segments(
                payload.get("segments", []),
                chunk_info["start_offset_seconds"],
                chunk_info["duration_seconds"],
            )
            await manifest_store.update_chunk_result(
                chunk_info["chunk_index"],
                status="transcribed",
                notes=payload.get("notes", []),
                segments=normalized_segments,
            )
        except Exception as exc:
            logger.error("Unexpected error during Gemini transcription request: %s", exc)
            await manifest_store.update_chunk_result(
                chunk_info["chunk_index"],
                status="failed",
                error=str(exc),
            )

    async def rebuild_transcript_from_manifest(self, manifest_store: TranscriptManifestStore) -> str:
        warnings: list[str] = []
        lines: list[str] = []

        for chunk in manifest_store.sorted_chunks():
            chunk_index = chunk["chunk_index"]
            if chunk.get("status") != "transcribed":
                error_message = chunk.get("error") or "Chunk transcription unavailable."
                warnings.append(f"Chunk {chunk_index}: {error_message}")
                continue

            for segment in self.normalize_segments(
                chunk.get("segments", []),
                chunk["start_offset_seconds"],
                chunk["duration_seconds"],
            ):
                absolute_seconds = chunk["start_offset_seconds"] + int(segment.get("offset_seconds", 0))
                timestamp = self.format_timestamp(absolute_seconds)
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

        transcript_parts: list[str] = []
        if manifest_store.session_started_at:
            transcript_parts.append(f"Session started: {manifest_store.session_started_at}")
        transcript_parts.append(f"Recording chunk seconds: {manifest_store.session_chunk_seconds}")

        manifest_notes: list[str] = []
        for chunk in manifest_store.sorted_chunks():
            for note in chunk.get("notes", []):
                manifest_notes.append(f"Chunk {chunk['chunk_index']}: {note}")

        all_warnings = warnings + manifest_notes
        if all_warnings:
            transcript_parts.append("\n=== TRANSCRIPTION NOTES ===")
            transcript_parts.extend(f"- {warning}" for warning in all_warnings)

        transcript_parts.append("\n=== SESSION TRANSCRIPT ===")
        transcript_parts.extend(
            lines or ["[00:00:00][UNCLEAR][Speaker: Unknown][Lang: RO+EN] No transcript content captured."]
        )

        transcript_content = "\n".join(transcript_parts).strip() + "\n"
        await asyncio.to_thread(self.transcript_path.write_text, transcript_content, "utf-8")
        return transcript_content
