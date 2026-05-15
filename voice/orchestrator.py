import asyncio
import logging

from .audio_utils import get_category_id_voice


logger = logging.getLogger(__name__)


class VoiceSessionOrchestrator:
    async def finalize_voice_session(self, recorder) -> None:
        if recorder.transcription_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*recorder.transcription_tasks, return_exceptions=True),
                    timeout=300.0,
                )
            except asyncio.TimeoutError:
                logger.warning("Transcription tasks timed out after 300s, proceeding with finalization")

        category_id = get_category_id_voice(recorder.voice_client.channel)
        logger.info("Retrieved category ID: %s", category_id)
        await recorder.rebuild_transcript_from_manifest()
        await recorder.summarize_transcript(category_id)
        await recorder.cleanup_files()
        await recorder.voice_client.disconnect()
        logger.info("Disconnected from voice channel.")
