import asyncio
import logging
from pathlib import Path

from .audio_utils import build_ffmpeg_command


logger = logging.getLogger(__name__)


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
