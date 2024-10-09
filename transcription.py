import discord
import shutil
import subprocess
import os
import aiohttp
import asyncio
import logging
from config import WHISPER_API_URL, WHISPER_API_KEY

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Create the folder to save audio files if it doesn't exist
if not os.path.exists('audio_files'):
    os.makedirs('audio_files')

class VoiceRecorder:
    def __init__(self):
        self.recording = False
        self.voice_client = None

    async def capture_audio(self, voice_client, duration=10):  # duration for listening and summarization
        """Record audio from the voice channel for `duration` seconds."""
        self.voice_client = voice_client
        audio_filename = f'audio_files/audio_recording_{int(asyncio.get_event_loop().time())}.wav'

        logging.info("Starting audio capture...")

        if self.voice_client and self.voice_client.is_connected():
            try:
                logging.info(f"Recording for {duration} seconds... Saving to {audio_filename}")
                # Update ffmpeg command
                # Start recording
                proc = subprocess.Popen(
                    ['ffmpeg', '-f', 'avfoundation', '-i', ':0', '-t', str(duration), audio_filename],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                await asyncio.sleep(duration)  # Wait for the duration to complete

                # Now safely terminate the process
                proc.terminate()

                logging.info(f"Audio recording completed and saved as {audio_filename}")
            except Exception as e:
                logging.error(f"Failed during audio recording: {e}")

            # Send audio to Whisper API for transcription
            await self.send_to_whisper(audio_filename)  # This call should now work
        else:
            logging.error("Voice client is not connected, cannot capture audio.")

    async def send_to_whisper(self, audio_filename):
        """Send the recorded audio file to Whisper for transcription."""
        logging.info(f"Preparing to send {audio_filename} to Whisper API for transcription...")

        # Check if the file exists and is not empty
        if not os.path.exists(audio_filename) or os.path.getsize(audio_filename) == 0:
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
                                data=form_data) as response:
                            if response.status == 200:
                                transcription = await response.json()
                                logging.info(f"Received transcription from Whisper API: {transcription['text']}")
                                self.process_transcription(transcription)
                                break  # Exit the loop if successful
                            else:
                                error_msg = await response.text()
                                logging.error(f"Whisper API returned error {response.status}: {error_msg}")
                                await asyncio.sleep(1)  # Wait before retrying
                except aiohttp.ClientError as e:
                    logging.error(f"Failed to connect to Whisper API: {e}")
                except Exception as e:
                    logging.error(f"Unexpected error during Whisper API request: {e}")

    def delete_audio_files(self):
        """Delete all audio files in the audio_files directory."""
        try:
            shutil.rmtree('audio_files')
            os.makedirs('audio_files')  # Recreate the directory
            logging.info("All audio files deleted successfully.")
        except Exception as e:
            logging.error(f"Failed to delete audio files: {e}")

    def process_transcription(self, transcription):
        """Process and save the transcription with timestamps."""
        try:
            text = transcription.get('text', '')
            words = transcription.get('words', [])
            with open('transcript.txt', 'a') as f:  # Open the file in append mode
                f.write(text + '\n')
                for word_info in words:
                    word = word_info.get('word')
                    start_time = word_info.get('start')
                    end_time = word_info.get('end')
                    f.write(f"{word} ({start_time:.2f}s - {end_time:.2f}s)\n")  # Save words with timestamps
            logging.info(f"Transcription successfully saved to transcript.txt")
            
            # Call the method to delete audio files after successful transcription
            self.delete_audio_files()
        except Exception as e:
            logging.error(f"Failed to save transcription: {e}")

