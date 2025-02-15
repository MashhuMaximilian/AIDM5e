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
# import message_handlers
from memory_management import get_default_memory, set_default_memory, create_openai_thread
from helper_functions import handle_channel_creation
# from pyannote.audio import Pipeline
# from config import HUGGING_FACE_TOKEN



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

# async def create_threads_for_category(category_id):
#     user_message = "Starting a new thread for this category"  # Placeholder message for OpenAI threads
    
#     # Ensure category exists in the global data
#     if str(category_id) not in category_threads:
#         category_threads[str(category_id)] = {}

#     threads = category_threads[str(category_id)]

#     # Check if 'gameplay' thread exists, if not create it
#     if 'gameplay' not in threads:
#         threads['gameplay'] = await create_openai_thread(client.session, user_message, category_id, 'gameplay')
#         logging.info(f"New 'gameplay' thread created with ID: {threads['gameplay']} for category {category_id}")
    
#     # Check if 'out-of-game' thread exists, if not create it
#     if 'out-of-game' not in threads:
#         threads['out-of-game'] = await create_openai_thread(client.session, user_message, category_id, 'out-of-game')
#         logging.info(f"New 'out-of-game' thread created with ID: {threads['out-of-game']} for category {category_id}")

#     return threads

# async def handle_new_category(channel):
#     # Load existing thread data before checking for a new category
#     global category_threads
#     existing_data = load_thread_data()

#     # Merge existing data into the global category_threads
#     if existing_data:
#         category_threads.update(existing_data)

#     if str(channel.id) not in category_threads:
#         logging.info(f'New category created: {channel.id}. Adding to thread data.')
        
#         # Create threads for the new category
#         category_threads[str(channel.id)] = await create_threads_for_category(channel.id)

#         # Save the updated data
#         save_thread_data(category_threads)
#         logging.info(f'Thread data updated for new category {channel.id}.')

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

    # data_changed = False

    # # Loop through existing categories and set default memory
    # for category_id, threads in category_threads.items():
    #     logging.info("Processing existing category %s...", category_id)
        
    #     # Check and create threads if they don't exist
    #     new_threads = await create_threads_for_category(category_id)
    #     threads.update(new_threads)

    #     # Set default memory for the category
    #     await set_default_memory(category_id)

    #     data_changed = True

    # if data_changed:
    #     save_thread_data(category_threads)

    logging.info("Bot is ready and all categories have been processed.")

# # Preload the pipeline once
# diarization_pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization", use_auth_token=HUGGING_FACE_TOKEN)
# # # Assign the pipeline to your VoiceRecorder instance
# recorder.diarization_pipeline = diarization_pipeline
# logging.info("Diarization pipeline loaded and assigned to recorder.")

# Triggered when a new channel is created in the guild
# @client.event
# async def on_guild_channel_create(channel):
#     logging.info(f"New channel created with ID: {channel.id}, Type: {type(channel).__name__}")
#     if isinstance(channel, discord.CategoryChannel):
#         await handle_new_category(channel)
#     elif isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel):
#         category_id = str(channel.category_id).strip() if channel.category_id else None
#         channel_id = str(channel.id).strip()

#         # Make sure this part is working
#         if category_id and category_id in category_threads:
#             logging.info(f"Handling new channel creation: {channel_id}")
#             await handle_channel_creation("NEW CHANNEL", channel.name, channel.guild, channel.category, None)

# @client.event
# async def on_thread_create(thread):
#     logging.info(f"New thread created with ID: {thread.id}, parent channel ID: {thread.parent.id}")

#     if thread.parent is None:
#         logging.warning(f"Thread creation detected, but parent channel is None.")
#         return

#     parent_channel_id = str(thread.parent.id)
#     parent_category_id = str(thread.parent.category_id) if thread.parent.category_id else None

#     if parent_category_id in category_threads:
#         # Get the assigned memory for the parent category
#         assigned_memory = await get_default_memory(parent_category_id)

#         # Retrieve the corresponding memory name if exists
#         memory_name = None
#         if assigned_memory:
#             memory_name = next((name for name, mem_id in category_threads[parent_category_id]['memory_threads'].items() if mem_id == assigned_memory), None)

#         # Check if the parent channel exists
#         if parent_channel_id in category_threads[parent_category_id].get('channels', {}):
#             # Get the channel's threads
#             threads = category_threads[parent_category_id]['channels'][parent_channel_id].get('threads', {})

#             # Add the new thread to the threads dictionary
#             threads[str(thread.id)] = {
#                 'name': thread.name,
#                 'assigned_memory': assigned_memory,  # Assign the fetched memory ID
#                 'memory_name': memory_name            # Assign the fetched memory name
#             }

#             # Save the updated category_threads structure
#             with save_lock:
#                 save_thread_data(category_threads)
#             logging.info(f"New thread {thread.id} added to channel {parent_channel_id} with assigned memory and name, and saved.")
#         else:
#             logging.warning(f"Parent channel {parent_channel_id} not found in category {parent_category_id}.")
#     else:
#         logging.warning(f"Parent category {parent_category_id} not found in category_threads.")

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
