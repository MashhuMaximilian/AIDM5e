#aidm.py

import logging
import bot_commands
from pathlib import Path
from config import client, tree, DISCORD_BOT_TOKEN
from assistant_interactions import get_assistant_response
import transcription  
import discord
import aiohttp
from pathlib import Path
from utils import save_thread_data, load_thread_data
import json
from threading import Lock
import message_handlers
from message_handlers import on_message
from memory_management import get_default_memory, set_default_memory, create_openai_thread
from helper_functions import handle_channel_creation

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

file_path = Path(__file__).parent.resolve() / 'aidm_prompt.txt'
try:
    with open(file_path, 'r') as f:
        system_prompt = f.read()
except FileNotFoundError:
    raise FileNotFoundError(f"Could not find the file: {file_path}")

# # Create a single instance of VoiceRecorder
recorder = transcription.VoiceRecorder()



# Global variable for category threads
category_threads = {}

def get_all_categories():
    return [category.id for category in client.guilds[0].categories]  # Adjust if your bot is in multiple guilds


@client.event
async def on_ready():
    logging.info(f'Bot has logged in as {client.user}')
    await client.change_presence(status=discord.Status.online, activity=discord.Game("Bot is ready"))

    client.session = aiohttp.ClientSession()
    
    try:
        await tree.sync()
        logging.info("Slash commands have been successfully synced.")
    except Exception as e:
        logging.error(f"Error syncing commands: {e}")

    # Load existing thread data
    global category_threads
    category_threads = load_thread_data()
    client.event(on_message)


    logging.info("Bot is ready and all categories have been processed.")


save_lock = Lock()  # Lock to ensure single access to JSON save function

@client.event
async def on_thread_delete(thread):
    if thread.parent is None:
        logging.warning(f"Thread deletion detected for thread ID: {thread.id}, but parent channel is None.")
        return

    logging.info(f"Thread deletion detected for thread ID: {thread.id}, parent channel ID: {thread.parent.id}")

    parent_channel_id = str(thread.parent.id)
    parent_category_id = str(thread.parent.category_id) if thread.parent.category_id else None

    # Log only the first 100 characters of the current category_threads structure
    logging.info(f"Current category_threads structure: {json.dumps(category_threads)[:100]}")

    # Check if the parent category exists
    if parent_category_id in category_threads:
        # Check if the parent channel exists
        if parent_channel_id in category_threads[parent_category_id].get('channels', {}):
            # Access the threads in that specific channel
            threads = category_threads[parent_category_id]['channels'][parent_channel_id].get('threads', {})

            # Check if the thread ID exists in the threads dictionary
            if str(thread.id) in threads:
                logging.info(f"Deleting Thread with ID: {thread.id}")
                del threads[str(thread.id)]  # Delete the specific thread entry

                # Save the updated category_threads structure
                with save_lock:
                    save_thread_data(category_threads)
                logging.info(f"Thread {thread.id} removed from JSON and saved.")
            else:
                logging.warning(f"Thread {thread.id} not found in channel {parent_channel_id} under category {parent_category_id}.")
        else:
            logging.warning(f"Parent channel {parent_channel_id} not found in category {parent_category_id}.")
    else:
        logging.warning(f"Parent category {parent_category_id} not found in category_threads.")


@client.event
async def on_guild_channel_delete(channel):
    logging.info(f"Channel deletion detected for channel ID: {channel.id}, Type: {type(channel).__name__}")

    if isinstance(channel, discord.CategoryChannel):
        category_id = str(channel.id).strip()
        logging.info(f"Detected CategoryChannel deletion with ID: {category_id}")

        if category_id in category_threads:
            logging.info(f"Deleted a CategoryChannel with ID: {category_id}")
            del category_threads[category_id]

            with save_lock:
                save_thread_data(category_threads)
            logging.info(f"Category {category_id} removed from JSON and saved.")

    elif isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
        category_id = str(channel.category_id).strip() if channel.category_id else None
        channel_id = str(channel.id).strip()

        logging.info(f"Detected TextChannel/VoiceChannel deletion with ID: {channel_id}, in category: {category_id}")

        if category_id and category_id in category_threads:
            if channel_id in category_threads[category_id].get('channels', {}):
                logging.info(f"Deleted a TextChannel/VoiceChannel with ID: {channel_id}")
                del category_threads[category_id]['channels'][channel_id]

                with save_lock:
                    save_thread_data(category_threads)
                logging.info(f"Channel {channel_id} removed from JSON and saved.")

    logging.info(f"Finished processing deletion for channel ID: {channel.id}")

# Automatically join and leave voice channels
@client.event
async def on_voice_state_update(member, before, after):
    # Check if a user has joined a voice channel
    if after.channel and member.id != client.user.id: 
        if not any(vc.channel.id == after.channel.id for vc in client.voice_clients): 
            try:
                voice_client = await after.channel.connect()
                logging.info(f"Bot has joined the voice channel: {after.channel.name}")
                await recorder.capture_audio(voice_client)
            except discord.ClientException:
                logging.info(f"Already connected to {after.channel.name}")

    # Check if a user has left a voice channel
    elif before.channel and len(before.channel.members) == 1 and before.channel.members[0].id == client.user.id:
        voice_client = discord.utils.get(client.voice_clients, channel=before.channel)
        if voice_client:
            logging.info(f"Bot is the last member in the voice channel: {before.channel.name}.")

bot_commands.setup_commands(tree, get_assistant_response)

@client.event
async def on_close():
    await client.session.close()

def run_bot():
    client.run(DISCORD_BOT_TOKEN)

if __name__ == '__main__':
    run_bot()
