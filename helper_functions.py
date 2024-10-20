# helper_funtions

import discord
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

async def handle_channel_creation(interaction, channel, channel_name):
    guild = interaction.guild
    category = interaction.channel.category
    target_channel = None

    if channel == "NEW CHANNEL":
        target_channel = await guild.create_text_channel(channel_name, category=category)
        await interaction.followup.send(f"New channel created: {target_channel.mention}")
    else:
        target_channel = guild.get_channel(int(channel))
        if target_channel is None:
            await interaction.followup.send("Error: Target channel not found.")
            return None
        await interaction.followup.send(f"Using existing channel: <#{target_channel.id}>")

    return target_channel


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