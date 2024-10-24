# helper_funtions

import discord
from discord import app_commands
from message_handlers import send_response_in_chunks
import json
from assistant_interactions import create_or_get_thread, get_assistant_response
from config import HEADERS, client
import aiohttp
import logging
from pathlib import Path
import os


# Dictionary to store thread IDs for the #telldm channel
category_threads = {}
category_conversations = {}




async def create_openai_thread(session, user_message, category_id, memory_name):
    """Create a new OpenAI thread and store its ID for the category."""
    logging.info(f"Creating new OpenAI thread for category {category_id} of type {memory_name}")
    
    async with session.post("https://api.openai.com/v1/threads", headers=HEADERS, json={
        "messages": [{"role": "user", "content": user_message}]
    }) as thread_response:
        if thread_response.status != 200:
            raise Exception(f"Error creating thread: {await thread_response.text()}")
        
        thread_data = await thread_response.json()
        thread_id = thread_data['id']
        
        # Store thread ID in the category-specific structure
        if category_id not in category_threads:
            category_threads[category_id] = {}

        # Store the thread under the appropriate thread type
        category_threads[category_id][memory_name] = thread_id
        logging.info(f"New OpenAI thread created for category {category_id} with thread ID: {thread_id} of type {memory_name}")
    
    return thread_id

async def send_to_telldm(interaction, response, category_id, memory_name):
    # Ensure you have a session created for API calls
    async with aiohttp.ClientSession() as session:
        # Get the thread ID by creating a new OpenAI thread with the specified memory
        thread_id = await create_openai_thread(session, response, category_id, memory_name)

        # Now send the message to the telldm channel
        telldm_channel = discord.utils.get(interaction.guild.channels, name='telldm')  # Find the #telldm channel
        if telldm_channel:
            await telldm_channel.send(f"New thread created with ID: {thread_id}")  # You can customize this message
        else:
            logging.error("Channel #telldm not found.")

async def fetch_discord_threads(channel):
    """Fetches all available threads in a given channel."""
    discord_threads = []
    # Check for threads in the specified channel
    for thread in channel.threads:
        discord_threads.append(thread)
    return discord_threads

# Function to summarize the conversation
async def summarize_conversation(interaction, conversation_history, options, query):
    if options['type'] == 'messages':
        history = "\n".join(conversation_history)
    elif options['type'] == 'from':
        start_index = options['start_index']
        history = "\n".join(conversation_history[start_index:])
    elif options['type'] == 'between':
        start_index, end_index = options['start_index'], options['end_index']
        history = "\n".join(conversation_history[start_index:end_index])
    else:
        logging.error("Invalid options for summarization.")
        return "Invalid options for summarization."

    prompt = (f"Summarize the following conversation history or messages. Only focus on essential information."
              f"Here is the conversation history:\n\n{history}"
              f"Here are other requests I want about the summary:\n\n{query}"
              )
    
    response = await get_assistant_response(prompt, interaction.channel.id)
    return response

async def fetch_conversation_history(channel, start=None, end=None, message_ids=None):
    # Initialize an empty list to store the conversation history
    conversation_history = []

    if message_ids is not None:
        message_ids_list = message_ids.split(',')
        for message_id in message_ids_list:
            try:
                message = await channel.fetch_message(int(message_id.strip()))
                conversation_history.append(f"{message.author.name}: {message.content}")
            except (ValueError, discord.errors.NotFound):
                return None, f"Message ID {message_id.strip()} not found."
        return conversation_history, {'type': 'messages'}

    # Handle 'from' option
    if start is not None and end is not None:
        try:
            start_id = int(start)
            end_id = int(end)
            start_message = await channel.fetch_message(start_id)
            end_message = await channel.fetch_message(end_id)
        except (ValueError, discord.errors.NotFound):
            return None, "Invalid message ID format or message not found."

        # Fetch messages including the start and end messages
        async for message in channel.history(after=start_message.created_at, before=end_message.created_at):
            conversation_history.append(f"{message.author.name}: {message.content}")

        # Add start message explicitly
        conversation_history.insert(0, f"{start_message.author.name}: {start_message.content}")
        
        # Add end message explicitly if it's different from start
        if start_id != end_id:
            conversation_history.append(f"{end_message.author.name}: {end_message.content}")

        if not conversation_history:
            return None, "No messages found between the specified messages."

        return conversation_history, {'type': 'between', 'start_index': 0, 'end_index': len(conversation_history)}

    # Handle 'from' option only
    if start is not None:
        try:
            start_id = int(start)
            start_message = await channel.fetch_message(start_id)
        except (ValueError, discord.errors.NotFound):
            return None, "Invalid start message ID format or message not found."

        async for message in channel.history(after=start_message.created_at, limit=100):
            conversation_history.append(f"{message.author.name}: {message.content}")

        # Add the start message explicitly
        conversation_history.insert(0, f"{start_message.author.name}: {start_message.content}")

        if not conversation_history:
            return None, "No messages found after the specified message."

        return conversation_history, {'type': 'from', 'start_index': 0}

    # Error if no valid options provided
    return None, "You must provide at least one of the options."

async def handle_channel_creation(channel, channel_name, guild, category, interaction):
    if channel == "NEW CHANNEL":
        new_channel = await guild.create_text_channel(channel_name, category=category)
        await interaction.followup.send(f"New channel created: {new_channel.mention}")
        return new_channel
    else:
        # Attempt to find the channel by ID or name
        existing_channel = discord.utils.get(guild.channels, id=int(channel))  # Ensure channel ID is an integer
        if existing_channel:
            return existing_channel
        else:
            await interaction.followup.send(f"Error: Channel '{channel}' not found.")
            return None


# Path to store thread data
thread_data_path = Path(__file__).parent.resolve() / 'threads.json'
category_threads = {}


def save_thread_data(new_data):
    """Save thread data to a JSON file."""
    global category_threads

    try:
        with open(thread_data_path, 'w') as json_file:
            json.dump(new_data, json_file, indent=4)  # Ensure indentation for readability

        category_threads = new_data
        logging.info("Thread data saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save thread data: {e}")

def load_thread_data():
    """Load thread data from the JSON file."""
    global category_threads  # Ensure we're using the global variable

    if os.path.exists(thread_data_path):
        if os.path.getsize(thread_data_path) == 0:
            logging.error("Thread data file is empty. Initializing an empty dictionary.")
            category_threads = {}
        else:
            with open(thread_data_path, 'r') as f:
                try:
                    category_threads = json.load(f)
                    logging.info(f"Loaded thread data: {category_threads}")
                except json.JSONDecodeError as e:
                    logging.error(f"Error loading JSON data: {e}. Initializing empty thread data.")
                    category_threads = {}
    else:
        logging.warning("Thread data file not found. Initializing empty thread data.")
        category_threads = {}

    return category_threads  # Return loaded data


async def set_default_memory(category_id):
    """Set the default memory for a category to 'gameplay' if not already set."""
    global category_threads
    if category_id not in category_threads:
        category_threads[category_id] = {"gameplay": None, "out-of-game": None}
    
    # Set the default memory to gameplay if it's not already set
    if not category_threads[category_id]["gameplay"]:
        category_threads[category_id]["gameplay"] = "gameplay_thread_id"  # Replace with the actual thread ID or retrieval logic
    
    save_thread_data(category_threads)  # Save the updated data
    logging.info(f"Default memory set for category {category_id}.")

async def assign_memory(category_id, memory_name, channel_id=None):
    """Assign memory to a category or a specific channel."""
    # Load existing thread data from JSON
    category_threads = load_thread_data()

    # Ensure category_id is a string for consistent JSON handling
    category_id_str = str(category_id)

    # Log current data for this category
    logging.info(f"Current data for category {category_id_str}: {category_threads.get(category_id_str, {})}")

    # Check if the category exists in the loaded data
    if category_id_str not in category_threads:
        # Initialize if the category does not exist
        category_threads[category_id_str] = {
            'memory': {},
            'channels': {}
        }

    # Assign memory to the specified channel or category
    if channel_id is not None:
        channel_id_str = str(channel_id)
        if channel_id_str not in category_threads[category_id_str]['channels']:
            # Initialize channel data if it doesn't exist
            category_threads[category_id_str]['channels'][channel_id_str] = {
                "memory_name": memory_name,
                "assigned_memory": "",  # Initially empty
                "threads": {}
            }

        # Now, find the thread ID corresponding to the memory_name in the category's memory section
        memory_thread_id = category_threads[category_id_str]['memory'].get(memory_name, {}).get('assigned_memory')

        if memory_thread_id is None:
            logging.error(f"No thread ID found for memory '{memory_name}' in category '{category_id_str}'.")
            return "Error: No thread ID found for the specified memory."

        # Update assigned_memory for the channel
        category_threads[category_id_str]['channels'][channel_id_str]['assigned_memory'] = memory_thread_id

        # Also, create/update the thread in that channel
        category_threads[category_id_str]['channels'][channel_id_str]['threads'][memory_thread_id] = {
            "name": memory_name,  # Use memory_name for the thread name
            "assigned_memory": memory_thread_id,  # Set to the correct thread ID
            "memory_name": memory_name
        }

    # Save the updated thread data back to the JSON file
    save_thread_data(category_threads)

async def create_or_assign_memory(session, memory, memory_name, category_id_str):
    # Your logic for creating or retrieving a memory thread ID
    new_thread_id = f"thread_{memory_name}"  # Replace this with your logic to get the actual thread ID

    # Update the category_threads dictionary with the correct thread ID
    if category_id_str in category_threads:
        for channel_id, channel_data in category_threads[category_id_str]['channels'].items():
            if channel_data['memory_name'] == memory_name:  # If memory name matches
                channel_data['assigned_memory'] = new_thread_id  # Update assigned_memory to the thread ID

            # Update the threads within that channel
            for thread_id, thread_data in channel_data.get('threads', {}).items():
                if thread_data['memory_name'] == memory_name:
                    thread_data['assigned_memory'] = new_thread_id  # Ensure assigned_memory is updated to the thread ID

    return new_thread_id  # Return the new thread ID if needed


async def get_channels_in_category(category, guild):
    return [
        app_commands.Choice(name=channel.name, value=str(channel.id))
        for channel in guild.text_channels if channel.category == category
    ]


async def get_memory_options(category_id, session, predefined_threads):
    if category_id not in category_threads:
        category_threads[category_id] = {}
    for predefined_thread in predefined_threads:
        if predefined_thread not in category_threads[category_id]:
            category_threads[category_id][predefined_thread] = await create_openai_thread(
                session, f"{predefined_thread} context message", category_id, predefined_thread)
    return [
        app_commands.Choice(name=thread_name, value=thread_name)
        for thread_name in category_threads[category_id].keys()
    ] + [app_commands.Choice(name="CREATE NEW MEMORY", value="CREATE NEW MEMORY")]


async def handle_thread_creation(channel, thread_name, category_id, memory_name=None):
    # Example logic for creating a thread
    if thread_name:
        existing_threads = [t for t in channel.threads if t.name == thread_name]
        if existing_threads:
            return None, f"A thread with the name '{thread_name}' already exists."
        
        thread = await channel.create_thread(name=thread_name)
        if memory_name:
            # Additional memory handling logic here
            pass
        
        return thread, None
    else:
        return None, "Error: You must provide a name for the new thread."


async def get_assigned_memory(category_id):
    """Fetch the assigned memory for a specific category."""
    # Load the current thread data from JSON
    category_threads = load_thread_data()

    # Ensure category_id is a string for consistent JSON handling
    category_id_str = str(category_id)

    # Check if the category exists in the loaded data
    if category_id_str in category_threads:
        # Retrieve the assigned memory for the category
        assigned_memory = category_threads[category_id_str].get('assigned_memory', None)
        
        if assigned_memory is not None:
            logging.info(f"Assigned memory for category {category_id_str}: {assigned_memory}")
            return assigned_memory
        else:
            logging.info(f"No assigned memory found for category {category_id_str}.")
            return None
    else:
        logging.error(f"Category {category_id_str} does not exist in the thread data.")
        return None

async def initialize_threads(guild):
    """Initialize threads for each category and create OpenAI threads if necessary."""
    # Load existing thread data
    existing_data = load_thread_data()

    # Initialize to empty dict if data is None
    if existing_data is None:
        existing_data = {}

    async with aiohttp.ClientSession() as session:  # Ensure session is created here
        for category in guild.categories:
            category_id = str(category.id)
            category_name = category.name   

            # Create category structure if it doesn't exist
            if category_id not in existing_data:
                # Initialize category with proper structure
                existing_data[category_id] = {
                    "name": category_name,
                    "default_memory": "gameplay",
                    "memory_threads": {
                        "gameplay": None,
                        "out-of-game": None
                    },
                    "channels": {}
                }

                # Create OpenAI threads for gameplay and out-of-game
                existing_data[category_id]["memory_threads"]["gameplay"] = await create_openai_thread(session, f"Gameplay memory for {category_name}", category_id, "gameplay")
                existing_data[category_id]["memory_threads"]["out-of-game"] = await create_openai_thread(session, f"Out-of-game memory for {category_name}", category_id, "out-of-game")

            # Update or initialize channels
            for channel in category.text_channels:
                channel_id = str(channel.id)
                channel_name = channel.name
                
                # Create channel structure if it doesn't exist
                if channel_id not in existing_data[category_id]["channels"]:
                    existing_data[category_id]["channels"][channel_id] = {
                        'name': channel_name,
                        'assigned_memory': existing_data[category_id]["memory_threads"]["gameplay"],  # Default to gameplay
                        'memory_name': 'gameplay',  # Default memory name
                        'threads': {}
                    }
                else:
                    # If the channel already exists, ensure its assigned memory is correct
                    current_memory_name = existing_data[category_id]["channels"][channel_id]["memory_name"]
                    if current_memory_name == "gameplay" and channel_name.lower() == "telldm":
                        # Update the channel to use out-of-game memory if it's incorrectly set to gameplay
                        existing_data[category_id]["channels"][channel_id]["assigned_memory"] = existing_data[category_id]["memory_threads"]["out-of-game"]
                        existing_data[category_id]["channels"][channel_id]["memory_name"] = "out-of-game"

                # Ensure that the memory is set correctly for #telldm
                if channel_name.lower() == "telldm":
                    existing_data[category_id]["channels"][channel_id]["assigned_memory"] = existing_data[category_id]["memory_threads"]["out-of-game"]
                    existing_data[category_id]["channels"][channel_id]["memory_name"] = "out-of-game"

                # Access the threads property directly and populate the channel's threads
                threads = channel.threads  # Assuming `channel.threads` returns an iterable of thread objects
                for thread in threads:
                    # Add each thread under the respective channel
                    existing_data[category_id]["channels"][channel_id]['threads'][str(thread.id)] = {
                        'name': thread.name,
                        'assigned_memory': existing_data[category_id]["memory_threads"]["gameplay"],  # Change this to the actual memory ID
                        'memory_name': existing_data[category_id]["channels"][channel_id]['memory_name']  # Use channel memory name
                    }

    # Save the updated thread data
    save_thread_data(existing_data)


def get_default_memory(category_id):
    """Fetch the default memory (thread) for a given category."""
    global category_threads
    if category_id in category_threads and "gameplay" in category_threads[category_id]:
        return category_threads[category_id]["gameplay"]
    return None  # Return None if no default memory is found

def get_category_id(interaction):
    """Retrieve the category ID of the channel where the interaction occurred."""
    channel = interaction.channel
    return channel.category.id if channel.category else None