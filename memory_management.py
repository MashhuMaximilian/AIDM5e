import logging
import aiohttp
import discord
from config import HEADERS
from utils import load_thread_data, save_thread_data, category_threads




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
    existing_data = load_thread_data() or {}  # Ensure existing_data is an empty dict if None

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
                    # Determine if the channel is #telldm
                    is_telldm = channel_name.lower() == "telldm"
                    
                    # Initialize channel with proper structure, including always_on
                    existing_data[category_id]["channels"][channel_id] = {
                        'name': channel_name,
                        'assigned_memory': existing_data[category_id]["memory_threads"]["gameplay"],  # Default to gameplay
                        'memory_name': "gameplay" if not is_telldm else "out-of-game",  # Set based on whether it's #telldm
                        'always_on': True if is_telldm else False,  # Set True for #telldm
                        'threads': {}
                    }

                # Access the threads property directly and populate the channel's threads
                threads = channel.threads  # Assuming `channel.threads` returns an iterable of thread objects
                for thread in threads:
                    # Use .get() to safely access the always_on value
                    always_on = existing_data[category_id]["channels"][channel_id].get('always_on', False)  # Default to False if not found
                    
                    # Add each thread under the respective channel
                    existing_data[category_id]["channels"][channel_id]['threads'][str(thread.id)] = {
                        'name': thread.name,
                        'assigned_memory': existing_data[category_id]["memory_threads"]["gameplay"],  # Change this to the actual memory ID
                        'memory_name': existing_data[category_id]["channels"][channel_id]['memory_name'],  # Use channel memory name
                        'always_on': always_on  # Use inherited always_on value
                    }

    # Save the updated thread data, including channels
    save_thread_data(existing_data)


