# helper_funtions

import discord
from discord import app_commands
from message_handlers import send_response_in_chunks
import json
from assistant_interactions import create_or_get_thread, get_assistant_response
from config import HEADERS
import aiohttp
import logging
from pathlib import Path
import os


# Dictionary to store thread IDs for the #telldm channel
category_threads = {}
category_conversations = {}




async def create_openai_thread(session, user_message, category_id, thread_type):
    """Create a new OpenAI thread and store its ID for the category."""
    logging.info(f"Creating new OpenAI thread for category {category_id} of type {thread_type}")
    
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
        category_threads[category_id][thread_type] = thread_id
        logging.info(f"New OpenAI thread created for category {category_id} with thread ID: {thread_id} of type {thread_type}")
    
    return thread_id

async def send_to_telldm(interaction, response):
    """Send a response to the #telldm channel and the corresponding OpenAI thread."""
    
    # Get the current channel and its category
    current_channel = interaction.channel
    category = current_channel.category
    category_id = category.id  # Use the category ID for OpenAI thread management

    # Initialize a variable to hold the thread ID
    thread_id = None
    
    # Check if a thread already exists for this category
    if category_id in category_threads:
        thread_id = category_threads[category_id]
        logging.info(f"Reusing existing OpenAI thread ID for category {category_id}: {thread_id}")
    else:
        # Create a new OpenAI thread if it doesn't exist
        async with aiohttp.ClientSession() as session:

            thread_id = await create_openai_thread(session, response, category_id)

    
    # Now send the response to the OpenAI thread
    async with aiohttp.ClientSession() as session:
        async with session.post(f"https://api.openai.com/v1/threads/{thread_id}/messages", headers=HEADERS, json={
            "role": "assistant",  # Assuming the bot acts as the assistant
            "content": response
        }) as send_response:
            if send_response.status != 200:
                raise Exception(f"Error sending message to OpenAI thread: {await send_response.text()}")

    # Find or create the #telldm channel in the same category
    telldm_channel = discord.utils.get(interaction.guild.channels, name='telldm', category=category)
    if not telldm_channel:
        # Create the channel if it doesn't exist
        telldm_channel = await interaction.guild.create_text_channel('telldm', category=category)
    
    # Send the response to the #telldm Discord channel
    if telldm_channel:
        await send_response_in_chunks(telldm_channel, response)  # Send the response to the #telldm channel
        logging.info(f"Response sent to #telldm channel: {response[:100]}")
    else:
        logging.error("Channel #telldm not found or could not be created.")

    # Inform the user where the response was sent, including a link to the channel
    await interaction.followup.send(f"Response has been posted to the OpenAI thread and the {telldm_channel.mention} channel.")

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

    # Write the new data directly to the file
    try:
        with open(thread_data_path, 'w') as json_file:
            json.dump(new_data, json_file, indent=4)  # Ensure indentation for readability

        # Update the global category_threads with the new data
        category_threads = new_data
        logging.info("Thread data saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save thread data: {e}")

def load_thread_data():
    """Load thread data from the JSON file."""
    try:
        with open(thread_data_path, 'r') as json_file:
            return json.load(json_file)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.error(f"Failed to load thread data: {e}")
        return {}
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
        logging.warning(f"Thread data file not found. Initializing empty thread data.")
        category_threads = {}

    return category_threads  # Return loaded data

async def set_default_thread(category_id):
    """Set the default thread for a category to 'gameplay'."""
    global category_threads
    if category_id not in category_threads:
        category_threads[category_id] = {"gameplay": None, "out-of-game": None}
        save_thread_data(category_threads)  # Save the updated data
        logging.info(f"Default thread set for category {category_id}.")

async def assign_thread(category_id, thread_type, thread_id):
    """Assign a thread ID to a specific thread type for a category."""
    global category_threads
    if category_id in category_threads:
        category_threads[category_id][thread_type] = thread_id
        save_thread_data(category_threads)  # Save the updated data
        logging.info(f"Assigned thread ID {thread_id} to {thread_type} for category {category_id}.")
    else:
        logging.error(f"Category {category_id} not found. Cannot assign thread.")


async def create_or_assign_memory(session, memory, memory_name, category_id):
    if memory == "CREATE NEW MEMORY":
        if memory_name is None:
            return "Error: You must provide a name for the new memory."
        
        memory_thread_id = await create_openai_thread(session, memory_name, category_id, memory_name)

        # Ensure the category exists in the global category_threads
        if category_id not in category_threads:
            category_threads[category_id] = {}

        # Add the new memory thread ID under its memory name
        category_threads[category_id][memory_name] = memory_thread_id

        # Save the updated category threads to JSON
        save_thread_data(category_threads)

        logging.info(f"Created new memory thread '{memory_name}' for category {category_id} with ID: {memory_thread_id}")
        return f"New memory '{memory_name}' created with thread ID: {memory_thread_id}"
    else:
        # Logic for assigning to an existing memory can be added here
        return "No action taken."


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


