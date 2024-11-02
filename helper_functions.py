# helper_funtions

import discord
from discord import app_commands
import json
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

async def fetch_discord_threads(channel):
    """Fetches all available threads in a given channel and populates from the JSON file."""
    discord_threads = []
    # Fetching threads directly from Discord
    for thread in channel.threads:
        discord_threads.append(thread)
    
    # Load the category threads from the JSON file to compare or augment
    category_id = str(channel.category.id) if channel.category else None
    if category_id in category_threads:
        logging.info(f"Threads for category {category_id}: {category_threads[category_id]}")
    
    return discord_threads

async def summarize_conversation(interaction, conversation_history, options, query):
    from assistant_interactions import get_assistant_response  # Local import to avoid circular dependency
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

async def handle_channel_creation(channel: str, channel_name: str, guild: discord.Guild, category: discord.CategoryChannel, interaction: discord.Interaction):
    if channel == "NEW CHANNEL":
        # Create new channel
        new_channel = await guild.create_text_channel(name=channel_name, category=category)
        logging.info(f"Created new channel: {new_channel.id} ({new_channel.name})")
        return new_channel
    else:
        # Retrieve existing channel
        target_channel = guild.get_channel(int(channel))  # Ensure channel ID is converted to int
        if target_channel is None:
            await interaction.followup.send("Error: Channel not found.")
            return None
        return target_channel

async def handle_thread_creation(interaction, channel, thread_name, category_id, memory_name=None):
    # Example logic for creating a thread
    if thread_name:
        existing_threads = [t for t in channel.threads if t.name == thread_name]
        if existing_threads:
            return None, f"A thread with the name '{thread_name}' already exists."
        
        thread = await channel.create_thread(name=thread_name)
        logging.info(f"Created new thread: {thread.id} ({thread.name})")
        
        # Immediately update JSON for the new thread
        category_threads = load_thread_data()
        category_id_str = str(category_id)

        # Create an entry for the new thread in the JSON
        if category_id_str in category_threads:
            channel_data = category_threads[category_id_str]['channels'].setdefault(str(channel.id), {
                "name": channel.name,
                "assigned_memory": None,
                "memory_name": None,
                "threads": {}
            })
            channel_data['threads'][str(thread.id)] = {
                "name": thread.name,
                "assigned_memory": None,
                "memory_name": None
            }

            # Save the updated JSON data
            save_thread_data(category_threads)

            # Optionally assign memory to the new thread if provided
            if memory_name:
                await assign_memory(interaction, memory_name, str(channel.id), str(thread.id))

        return thread, None
    else:
        return None, "Error: You must provide a name for the new thread."

# Path to store thread data
thread_data_path = Path(__file__).parent.resolve() / 'threads.json'


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
                    logging.info(f"Loaded thread data: {str(category_threads)[-100:]}")
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

async def create_memory(interaction: discord.Interaction, memory_name: str, category_id_str: str):
    async with aiohttp.ClientSession() as session:
        memory_thread_id = await create_openai_thread(session, f"Memory: {memory_name}", category_id_str, memory_name)

    # Load the current category threads data
    category_threads = load_thread_data()
    if category_id_str not in category_threads:
        category_threads[category_id_str] = {'memory_threads': {}, 'channels': {}}

    # Store the new memory in the memory_threads
    category_threads[category_id_str]['memory_threads'][memory_name] = memory_thread_id

    # Save the updated JSON data
    save_thread_data(category_threads)

    return memory_thread_id  # Return the ID of the created memory thread

async def assign_memory(
    interaction: discord.Interaction,
    memory: str,
    channel_id: str = None,
    thread_id: str = None,
    memory_name: str = None,
):
    # No need to defer again since it's already been done
    logging.info(f"Assigning memory: {memory}, channel_id: {channel_id}, thread_id: {thread_id}, memory_name: {memory_name}")

    if memory == "CREATE NEW MEMORY" and not memory_name:
        logging.error("Error: You must provide a name for the new memory.")
        return "Error: You must provide a name for the new memory."

    channel_obj = interaction.guild.get_channel(int(channel_id))
    if not channel_obj:
        logging.error("Invalid channel specified.")
        return "Invalid channel specified. Please specify a valid channel."

    category_id_str = str(interaction.channel.category.id)
    category_threads = load_thread_data()  # Load your JSON data

    if category_id_str not in category_threads:
        logging.error(f"Error: Category ID '{category_id_str}' does not exist.")
        return f"Error: Category ID '{category_id_str}' does not exist."

    category_data = category_threads[category_id_str]

    # Create a new memory if necessary
    if memory == "CREATE NEW MEMORY":
        async with aiohttp.ClientSession() as session:
            memory_thread_id = await create_openai_thread(session, f"Memory: {memory_name}", category_id_str, memory_name)
            category_data['memory_threads'][memory_name] = memory_thread_id  # Set the new memory in memory_threads
            logging.info(f"New memory created: {memory_name} with ID: {memory_thread_id}")
    else:
        memory_thread_id = category_data['memory_threads'].get(memory)
        if memory_thread_id is None:
            logging.error(f"Error: Memory '{memory}' does not exist in category '{category_id_str}'.")
            return f"Error: Memory '{memory}' does not exist in category '{category_id_str}'. Available memories: {list(category_data['memory_threads'].keys())}."

        memory_name = memory  # Use memory as the name
        logging.info(f"Using existing memory: {memory_name}")

    # Update or create the channel entry
    channel_data = category_data['channels'].setdefault(str(channel_id), {
        "name": channel_obj.name,
        "assigned_memory": None,
        "memory_name": None,
        "threads": {}
    })

    # Update memory assignment for a specific thread if provided
    if thread_id:
        thread_obj = await interaction.guild.fetch_channel(int(thread_id))  # Assuming `thread` is the ID of the thread
        if not isinstance(thread_obj, discord.Thread):
            logging.error(f"Error: Thread with ID '{thread_id}' not found or is not a thread.")
            return f"Error: Thread with ID '{thread_id}' not found or is not a thread."

        thread_id_str = str(thread_obj.id)
        thread_name = thread_obj.name

        logging.info(f"Assigning memory to thread: {thread_name}, ID: {thread_id_str}")
        # Assign the memory to the thread within the channel
        channel_data['threads'][thread_id_str] = {
            "name": thread_name,
            "assigned_memory": memory_thread_id,
            "memory_name": memory_name
        }
    else:
        # If no thread is specified, assign the memory to the entire channel
        logging.info(f"Assigning memory to channel: {channel_obj.name}")
        channel_data['assigned_memory'] = memory_thread_id
        channel_data['memory_name'] = memory_name
        # Update the memory_threads with the channel-wide memory
        category_data['memory_threads'][memory_name] = memory_thread_id

    # Save the updated JSON data
    save_thread_data(category_threads)
    logging.info("Thread data saved successfully.")

    if thread_id:
        return f"Memory '{memory_name}' assigned to thread '{thread_obj.name}' in channel '{channel_obj.name}' with thread ID '{memory_thread_id}'."
    else:
        return f"Memory '{memory_name}' assigned to channel '{channel_obj.name}' with thread ID '{memory_thread_id}'."

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

async def get_default_memory(category_id):
    """Retrieve the default or 'out-of-game' memory for a category."""
    category_data = category_threads.get(category_id)
    if category_data:
        return category_data['memory_threads'].get("out-of-game")

    logging.info(f"No default memory found for category {category_id}.")
    return None

async def get_assigned_memory(channel_id, category_id, thread_id=None):
    """Retrieve the assigned memory for a specific channel or thread in a category."""
    logging.info(f"Fetching assigned memory for channel_id: {channel_id}, thread_id: {thread_id}, category_id: {category_id}")

    category_threads = load_thread_data()  # Load your JSON data
    category_id_str = str(category_id)

    if category_id_str not in category_threads:
        logging.info(f"No data found for category '{category_id_str}'.")
        return None

    channel_data = category_threads[category_id_str]['channels'].get(str(channel_id))
    if channel_data:
        assigned_memory = channel_data.get('assigned_memory')

        if thread_id:
            thread_data = channel_data['threads'].get(str(thread_id))
            if thread_data:
                assigned_memory = thread_data.get('assigned_memory') or assigned_memory

        if assigned_memory:
            # Remove leading/trailing whitespace, quotes, and stray periods
            assigned_memory = assigned_memory.strip().strip("'\". ")
            logging.info(f"Assigned Memory found: {assigned_memory}")
            return assigned_memory if assigned_memory else None

    logging.info(f"No assigned memory found for channel '{channel_id}' in category '{category_id}'.")
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

def get_category_id(interaction):
    """Retrieve the category ID of the channel where the interaction occurred."""
    channel = interaction.channel
    return channel.category.id if channel.category else None

async def thread_autocomplete(interaction: discord.Interaction, current: str):
    # Ensure the options are available and correct
    for option in interaction.data['options']:
        if option['name'] == 'channel':  # Check if 'channel' is provided
            try:
                channel_id = int(option['value'])  # Convert channel ID to integer
                channel_obj = interaction.guild.get_channel(channel_id)

                if not channel_obj:
                    return []

                # Fetch active and archived threads
                active_threads = channel_obj.threads
                archived_threads = []
                async for thread in channel_obj.archived_threads():
                    archived_threads.append(thread)

                all_threads = active_threads + archived_threads

                # Filter threads by current input
                matching_threads = [
                    discord.app_commands.Choice(name=thread.name, value=str(thread.id))
                    for thread in all_threads if current.lower() in thread.name.lower()
                ]

                return matching_threads[:50]  # Limit to 50 suggestions

            except ValueError:
                print(f"Invalid channel ID: {option['value']}")
                return []  # Return empty list if there's an error

    return []  # Return empty if no 'channel' option was found

async def channel_autocomplete(interaction: discord.Interaction, current: str):
    # Assuming get_channels_in_category is a function you've defined for fetching channels in a category
    return await get_channels_in_category(interaction.channel.category, interaction.guild)

async def memory_autocomplete(interaction: discord.Interaction, current: str):
    category_id_str = str(interaction.channel.category.id)

    # Load the memory_threads from JSON data
    category_threads = load_thread_data()
    if category_id_str not in category_threads:
        return []

    # Get all memory threads for the category
    memory_threads = category_threads[category_id_str].get('memory_threads', {})

    # Create list for matching memories, including "Create New Memory" option
    matching_memories = [
        discord.app_commands.Choice(name="CREATE A NEW MEMORY", value="CREATE NEW MEMORY")
    ]

    # Filter memory names by input
    matching_memories += [
        discord.app_commands.Choice(name=memory_name, value=memory_name)
        for memory_name in memory_threads if current.lower() in memory_name.lower()
    ]

    return matching_memories[:50]  # Limit to 50 suggestions
