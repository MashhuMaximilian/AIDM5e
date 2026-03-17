# helper_funtions

import asyncio
import logging

import discord
from discord import app_commands

from assistant_interactions import get_assistant_response
from content_retrieval import (
    extract_public_url_text,
    format_message_text,
    format_message_with_attachments,
    select_messages,
)
from db_repository import ensure_thread_for_channel, list_memory_names
from gemini_client import gemini_client
from memory_management import get_assigned_memory, assign_memory
from prompts.reference_prompts import build_reference_prompt
from prompts.query_prompts import construct_query_prompt
from prompts.summary_prompts import build_summary_prompt
from shared_functions import send_response
from utils import category_threads, load_thread_data

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


async def build_history_from_messages(messages: list[discord.Message], include_attachments: bool = False) -> list[str]:
    formatter = format_message_with_attachments if include_attachments else format_message_text
    history = []
    for message in messages:
        history.append(await formatter(message) if include_attachments else formatter(message))
    return history

async def summarize_conversation(interaction, conversation_history, options, query, channel_id, thread_id, assigned_memory):
    if options['type'] == 'messages':
        history = "\n".join(conversation_history)
    elif options['type'] == 'from':
        start_index = options['start_index']
        history = "\n".join(conversation_history[start_index:])
    elif options['type'] == 'between':
        start_index, end_index = options['start_index'], options['end_index']
        history = "\n".join(conversation_history[start_index:end_index])
    elif options['type'] == 'last_n':
        # For 'last_n' messages, use the provided 'n' value
        start_index = -options['last_n']
        history = "\n".join(conversation_history[start_index:])
    else:
        logging.error("Invalid options for summarization.")
        return "Invalid options for summarization."

    prompt = build_summary_prompt(history, query)

    # Call get_assistant_response with channel_id, thread_id, and assigned_memory
    response = await get_assistant_response(prompt, channel_id, thread_id=thread_id, assigned_memory=assigned_memory)
    return response

async def fetch_conversation_history(channel, start=None, end=None, message_ids=None, last_n=None):
    messages, options_or_error = await select_messages(channel, start, end, message_ids, last_n)
    if isinstance(options_or_error, str):
        return None, options_or_error
    conversation_history = await build_history_from_messages(messages, include_attachments=False)
    return conversation_history, options_or_error


async def fetch_reference_material(channel, start=None, end=None, message_ids=None, last_n=None):
    messages, options_or_error = await select_messages(channel, start, end, message_ids, last_n)
    if isinstance(options_or_error, str):
        return None, options_or_error
    material = await build_history_from_messages(messages, include_attachments=True)
    return material, options_or_error


async def answer_from_references(
    query: str,
    reference_material: list[str],
    channel_id: int,
    assigned_memory: str,
    thread_id: int | None = None,
    url: str | None = None,
):
    prompt = build_reference_prompt("\n\n".join(reference_material), query, url)
    return await get_assistant_response(prompt, channel_id, thread_id=thread_id, assigned_memory=assigned_memory)


async def answer_from_public_url(
    query: str,
    url: str,
    channel_id: int,
    assigned_memory: str,
    thread_id: int | None = None,
):
    try:
        extracted_text = await extract_public_url_text(url)
        prompt = build_reference_prompt(extracted_text, query, url)
        return await get_assistant_response(prompt, channel_id, thread_id=thread_id, assigned_memory=assigned_memory)
    except Exception as exc:
        logging.warning("Direct URL fetch failed for %s, falling back to Gemini URL Context: %s", url, exc)
        prompt = build_reference_prompt(
            "Direct fetch was unavailable. Use the provided public URL as the primary source.",
            query,
            url,
        )
        response = await asyncio.to_thread(
            gemini_client.generate_text_with_url_context,
            prompt,
            [url],
            None,
        )
        if not response:
            raise
        return response

async def handle_channel_creation(channel: str, channel_name: str, guild: discord.Guild, category: discord.CategoryChannel, interaction: discord.Interaction):
    if channel == "NEW CHANNEL":
        if not channel_name:
            await interaction.followup.send("Error: You must provide a name for the new channel.")
            return None
        # Create new channel
        new_channel = await guild.create_text_channel(name=channel_name, category=category)
        logging.info(f"Created new channel: {new_channel.id} ({new_channel.name})")
        return new_channel
    else:
        # Retrieve existing channel by ID
        try:
            target_channel = guild.get_channel(int(channel))  # Ensure channel ID is converted to int
        except ValueError:
            await interaction.followup.send("Error: Invalid channel ID.")
            return None

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
        
        await asyncio.to_thread(ensure_thread_for_channel, channel.id, thread.id, thread.name, False)

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
    del session, predefined_threads
    memory_names = await asyncio.to_thread(list_memory_names, int(category_id))
    return [
        app_commands.Choice(name=memory_name, value=memory_name)
        for memory_name in memory_names
    ] + [app_commands.Choice(name="CREATE NEW MEMORY", value="CREATE NEW MEMORY")]

def get_category_id(interaction):
    """Retrieve the category ID of the channel where the interaction occurred."""
    channel = interaction.channel
    return channel.category.id if channel.category else None

async def thread_autocomplete(interaction: discord.Interaction, current: str):
    try:
        # Load thread data from JSON
        category_threads = load_thread_data()
        category_id = str(interaction.channel.category.id)
        channel_id = None

        # Find the channel ID from command options
        for option in interaction.data.get('options', []):
            if option['name'] == 'channel':
                channel_id = str(option['value'])
                break

        if not channel_id or category_id not in category_threads:
            return []

        # Get threads from JSON structure
        channel_data = category_threads[category_id]['channels'].get(channel_id)
        if not channel_data:
            return []

        # Get both active threads and JSON-stored threads
        choices = []
        
        # 1. Add threads from JSON data
        for thread_id, thread_data in channel_data.get('threads', {}).items():
            thread_name = thread_data.get('name', f"Unnamed Thread {thread_id}")
            choices.append(
                discord.app_commands.Choice(
                    name=f"{thread_name}",
                    value=thread_id
                )
            )

        # 2. Add active threads from Discord API
        channel_obj = interaction.guild.get_channel(int(channel_id))
        if channel_obj:
            # Get active threads
            active_threads = channel_obj.threads
            # Get archived threads (adjust limits as needed)
            archived_threads = []
            async for thread in channel_obj.archived_threads(limit=100):
                archived_threads.append(thread)

            for thread in active_threads + archived_threads:
                if str(thread.id) not in channel_data.get('threads', {}):
                    choices.append(
                        discord.app_commands.Choice(
                            name=f"{thread.name} ({'active' if not thread.archived else 'archived'})",
                            value=str(thread.id)
                        )
                    )

        # Filter by current input
        filtered = [c for c in choices if current.lower() in c.name.lower()]
        return filtered[:25]

    except Exception as e:
        logging.error(f"Thread autocomplete error: {str(e)}")
        return []

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

async def process_query_command(interaction: discord.Interaction, query_type: app_commands.Choice[str], query: str, backup_channel_name: str, channel: str = None, thread: str = None):
    await interaction.response.defer()  # Defer response while processing
    
    # Construct the prompt
    prompt = construct_query_prompt(query_type.value, query)

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

    # Get the assistant's response without sending it directly
    response = await get_assistant_response(
        prompt, 
        channel_id, 
        category_id, 
        thread_id, 
        assigned_memory=assigned_memory,
        send_message=False  # Crucial change: prevent auto-sending
    )

    # Send the response through the proper interaction flow
    await send_response(
        interaction, 
        response, 
        channel_id=channel_id, 
        thread_id=thread_id, 
        backup_channel_name=backup_channel_name
    )
