import asyncio
import json
from datetime import datetime
from pathlib import Path


class TranscriptManifestStore:
    def __init__(self, transcript_path: Path, manifest_path: Path, chunk_seconds: int) -> None:
        self.transcript_path = transcript_path
        self.manifest_path = manifest_path
        self.chunk_manifest: list[dict] = []
        self.chunk_counter = 0
        self.session_started_at: str | None = None
        self.session_chunk_seconds = chunk_seconds
        self.lock = asyncio.Lock()

    async def initialize_session_files(self, duration: int) -> None:
        self.chunk_manifest = []
        self.chunk_counter = 0
        self.session_started_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        self.session_chunk_seconds = duration

        self.transcript_path.write_text("", encoding="utf-8")
        self.manifest_path.write_text("", encoding="utf-8")
        await self.persist()

    async def persist(self) -> None:
        payload = {
            "session_started_at": self.session_started_at,
            "recording_chunk_seconds": self.session_chunk_seconds,
            "chunks": self.chunk_manifest,
        }
        await asyncio.to_thread(
            self.manifest_path.write_text,
            json.dumps(payload, ensure_ascii=False, indent=2),
            "utf-8",
        )

    async def register_chunk(self, audio_filename: Path, duration: int) -> dict:
        return await self.register_external_chunk(audio_filename, duration, self.chunk_counter * duration)

    async def register_external_chunk(
        self,
        audio_filename: Path,
        duration: int,
        start_offset_seconds: int,
        *,
        source_user_id: int | None = None,
        source_user_name: str | None = None,
        capture_mode: str | None = None,
    ) -> dict:
        async with self.lock:
            self.chunk_counter += 1
            chunk = {
                "chunk_index": self.chunk_counter,
                "audio_file": str(audio_filename),
                "start_offset_seconds": start_offset_seconds,
                "duration_seconds": duration,
                "status": "recorded",
                "notes": [],
                "roster_hints": [],
                "segments": [],
            }
            if source_user_id is not None:
                chunk["source_user_id"] = source_user_id
            if source_user_name:
                chunk["source_user_name"] = source_user_name
            if capture_mode:
                chunk["capture_mode"] = capture_mode
            self.chunk_manifest.append(chunk)
            await self.persist()
            return chunk

    async def update_chunk_result(
        self,
        chunk_index: int,
        *,
        status: str,
        notes: list[str] | None = None,
        roster_hints: list[dict] | None = None,
        segments: list[dict] | None = None,
        error: str | None = None,
    ) -> None:
        async with self.lock:
            chunk = self.get_chunk(chunk_index)
            if chunk is None:
                return
            chunk["status"] = status
            if notes is not None:
                chunk["notes"] = notes
            if roster_hints is not None:
                chunk["roster_hints"] = roster_hints
            if segments is not None:
                chunk["segments"] = segments
            if error:
                chunk["error"] = error
            await self.persist()

    def get_chunk(self, chunk_index: int) -> dict | None:
        return next((item for item in self.chunk_manifest if item["chunk_index"] == chunk_index), None)

    def sorted_chunks(self) -> list[dict]:
        return sorted(
            self.chunk_manifest,
            key=lambda item: (
                int(item.get("start_offset_seconds", 0)),
                int(item.get("chunk_index", 0)),
            ),
        )

    def pending_recorded_chunks(self) -> list[dict]:
        return [chunk for chunk in self.chunk_manifest if chunk.get("status") == "recorded"]

    def build_roster_context(self, *, before_chunk_index: int | None = None) -> str | None:
        lines: list[str] = []
        seen: set[tuple[str | None, str | None, str | None]] = set()
        for chunk in self.sorted_chunks():
            if before_chunk_index is not None and chunk["chunk_index"] >= before_chunk_index:
                continue
            for hint in chunk.get("roster_hints", []) or []:
                speaker = hint.get("speaker")
                character = hint.get("character")
                confidence = hint.get("confidence")
                key = (
                    speaker.strip() if isinstance(speaker, str) and speaker.strip() else None,
                    character.strip() if isinstance(character, str) and character.strip() else None,
                    confidence.strip().lower() if isinstance(confidence, str) and confidence.strip() else None,
                )
                if key in seen:
                    continue
                seen.add(key)

                details: list[str] = []
                if key[0]:
                    details.append(f"speaker={key[0]}")
                if key[1]:
                    details.append(f"character={key[1]}")
                if key[2]:
                    details.append(f"confidence={key[2]}")
                if details:
                    lines.append("- " + ", ".join(details))

        if not lines:
            return None
        return "Previously observed roster hints from earlier chunks:\n" + "\n".join(lines)

    async def clear_transcript_artifacts(self) -> None:
        try:
            self.transcript_path.write_text("", encoding="utf-8")
        except Exception:
            pass
        try:
            self.manifest_path.write_text("", encoding="utf-8")
        except Exception:
            pass

    def build_manifest_payload(self, *, window_summaries: list[dict] | None = None) -> dict:
        payload = {"chunks": self.chunk_manifest}
        if window_summaries is not None:
            payload["window_summaries"] = window_summaries
        return payload
