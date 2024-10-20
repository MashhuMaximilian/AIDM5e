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


def get_all_categories():
    return [category.id for category in client.guilds[0].categories]  # Adjust if your bot is in multiple guilds



@client.event
async def on_ready():
    logging.info(f'Bot has logged in as {client.user}')

    # Create an aiohttp session here
    client.session = aiohttp.ClientSession()

    try:
        await tree.sync()
        logging.info("Slash commands have been successfully synced.")
    except Exception as e:
        logging.error(f"Error syncing commands: {e}")

    # Load the initial data
    global category_threads
    category_threads = load_thread_data()

    data_changed = False  # Flag to track if any data is changed

    # Only process categories that are already in threads.json
    for category_id, threads in category_threads.items():
        logging.info("Processing existing category %s...", category_id)

        # Check if 'gameplay' thread already exists
        if 'gameplay' not in threads:
            logging.info("Creating new OpenAI thread for category %s of type gameplay", category_id)
            gameplay_thread_id = await create_openai_thread(client.session, category_id, 'gameplay')
            threads['gameplay'] = gameplay_thread_id
            logging.info("New 'gameplay' thread created with ID: %s for category %s", gameplay_thread_id, category_id)
            data_changed = True

        # Check if 'out-of-game' thread already exists
        if 'out-of-game' not in threads:
            logging.info("Creating new OpenAI thread for category %s of type out-of-game", category_id)
            out_of_game_thread_id = await create_openai_thread(client.session, category_id, 'out-of-game')
            threads['out-of-game'] = out_of_game_thread_id
            logging.info("New 'out-of-game' thread created with ID: %s for category %s", out_of_game_thread_id, category_id)
            data_changed = True

    # Save only if there were changes
    if data_changed:
        save_thread_data(category_threads)


@client.event
async def on_guild_channel_create(channel):
    if isinstance(channel, discord.CategoryChannel):
        if str(channel.id) not in category_threads:
            logging.info(f'New category created: {channel.id}. Adding to thread data.')

            # Initialize category entry
            category_threads[str(channel.id)] = {}

            user_message = "Starting a new thread for this category"  # Placeholder message for OpenAI threads

            # Create 'gameplay' thread
            gameplay_thread_id = await create_openai_thread(client.session, user_message, channel.id, 'gameplay')
            category_threads[str(channel.id)]['gameplay'] = gameplay_thread_id
            logging.info(f"New 'gameplay' thread created with ID: {gameplay_thread_id} for category {channel.id}")

            # Create 'out-of-game' thread
            out_of_game_thread_id = await create_openai_thread(client.session, user_message, channel.id, 'out-of-game')
            category_threads[str(channel.id)]['out-of-game'] = out_of_game_thread_id
            logging.info(f"New 'out-of-game' thread created with ID: {out_of_game_thread_id} for category {channel.id}")

            # Save the updated data
            save_thread_data(category_threads)
            logging.info(f'Thread data updated for new category {channel.id}.')


# Load the initial data
category_threads = load_thread_data()


@client.event
async def on_guild_channel_delete(channel):
    if isinstance(channel, discord.CategoryChannel):
        category_id = str(channel.id).strip()  # Ensure the ID is a string

        # Log the channel deletion event
        logging.info(f"Channel deleted: {category_id} - Type: {type(channel)}")

        # Debugging: Log the current thread data
        logging.debug(f"Current thread data before deletion: {category_threads}")

        # Check if the deleted category exists in the thread data
        if category_id in category_threads:
            logging.info(f"Category {category_id} found. Removing from thread data.")

            # Remove the category and its associated threads from the thread data
            del category_threads[category_id]

            # Log the state after deletion
            logging.debug(f"State after deletion: {category_threads}")

            # Save the updated data
            save_thread_data(category_threads)

            # Log successful save confirmation
            logging.info(f"Thread data updated. Category {category_id} removed.")
        else:
            logging.warning(f"Deleted category {category_id} not found in thread data.")



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
                await recorder.capture_audio(voice_client)  # Start capturing audio
            except discord.ClientException:
                logging.info(f"Already connected to {after.channel.name}")

    # Check if a user has left a voice channel
    elif before.channel and len(before.channel.members) == 1 and before.channel.members[0].id == client.user.id:
        # If the bot is the only one left, let capture_audio handle the summarization and disconnect
        voice_client = discord.utils.get(client.voice_clients, channel=before.channel)
        if voice_client:
            logging.info(f"Bot is the last member in the voice channel: {before.channel.name}.")
            # No need to summarize here; it will be handled in capture_audio.

bot_commands.setup_commands(tree, get_assistant_response)

@client.event
async def on_close():
    await client.session.close()

# Run the bot
def run_bot():
    client.run(DISCORD_BOT_TOKEN)

if __name__ == '__main__':
    run_bot()
