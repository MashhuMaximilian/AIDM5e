#aidm.py

import logging
import bot_commands
from pathlib import Path
from config import *
from assistant_interactions import get_assistant_response
import transcription  
import discord
import aiohttp
from helper_functions import create_openai_thread
from pathlib import Path
from helper_functions import load_thread_data, save_thread_data
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

file_path = Path(__file__).parent.resolve() / 'aidm_prompt.txt'
try:
    with open(file_path, 'r') as f:
        system_prompt = f.read()
except FileNotFoundError:
    raise FileNotFoundError(f"Could not find the file: {file_path}")

# Create a single instance of VoiceRecorder
recorder = transcription.VoiceRecorder()

# Global variable for category threads
category_threads = {}

def get_all_categories():
    return [category.id for category in client.guilds[0].categories]  # Adjust if your bot is in multiple guilds

async def create_threads_for_category(category_id):
    user_message = "Starting a new thread for this category"  # Placeholder message for OpenAI threads
    threads = {}
    
    # Create 'gameplay' thread
    threads['gameplay'] = await create_openai_thread(client.session, user_message, category_id, 'gameplay')
    logging.info(f"New 'gameplay' thread created with ID: {threads['gameplay']} for category {category_id}")

    # Create 'out-of-game' thread
    threads['out-of-game'] = await create_openai_thread(client.session, user_message, category_id, 'out-of-game')
    logging.info(f"New 'out-of-game' thread created with ID: {threads['out-of-game']} for category {category_id}")

    return threads

async def handle_new_category(channel):
    # Load existing thread data before checking for a new category
    global category_threads
    category_threads = load_thread_data()

    if str(channel.id) not in category_threads:
        logging.info(f'New category created: {channel.id}. Adding to thread data.')
        category_threads[str(channel.id)] = await create_threads_for_category(channel.id)

        # Save the updated data
        save_thread_data(category_threads)
        logging.info(f'Thread data updated for new category {channel.id}.')

@client.event
async def on_ready():
    logging.info(f'Bot has logged in as {client.user}')

    client.session = aiohttp.ClientSession()
    
    try:
        await tree.sync()
        logging.info("Slash commands have been successfully synced.")
    except Exception as e:
        logging.error(f"Error syncing commands: {e}")

    global category_threads
    category_threads = load_thread_data()
    
    data_changed = False

    for category_id, threads in category_threads.items():
        logging.info("Processing existing category %s...", category_id)
        
        # Check and create threads if they don't exist
        if 'gameplay' not in threads or 'out-of-game' not in threads:
            new_threads = await create_threads_for_category(category_id)
            threads.update(new_threads)
            data_changed = True

    if data_changed:
        save_thread_data(category_threads)

@client.event
async def on_guild_channel_create(channel):
    if isinstance(channel, discord.CategoryChannel):
        await handle_new_category(channel)

@client.event
async def on_guild_channel_delete(channel):
    if isinstance(channel, discord.CategoryChannel):
        category_id = str(channel.id).strip()
        logging.info(f"Channel deleted: {category_id}")

        if category_id in category_threads:
            logging.info(f"Category {category_id} found. Removing from thread data.")
            del category_threads[category_id]
            save_thread_data(category_threads)
            logging.info(f"Thread data updated. Category {category_id} removed.")
        else:
            logging.warning(f"Deleted category {category_id} not found in thread data.")

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
