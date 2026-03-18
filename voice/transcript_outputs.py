import logging
import os
from pathlib import Path

import discord

from config import KEEP_AUDIO_FILES, KEEP_TRANSCRIPT_FILES


logger = logging.getLogger(__name__)


class TranscriptOutputService:
    def __init__(self, transcript_path: Path, manifest_path: Path, audio_files_path: Path) -> None:
        self.transcript_path = transcript_path
        self.manifest_path = manifest_path
        self.audio_files_path = audio_files_path
        self.archive_path = transcript_path.parent / "transcript_archive.txt"

    async def archive_transcript(self, content: str) -> None:
        try:
            with open(self.archive_path, "a", encoding="utf-8") as archive_file:
                archive_file.write("\n\n\n")
                archive_file.write("_______________________________________________________________________\n")
                archive_file.write("\n\n")
                archive_file.write("SESSION TRANSCRIPTION\n")
                archive_file.write("_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _\n")
                archive_file.write("\n\n")
                archive_file.write(content)
                archive_file.write("\n\n")
            logger.info("Transcript archived successfully.")
        except Exception as exc:
            logger.error("Error archiving transcript: %s", exc)

    async def post_transcript_to_channel(self, summary_channel) -> None:
        await summary_channel.send("Full transcript attached:", file=discord.File(self.transcript_path))

    async def cleanup_live_artifacts(self, voice_client, reset_callback) -> None:
        logger.info("Cleaning up transcript and audio files...")

        try:
            transcript_content = self.transcript_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error("Error reading transcript for archiving: %s", exc)
            transcript_content = ""

        await self.archive_transcript(transcript_content)

        if KEEP_AUDIO_FILES:
            logger.info("KEEP_AUDIO_FILES=true, leaving recorded audio files in place.")
        else:
            for filename in os.listdir(self.audio_files_path):
                file_path = self.audio_files_path / filename
                try:
                    os.remove(file_path)
                    logger.info("Deleted audio file: %s", file_path)
                except Exception as exc:
                    logger.error("Failed to delete audio file %s: %s", file_path, exc)

        if KEEP_TRANSCRIPT_FILES:
            logger.info("KEEP_TRANSCRIPT_FILES=true, leaving transcript artifacts in place.")
        else:
            await reset_callback()
            logger.info("Transcript artifacts cleared.")

    def cleanup_offline_segments(self, segment_output_root: Path) -> None:
        if segment_output_root.exists() and not KEEP_AUDIO_FILES:
            for segment_file in sorted(segment_output_root.rglob("*"), reverse=True):
                try:
                    if segment_file.is_file():
                        segment_file.unlink()
                    else:
                        segment_file.rmdir()
                except OSError:
                    pass
