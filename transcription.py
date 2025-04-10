import discord
import subprocess
import os
import aiohttp
import asyncio
import logging
from discord import app_commands
from config import OPENAI_API_KEY # Changed from WHISPER_API_KEY
from assistant_interactions import get_assistant_response
from memory_management import get_assigned_memory
from pathlib import Path
from shared_functions import send_response_in_chunks, send_response
import openai #Added

# CHANGE Recording duration TO | 550 | FOR REAL DEAL
recording_duration = 5
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

    async def capture_audio(self, voice_client, duration=recording_duration): #120 seconds or 5-10 for testing.
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
                        task = asyncio.create_task(self.send_to_openai(audio_filename)) #changed function name
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

    async def archive_transcript(self, content):
        """Append the transcript content to the archive with formatting."""
        archive_path = Path(__file__).parent / 'transcript_archive.txt'
        try:
            with open(archive_path, 'a', encoding='utf-8') as archive_file:  # <- This is the critical line
                # Write the separator and headers
                archive_file.write("\n\n\n")
                archive_file.write("_______________________________________________________________________\n")
                archive_file.write("\n\n")
                archive_file.write("SESSION TRANSCRIPTION\n")
                archive_file.write("_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _\n")
                archive_file.write("\n\n")
                # Write the content
                archive_file.write(content)
                # Add some spacing after the content
                archive_file.write("\n\n")
            logging.info("Transcript archived successfully.")
        except Exception as e:
            logging.error(f"Error archiving transcript: {e}")

    async def cleanup_files(self):
        """Cleanup transcript.txt and audio files."""
        logging.info("Cleaning up transcript and audio files...")
        category_id = get_category_id_voice(self.voice_client.channel)
        guild = self.voice_client.guild
        summary_channel = discord.utils.get(guild.text_channels, name='session-summary', category_id=category_id)
        if not summary_channel:
            logging.error(f"Could not find 'session-summary' channel in category {category_id}.")
            return

        # Read transcript content for archiving
        try:
            with open(self.transcript_path, 'r', encoding='utf-8') as f:
                transcript_content = f.read()
        except Exception as e:
            logging.error(f"Error reading transcript for archiving: {e}")
            transcript_content = ""

        # Archive the transcript
        await self.archive_transcript(transcript_content)

        await summary_channel.send("Full transcript attached:", file=discord.File(self.transcript_path))

        # Clear contents of transcript.txt
        try:
            with open(self.transcript_path, 'w', encoding='utf-8') as file:
                file.truncate(0)
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

    async def send_to_openai(self, audio_filename):
        """Send the recorded audio file to OpenAI GPT-4o API for transcription."""
        logging.info(f"Preparing to send {audio_filename} to OpenAI API for transcription (GPT-4o)...")
        
        if not audio_filename.exists() or audio_filename.stat().st_size == 0:
            logging.error(f"Audio file {audio_filename} does not exist or is empty.")
            return

        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        }

        try:
            async with aiohttp.ClientSession() as session:
                with open(audio_filename, "rb") as audio_file:
                    data = aiohttp.FormData()
                    data.add_field('file', audio_file, filename=audio_filename.name, content_type='audio/mpeg')
                    data.add_field('model', 'gpt-4o-transcribe')

                    async with session.post(url, headers=headers, data=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            transcript = result.get("text", "")
                            logging.info(f"Received transcription: {transcript[:100]}")

                            with open(self.transcript_path, 'a', encoding='utf-8') as transcript_file:
                                transcript_file.write(f"{transcript}\n")
                        else:
                            error_text = await response.text()
                            logging.error(f"API request failed: {response.status} - {error_text}")
        except Exception as e:
            logging.error(f"Unexpected error during OpenAI API request: {e}")


    async def summarize_transcript(self, category_id):
        logging.info("Starting transcript summarization...")

        if not self.voice_client:
            logging.error("Voice client is not connected. Cannot summarize transcript.")
            return

        guild = self.voice_client.guild
        summary_channel = discord.utils.get(guild.text_channels, name='session-summary', category_id=category_id)
        if not summary_channel:
            logging.error(f"Could not find 'session-summary' channel in category {category_id}.")
            return

        assigned_memory = await get_assigned_memory(summary_channel.id, category_id)
        if assigned_memory is None:
            logging.error("No assigned memory found for this channel.")
            return

        try:
            with open(self.transcript_path, 'r', encoding='utf-8') as transcript_file:
                transcript_content = transcript_file.read()
        except Exception as e:
            logging.error(f"Error reading transcript file: {e}")
            return

        logging.info("Transcript content loaded for summarization.")
        if not transcript_content:
            logging.warning("Transcript is empty. No summary generated.")
            return

        # Split transcript into chunks with overlap
        characters_per_chunk = 14000
        overlap = 150
        chunks = []
        start = 0
        while start < len(transcript_content):
            end = min(start + characters_per_chunk, len(transcript_content))
            chunk = transcript_content[max(0, start - overlap):end] if start > 0 else transcript_content[start:end]
            if len(chunk) >= 100:
                chunks.append(chunk)
            start = end

        # Process each chunk sequentially
        for i, chunk in enumerate(chunks):
            chapter_num = i + 1

            if i == 0:
                prompt = (
                    f"Great! We'll start a fresh session story retelling. The transcript you see is from another D&D session. "
                    f"Disregard any output you produced earlier for chapter numbering. Base your response solely on the transcript chunk and the following instructions. "
                    f"This is the first prompt only—do not include any session recap. And do not think of previous sessions. "
                    f"Do not consider any earlier retellings or chapter numbers—treat this chunk as a fresh continuation. "
                    f"Retell this D&D session’s start in a vivid third-person story, like telling a friend, staying 100% true to the transcript. "
                    f"Use in-game names and classes only, marking unclear names as [unknown, possibly character name]. "
                    f"Weave dialogue into the narration naturally (do not include direct quotes). "
                    f"Begin your response with 'Chapter 1: [Title from the Action]' and retell the following chunk:\n\n{f'''{chunk}'''}"
                )
            elif i < len(chunks) - 1:
                prompt = (
                    f"Continue the story from where you left off in Chapter {chapter_num - 1}. "
                    f"Do not consider any earlier retellings or chapter numbers—treat this chunk as a fresh continuation. (Only remember chapter number) "
                    f"Retell this next chunk of the D&D session in a vivid third-person narrative, sticking solely to the transcript events. "
                    f"Do not include a session recap yet. Use in-game names and mark unclear names as [unknown, possibly character name]. "
                    f"Begin your response with 'Chapter {chapter_num}: [Title from the Action]' and retell the following chunk:\n\n{f'''{chunk}'''}"
                )
            else:
                prompt = (
                    f"This is the final chunk of the transcript. Continue the story from where you left off in Chapter {chapter_num - 1}. "
                    f"Retell the concluding part of the D&D session in a vivid third-person story, accurately and exactly following the transcript. "
                    f"Do not provide a session recap in this response. Use in-game names and mark unclear names as [unknown, possibly character name]. "
                    f"Begin your response with 'Chapter {chapter_num}: [Ending Title]' and retell the following chunk:\n\n{f'''{chunk}'''}"
                )
            
            logging.debug(f"Generated prompt for chunk {chapter_num} (first 300 chars):\n{prompt[:300]}")

            try:
                # Await each assistant response before sending the next prompt.
                summary = await get_assistant_response(prompt, summary_channel.id, assigned_memory=assigned_memory)
                if "Error" in summary or "can't assist" in summary.lower():
                    logging.error(f"Chunk {chapter_num} failed: {summary}")
                    safe_summary = summary[:3800] + '...' if len(summary) > 3800 else summary
                    await summary_channel.send(f"Failed to summarize chunk {chapter_num}:\n\n{safe_summary}")

                else:
                    await send_response_in_chunks(summary_channel, summary)
                    logging.info(f"Chunk {chapter_num} retold successfully.")
            except Exception as e:
                logging.error(f"Error processing chunk {chapter_num}: {e}")
                await summary_channel.send(f"Error summarizing chunk {chapter_num}: {e}")

            # Optional: small delay to ensure the previous run is fully cleared.
            await asyncio.sleep(1)

        # Now, send the final summary prompt once all chunks have been processed.
        final_summary_prompt = (
            "Now that all parts of the session have been retold as a continuous story, please provide a full session recap. "
            "This recap should cover the entire session, including:\n"
            "- Key NPCs Met: [list names and brief descriptions]\n"
            "- Major Events: [bullet points of key plot developments]\n"
            "- Important Items: [notable loot/artifacts]\n"
            "- Unresolved Threads: [outstanding questions/mysteries]\n\n"
            "Please provide a final summary of the entire D&D session."
        )

        try:
            final_summary = await get_assistant_response(final_summary_prompt, summary_channel.id, assigned_memory=assigned_memory)
            if "Error" in final_summary or "can't assist" in final_summary.lower():
                logging.error(f"Final summary failed: {final_summary}")
                await summary_channel.send(f"Failed to generate final summary: {final_summary}")
            else:
                await send_response_in_chunks(summary_channel, final_summary)
                logging.info("Final session summary generated and sent successfully.")
        except Exception as e:
            logging.error(f"Error generating final session summary: {e}")
            await summary_channel.send(f"Error generating final session summary: {e}")

        logging.info("Transcript summarization completed.")