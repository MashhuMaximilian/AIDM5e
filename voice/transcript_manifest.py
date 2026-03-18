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

    async def register_external_chunk(self, audio_filename: Path, duration: int, start_offset_seconds: int) -> dict:
        async with self.lock:
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
            await self.persist()
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
        async with self.lock:
            chunk = self.get_chunk(chunk_index)
            if chunk is None:
                return
            chunk["status"] = status
            if notes is not None:
                chunk["notes"] = notes
            if segments is not None:
                chunk["segments"] = segments
            if error:
                chunk["error"] = error
            await self.persist()

    def get_chunk(self, chunk_index: int) -> dict | None:
        return next((item for item in self.chunk_manifest if item["chunk_index"] == chunk_index), None)

    def sorted_chunks(self) -> list[dict]:
        return sorted(self.chunk_manifest, key=lambda item: item["chunk_index"])

    def pending_recorded_chunks(self) -> list[dict]:
        return [chunk for chunk in self.chunk_manifest if chunk.get("status") == "recorded"]

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
