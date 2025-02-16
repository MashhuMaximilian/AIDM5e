import discord
import subprocess
import os
import aiohttp
import asyncio
import logging
from discord import app_commands
from config import WHISPER_API_URL, WHISPER_API_KEY
from assistant_interactions import get_assistant_response
from memory_management import get_assigned_memory
from pathlib import Path
from shared_functions import send_response_in_chunks, send_response


# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Create the folder to save audio files if it doesn't exist
audio_files_path = Path('audio_files')
audio_files_path.mkdir(exist_ok=True)

def get_category_id_voice(voice_channel):
    """Retrieve the category ID of the given voice channel."""
    if voice_channel and voice_channel.category:
        return voice_channel.category.id
    return None

class VoiceRecorder:
    def __init__(self):
        self.voice_client = None
        self.transcription_tasks = []  # Keep track of ongoing transcription tasks
        self.transcript_path = Path(__file__).parent / 'transcript.txt'  # Absolute path for transcript

    async def capture_audio(self, voice_client, duration=5): #120 seconds or 5-10 for testing.
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
                        
                        category_id = get_category_id_voice(self.voice_client.channel)
                        logging.info(f"Retrieved category ID: {category_id}")
                        # Call the summarize function
                        await self.summarize_transcript(category_id)

                        # Proceed to clean up files after summarization
                        await self.cleanup_files()
                        
                        # Leave the voice channel after everything is done
                        await self.voice_client.disconnect()  
                        logging.info("Disconnected from voice channel.")
                        break  # Exit the recording loop

                audio_filename = audio_files_path / f'audio_recording_{int(asyncio.get_event_loop().time())}.mp3'
                
                try:
                    logging.info(f"Recording for {duration} seconds... Saving to {audio_filename}")
                    proc = subprocess.Popen(
                        ['ffmpeg', '-f', 'avfoundation', '-i', ':0', '-t', str(duration), '-acodec', 'libmp3lame', '-ar', '44100', '-ac', '2','-b:a', '128k', str(audio_filename)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )

                    # Capture stderr (error messages)
                    stderr = await asyncio.to_thread(proc.stderr.read)
                    ffmpeg_error = stderr.decode('utf-8')
                    # logging.error(f"FFmpeg error: {ffmpeg_error}")

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
            with open(self.transcript_path, 'w', encoding='utf-8') as file:
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
                                logging.info(f"Received transcription from Whisper API: {transcription['text'][:100]}")

                                # Append transcription to transcript.txt
                                with open(self.transcript_path, 'a', encoding='utf-8') as transcript_file:
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


    async def summarize_transcript(self, category_id):
        logging.info("Starting transcript summarization...")

        # Ensure voice_client is connected and find the proper summary channel
        if not self.voice_client:
            logging.error("Voice client is not connected. Cannot summarize transcript.")
            return

        guild = self.voice_client.guild
        summary_channel = discord.utils.get(guild.text_channels, name='session-summary', category_id=category_id)
        if not summary_channel:
            logging.error(f"Could not find 'session-summary' channel in category {category_id}.")
            return

        # Fetch assigned memory (if needed for context)
        assigned_memory = await get_assigned_memory(summary_channel.id, category_id)
        if assigned_memory is None:
            logging.error("No assigned memory found for this channel.")
            return

        # Read and attach the full transcript file
        try:
            with open(self.transcript_path, 'r', encoding='utf-8') as transcript_file:
                transcript_content = transcript_file.read()
        except Exception as e:
            logging.error(f"Error reading transcript file: {e}")
            return

        logging.info("Transcript content loaded for summarization.")
        await summary_channel.send("Full transcript attached:", file=discord.File(self.transcript_path))

        if not transcript_content:
            logging.warning("Transcript is empty. No summary generated.")
            return

        # Split the transcript into chunks
        characters_per_chunk = 14000
        chunks = [
            transcript_content[i:i + characters_per_chunk]
            for i in range(0, len(transcript_content), characters_per_chunk)
        ]

        # Create a queue and enqueue all chunks
        chunk_queue = asyncio.Queue()
        for chunk in chunks:
            await chunk_queue.put(chunk)

        # Define a worker coroutine that processes each chunk sequentially
        async def process_chunks():
            while not chunk_queue.empty():
                chunk = await chunk_queue.get()

                # Determine the appropriate prompt based on whether this is the first chunk or a subsequent one.
                if chunk == chunks[0]:
                    prompt = (
                        "Make a comprehensive recap of the following file. It should be our entire session of gameplay. "
                        "Players may have used a single recording device and spoken in a jumble, so please include all key story elements, "
                        "player actions, combat encounters, NPC interactions, and notable dialogue. "
                        "Provide enough detail so the session can be resumed without confusion. "
                        "Highlight major decisions, challenges, and unresolved plot points. "
                        "If there were significant revelations or twists, please note them. "
                        "End by outlining what players should remember for the next session."
                        f"\n\n{chunk}"
                    )
                else:
                    prompt = (
                        "Please make a comprehensive recap of the following text in the same detailed manner as before. "
                        "This is a continuation of our D&D session transcript, which may include random conversations. "
                        "Capture all key events, player actions, combat encounters, NPC interactions, and notable dialogue. "
                        "Include character names, major decisions, challenges, and unresolved plot points. "
                        "Highlight any significant revelations or twists. "
                        "There will be more chunks to summarize."
                        f"\n\n{chunk}"
                    )

                # Get the assistant's summary response
                summary = await get_assistant_response(prompt, summary_channel.id, assigned_memory=assigned_memory)
                if "Error" in summary:
                    await summary_channel.send(summary)
                else:
                    await send_response_in_chunks(summary_channel, summary)

                # Mark this chunk as processed
                chunk_queue.task_done()

        # Process all chunks in order
        await process_chunks()
