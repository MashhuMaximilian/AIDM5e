# helper_funtions

import discord
from discord import app_commands
from assistant_interactions import get_assistant_response
import logging
from utils import load_thread_data, save_thread_data, category_threads
from memory_management import create_openai_thread, get_assigned_memory, assign_memory
from shared_functions import send_response

category_conversations = {}

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

async def construct_prompt(query_type: str, query: str) -> str:
    prompt_templates = {
        # for /tellme
        "spell": "I have a question about the spell. Besides your answer, be sure to also send the description of the spell mentioned, that you can find in the Player's Handbook, with its parameters: casting time, level, components, description, range, duration, attack/save, damage/effect, and a link to where somebody could find that spell on one of these websites: http://dnd5e.wikidot.com/, https://www.dndbeyond.com/, https://roll20.net/compendium/dnd5e, or https://www.aidedd.org/dnd. {query}",
        "checkstatus": "I would like to know the current status of a character, including HP, spell slots, conditions, and any other relevant information. {query}",
        "hbw_item": "I have a question about a homebrew item. Provide the item's full description, properties, and usage as it was detailed by the creator of the item or as it appears in this campaign. Make sure to mention who the item belongs to and any relevant background information. {query}",
        "npc": "I have a question about an NPC. Provide all known information about this NPC, including their background, motivations, recent interactions with the party. {query}",
        "inventory": "I have a question about the inventory of a character. Please provide a detailed list of items currently in the specified character’s inventory, including any magical properties or special features. If asking about a specific item, confirm its presence and provide details. {query}",
        "rollcheck": "I want to test the feasibility of an action or a skill check before deciding to do it in the game. Please provide guidance on what I would need to roll, including the appropriate skill and any potential outcomes or modifiers to consider. {query}",

        # for /askdm
        "game_mechanics": "This is a query about game mechanics and gameplay elements based on official sources like the Player’s Handbook (PHB) or Dungeon Master’s Guide (DMG). Please provide a detailed explanation with rules, examples, and references to relevant sources as well as links from https://www.dndbeyond.com/, https://rpgbot.net/dnd5, or https://roll20.net/. Here is the question: {query}",
        "monsters_creatures": "This is a question about monsters or creatures, including those from the Monster Manual or homebrew. Please include their abilities, weaknesses, lore, and strategies for handling them in combat. Provide references to the source and links to reliable websites like a link to where somebody could find that spell on one of these websites: http://dnd5e.wikidot.com/, https://www.dndbeyond.com/, https://roll20.net/compendium/dnd5e, https://forgottenrealms.fandom.com/wiki, or https://www.aidedd.org/dnd. Question: {query}",
        "world_lore_history": "This is an inquiry about the lore, history, and cosmology of the game world. Provide a detailed explanation with relevant background information, official sources, and any notable events or characters. Include links to 3 reliable links to relevant websites. Question: {query}",
        "conditions_effects": "This is a question about conditions and their effects, such as stunned, poisoned, grappled, etc. Please explain their rules, implications in combat and exploration, and provide any interactions with spells or abilities. Reference official sources like the PHB or DMG or links from https://www.dndbeyond.com/, https://rpgbot.net/dnd5, or https://roll20.net/. Question: {query}",
        "rules_clarifications": "This is a query about specific rule clarifications. Please provide a clear and detailed explanation based on official sources, and include any applicable errata or optional rules. Reference the PHB, DMG, or other official sourcebooks or links from https://www.dndbeyond.com/, https://rpgbot.net/dnd5, or https://roll20.net/. Question: {query}",
        "item": "I have a question about an item. Besides your answer, include the item’s full description, properties, and usage, as detailed in the Player’s Handbook or Dungeon Master’s Guide. Also, provide a link to where someone can find more information about the item on these websites: http://dnd5e.wikidot.com/, https://www.dndbeyond.com/, https://roll20.net/compendium/dnd5e, or https://www.aidedd.org/dnd. {query}",
        "race_class": "This is a question about a D&D race, class, or subclass, including official content or homebrew. Please provide details on abilities, traits, key features, and how to optimize gameplay. Include lore, background, and roleplaying suggestions for the race or class. If possible, compare it with similar races or classes. Provide references to the source material and links to reliable websites like https://forgottenrealms.fandom.com/wiki, https://www.dndbeyond.com/, https://rpgbot.net/dnd5, or https://roll20.net/. Question: {query}"
    }
    return prompt_templates.get(query_type, "{query}").format(query=query)

async def process_query_command(interaction: discord.Interaction, query_type: app_commands.Choice[str], query: str, backup_channel_name: str, channel: str = None, thread: str = None):
    await interaction.response.defer()  # Defer response while processing
    
    # Construct the prompt
    prompt = await construct_prompt(query_type.value, query)

    # Determine category ID from the interaction's category
    category_id = interaction.channel.category.id if interaction.channel.category else None

    # Initialize channel_id and thread_id with None
    channel_id = None
    thread_id = None

    # Determine where to send the response if no channel or thread is specified
    if not channel and not thread:
        # Find the backup channel in the current category
        target_channel = discord.utils.get(interaction.guild.channels, name=backup_channel_name, category=interaction.channel.category)
        channel_id = target_channel.id if target_channel else None
    else:
        # Set channel_id and thread_id if provided in the command
        channel_id = int(channel) if channel else None
        thread_id = int(thread) if thread else None

    # Fetch memory based on parameters (either channel, thread, or backup)
    assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id) if thread_id else await get_assigned_memory(channel_id, category_id)
    if not assigned_memory:
        logging.info("No assigned memory found for the given parameters.")
        await interaction.followup.send("No memory found for the specified parameters.")
        return

    # Get the assistant's response using the constructed prompt and the assigned memory
    response = await get_assistant_response(prompt, channel_id, category_id, thread_id, assigned_memory=assigned_memory)

    # Send the response to the specified channel, thread, or backup channel
    await send_response(interaction, response, channel_id=channel_id, thread_id=thread_id, backup_channel_name=backup_channel_name)
