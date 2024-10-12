import discord
import subprocess
import os
import aiohttp
import asyncio
import logging
from config import WHISPER_API_URL, WHISPER_API_KEY
from assistant_interactions import get_assistant_response, create_or_get_thread
from pathlib import Path
from message_handlers import send_response_in_chunks

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Create the folder to save audio files if it doesn't exist
audio_files_path = Path('audio_files')
audio_files_path.mkdir(exist_ok=True)

class VoiceRecorder:
    def __init__(self):
        self.voice_client = None
        self.transcription_tasks = []  # Keep track of ongoing transcription tasks


    async def capture_audio(self, voice_client, duration=15):
        self.voice_client = voice_client
        logging.info("Starting continuous audio capture...")

        while True:
            if self.voice_client and self.voice_client.is_connected():
                members_count = len(self.voice_client.channel.members)
                logging.info(f"Current members in voice channel: {members_count}")

                if members_count <= 1:  # Check if only the bot is left
                    logging.info("No members left in the voice channel. Preparing to finalize recording...")
                    await asyncio.sleep(5)  # Wait for a minute to see if anyone rejoins
                    if len(self.voice_client.channel.members) == 1:  # Confirm no one has joined
                        logging.info("No members have joined within the timeout period. Proceeding to finalize...")

                        # Wait for all transcription tasks to complete
                        if self.transcription_tasks:
                            await asyncio.gather(*self.transcription_tasks)
                        
                        # Call the summarize function
                        await self.summarize_transcript()

                        # Proceed to clean up files after summarization
                        await self.cleanup_files()
                        
                        # Leave the voice channel after everything is done
                        await self.voice_client.disconnect()  
                        logging.info("Disconnected from voice channel.")
                        break  # Exit the recording loop

                audio_filename = audio_files_path / f'audio_recording_{int(asyncio.get_event_loop().time())}.wav'
                try:
                    logging.info(f"Recording for {duration} seconds... Saving to {audio_filename}")
                    proc = subprocess.Popen(
                        ['ffmpeg', '-f', 'avfoundation', '-i', ':0', '-t', str(duration), str(audio_filename)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    await asyncio.sleep(duration)
                    proc.terminate()
                    logging.info(f"Audio recording completed and saved as {audio_filename}")

                    if audio_filename.exists() and audio_filename.stat().st_size > 0:
                        # Send the audio file for transcription as a background task
                        task = asyncio.create_task(self.send_to_whisper(audio_filename))
                        self.transcription_tasks.append(task)  # Track the task
                        task.add_done_callback(lambda t: self.transcription_tasks.remove(t))  # Remove task after completion
                    else:
                        logging.error(f"Audio file {audio_filename} does not exist or is empty after recording.")
                except Exception as e:
                    logging.error(f"Failed during audio recording: {e}")
                    break

                await asyncio.sleep(0.2)
            else:
                logging.info("Voice client not connected. Exiting recording loop.")
                break

    async def process_final_transcription(self):
        logging.info("Processing remaining audio files for transcription...")

        # Get list of remaining audio files
        remaining_audio_files = [file for file in self.audio_dir.iterdir() if file.suffix == ".wav"]

        # Process each remaining audio file once
        for audio_file in remaining_audio_files:
            logging.info(f"Transcribing file: {audio_file.name}")
            await self.transcribe_audio_file(audio_file)  # Make sure this function handles transcription

        logging.info("Final transcription processing completed.")


    async def cleanup_files(self):
        """Cleanup transcript.txt and audio files."""
        logging.info("Cleaning up transcript and audio files...")

        # Clear contents of transcript.txt
        try:
            with open('transcript.txt', 'w', encoding='utf-8') as file:
                file.truncate(0)  # Clear the file
            logging.info("Transcript file cleared.")
        except Exception as e:
            logging.error(f"Error clearing transcript file: {e}")

        # Remove all audio files
        for filename in os.listdir(audio_files_path):
            file_path = audio_files_path / filename
            try:
                os.remove(file_path)
                logging.info(f"Deleted audio file: {file_path}")
            except Exception as e:
                logging.error(f"Failed to delete audio file {file_path}: {e}")

    async def send_to_whisper(self, audio_filename):
        """Send the recorded audio file to Whisper for transcription."""
        logging.info(f"Preparing to send {audio_filename} to Whisper API for transcription...")

        if not audio_filename.exists() or audio_filename.stat().st_size == 0:
            logging.error(f"Audio file {audio_filename} does not exist or is empty.")
            return

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            for attempt in range(3):  # Retry up to 3 times
                try:
                    await asyncio.sleep(1)  # Small delay before sending
                    with open(audio_filename, 'rb') as audio_file:
                        form_data = aiohttp.FormData()
                        form_data.add_field('file', audio_file, content_type='audio/wav')
                        form_data.add_field('model', 'whisper-1')

                        logging.info(f"Sending {audio_filename} to Whisper API...")
                        async with session.post(
                            WHISPER_API_URL,
                            headers={'Authorization': f'Bearer {WHISPER_API_KEY}'},
                            data=form_data
                        ) as response:
                            if response.status == 200:
                                transcription = await response.json()
                                logging.info(f"Received transcription from Whisper API: {transcription['text']}")

                                # Append transcription to transcript.txt
                                with open('transcript.txt', 'a', encoding='utf-8') as transcript_file:
                                    transcript_file.write(f"{transcription['text']}\n")
                                break  # Exit the loop if successful
                            else:
                                error_msg = await response.text()
                                logging.error(f"Whisper API returned error {response.status}: {error_msg}")
                                await asyncio.sleep(1)  # Delay before retry
                except aiohttp.ClientError as e:
                    logging.error(f"Failed to connect to Whisper API: {e}")
                except Exception as e:
                    logging.error(f"Unexpected error during Whisper API request: {e}")

    async def summarize_transcript(self):
        """Summarize the contents of transcript.txt and send it to the session-summary channel."""
        logging.info("Starting transcript summarization...")

        # Ensure that self.voice_client is not None
        if not self.voice_client:
            logging.error("Voice client is not connected. Cannot summarize transcript.")
            return

        # Get the current category ID for the voice channel
        channel = self.voice_client.channel
        category_id = channel.category.id if channel.category else None

        if category_id is not None:
            summary_channel = discord.utils.get(channel.guild.text_channels, name='session-summary', category__id=category_id)
            if summary_channel is None:
                summary_channel = await channel.guild.create_text_channel('session-summary', category=channel.category)
                logging.info("Created new 'session-summary' channel.")

            try:
                with open('transcript.txt', 'r', encoding='utf-8') as transcript_file:
                    transcript_content = transcript_file.read()
                    logging.info("Transcript content loaded for summarization.")

                # Send the transcript to the assistant for summarization
                if transcript_content:
                    # Ensure to pass the required channel_id for summarization
                    await get_assistant_response(summary_channel.id, transcript_content)  # Use the correct call for summarization
                else:
                    logging.warning("Transcript is empty. No summary generated.")

            except Exception as e:
                logging.error(f"Error reading transcript file or sending summary: {e}")
