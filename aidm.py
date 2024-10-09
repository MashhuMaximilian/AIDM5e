# aidm.py
import logging
import bot_commands
from pathlib import Path
from config import DISCORD_BOT_TOKEN, ASSISTANT_ID, client, tree, HEADERS, category_threads, category_conversations, channel_character_sheets
from message_handlers import on_message, send_response_in_chunks
from assistant_interactions import get_assistant_response
import transcription  
import discord

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

file_path = Path(__file__).parent.resolve() / 'aidm_prompt.txt'
try:
    with open(file_path, 'r') as f:
        system_prompt = f.read()
except FileNotFoundError:
    raise FileNotFoundError(f"Could not find the file: {file_path}")

@client.event
async def on_ready():
    logging.info(f'Bot has logged in as {client.user}')
    try:
        await tree.sync()
        logging.info("Slash commands have been successfully synced.")
    except Exception as e:
        logging.error(f"Error syncing commands: {e}")

# Automatically join and leave voice channels
@client.event
async def on_voice_state_update(member, before, after):
    # Check if a user has joined a voice channel
    if after.channel and member.id != client.user.id:  # Avoid responding to the bot itself
        # Check if the bot is not already connected to a voice channel
        if not any(vc.channel.id == after.channel.id for vc in client.voice_clients): 
            try:
                voice_client = await after.channel.connect()  # Join the voice channel
                logging.info(f"Bot has joined the voice channel: {after.channel.name}")
                recorder = transcription.VoiceRecorder()  # Create a recorder instance
                await recorder.capture_audio(voice_client)  # Start capturing audio
            except discord.ClientException:
                logging.info(f"Already connected to {after.channel.name}")

    # Check if a user has left a voice channel
    elif before.channel and len(before.channel.members) == 1 and before.channel.members[0].id == client.user.id:
        # If the bot is the only one left, summarize and then disconnect
        voice_client = discord.utils.get(client.voice_clients, channel=before.channel)
        if voice_client:
            logging.info(f"Summarizing transcript before leaving the voice channel {before.channel.name}...")
            
            # Summarize transcript before disconnecting
            recorder = transcription.VoiceRecorder()
            await recorder.summarize_transcript(before.channel.id)
            
            await voice_client.disconnect()  # Leave the voice channel
            logging.info(f"Bot has left the voice channel: {before.channel.name}")

# Run the bot
def run_bot():
    client.run(DISCORD_BOT_TOKEN)

if __name__ == '__main__':
    run_bot()
