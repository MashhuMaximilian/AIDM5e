import asyncio
import logging

import discord
from discord import app_commands

from config import DM_ROLE_NAME
from discord_app.shared_functions import apply_always_on, send_interaction_message

from .db_repository import (
    DEFAULT_CHANNEL_SPECS,
    DEFAULT_MEMORY_NAMES,
    assign_memory_to_channel,
    assign_memory_to_thread,
    clear_memory_messages,
    delete_memory as delete_memory_record,
    ensure_channel_for_category,
    ensure_memory,
    ensure_thread_for_channel,
    fetch_memory_messages,
    get_assigned_memory_id,
    get_campaign_context_by_category,
    get_default_memory_id,
    get_memory_id_by_name,
    get_memory_name,
    get_or_create_campaign_context,
    list_memory_names,
    set_default_memory as set_default_memory_record,
)


logger = logging.getLogger(__name__)


async def create_memory(interaction: discord.Interaction, memory_name: str, category_id_str: str):
    context = await asyncio.to_thread(get_campaign_context_by_category, int(category_id_str))
    if not context:
        context = await asyncio.to_thread(
            get_or_create_campaign_context,
            interaction.guild.id,
            interaction.guild.name,
            int(category_id_str),
            interaction.channel.category.name,
            DM_ROLE_NAME,
        )
    return await asyncio.to_thread(ensure_memory, context.campaign_id, memory_name)


async def assign_memory(
    interaction: discord.Interaction,
    memory: str,
    channel_id: str = None,
    thread_id: str = None,
    memory_name: str = None,
):
    logger.info("Assigning memory=%s channel_id=%s thread_id=%s memory_name=%s", memory, channel_id, thread_id, memory_name)

    if memory == "CREATE NEW MEMORY" and not memory_name:
        return "Error: You must provide a name for the new memory."

    channel_obj = interaction.guild.get_channel(int(channel_id))
    if not channel_obj:
        return "Invalid channel specified. Please specify a valid channel."

    category = channel_obj.category or interaction.channel.category
    context = await asyncio.to_thread(
        get_or_create_campaign_context,
        interaction.guild.id,
        interaction.guild.name,
        category.id,
        category.name,
        DM_ROLE_NAME,
    )
    await asyncio.to_thread(
        ensure_channel_for_category,
        category.id,
        channel_obj.id,
        channel_obj.name,
        False,
        channel_obj.name == "dm-planning",
    )

    if memory == "CREATE NEW MEMORY":
        target_memory_name = memory_name
        memory_id = await asyncio.to_thread(ensure_memory, context.campaign_id, memory_name)
    else:
        target_memory_name = memory
        memory_id = await asyncio.to_thread(get_memory_id_by_name, context.campaign_id, memory)
        if memory_id is None:
            return (
                f"Error: Memory '{memory}' does not exist in category '{category.id}'. "
                f"Available memories: {await asyncio.to_thread(list_memory_names, category.id)}."
            )

    if thread_id:
        thread_obj = await interaction.guild.fetch_channel(int(thread_id))
        if not isinstance(thread_obj, discord.Thread):
            return f"Error: Thread with ID '{thread_id}' not found or is not a thread."

        await asyncio.to_thread(
            ensure_thread_for_channel,
            channel_obj.id,
            thread_obj.id,
            thread_obj.name,
            False,
        )
        await asyncio.to_thread(assign_memory_to_thread, thread_obj.id, memory_id)
        return (
            f"Memory '{target_memory_name}' assigned to thread '{thread_obj.name}' in channel "
            f"'{channel_obj.name}' with memory ID '{memory_id}'."
        )

    await asyncio.to_thread(assign_memory_to_channel, channel_obj.id, memory_id)
    return f"Memory '{target_memory_name}' assigned to channel '{channel_obj.name}' with memory ID '{memory_id}'."


async def get_default_memory(category_id):
    return await asyncio.to_thread(get_default_memory_id, int(category_id))


async def set_default_memory(category_id):
    context = await asyncio.to_thread(get_campaign_context_by_category, int(category_id))
    if not context:
        return
    gameplay_memory_id = await asyncio.to_thread(get_memory_id_by_name, context.campaign_id, "gameplay")
    if gameplay_memory_id:
        await asyncio.to_thread(set_default_memory_record, context.campaign_id, gameplay_memory_id)


async def get_assigned_memory(channel_id, category_id, thread_id=None):
    logger.info("Fetching assigned memory channel_id=%s category_id=%s thread_id=%s", channel_id, category_id, thread_id)
    return await asyncio.to_thread(get_assigned_memory_id, int(channel_id), int(category_id), int(thread_id) if thread_id else None)


async def initialize_threads(category):
    guild = category.guild
    dm_role = discord.utils.get(guild.roles, name=DM_ROLE_NAME)
    if dm_role is None:
        raise ValueError(f"Role '{DM_ROLE_NAME}' was not found. Create it and assign it to at least one user before running /invite.")

    context = await asyncio.to_thread(
        get_or_create_campaign_context,
        guild.id,
        guild.name,
        category.id,
        category.name,
        DM_ROLE_NAME,
    )

    memory_ids = {}
    for memory_name in DEFAULT_MEMORY_NAMES:
        memory_ids[memory_name] = await asyncio.to_thread(ensure_memory, context.campaign_id, memory_name)

    await asyncio.to_thread(set_default_memory_record, context.campaign_id, memory_ids["gameplay"])

    created_channels = []
    reused_channels = []
    bot_member = guild.me or guild.get_member(getattr(guild._state.user, "id", 0))
    dm_overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        dm_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    if bot_member:
        dm_overwrites[bot_member] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
        )

    for spec in DEFAULT_CHANNEL_SPECS:
        channel = discord.utils.get(category.text_channels, name=spec["name"])
        if channel is None:
            kwargs = {"name": spec["name"], "category": category}
            if spec["is_dm_private"]:
                kwargs["overwrites"] = dm_overwrites
            channel = await guild.create_text_channel(**kwargs)
            created_channels.append(spec["name"])
        else:
            reused_channels.append(spec["name"])
            if spec["is_dm_private"]:
                await channel.edit(overwrites=dm_overwrites)

        await asyncio.to_thread(
            ensure_channel_for_category,
            category.id,
            channel.id,
            channel.name,
            spec["always_on"],
            spec["is_dm_private"],
        )
        await asyncio.to_thread(assign_memory_to_channel, channel.id, memory_ids[spec["memory"]])

    return {"created": created_channels, "reused": reused_channels}


async def handle_memory_assignment(
    interaction: discord.Interaction,
    memory: str,
    channel_id: str,
    thread_id: str,
    memory_name: str = None,
    always_on: app_commands.Choice[str] = None,
):
    if memory == "CREATE NEW MEMORY" and not memory_name:
        await send_interaction_message(interaction, "Error: You must provide a name for the new memory.")
        return None, None

    if memory == "CREATE NEW MEMORY":
        await create_memory(interaction, memory_name, str(interaction.channel.category.id))
        memory_to_assign = memory_name
    else:
        memory_to_assign = memory

    result = await assign_memory(
        interaction,
        memory_to_assign,
        channel_id=channel_id,
        thread_id=thread_id,
        memory_name=memory_name,
    )
    logger.info(result)

    target_channel, target_thread = await get_channel_and_thread(interaction, channel_id, thread_id)
    if always_on:
        await apply_always_on(target_channel, target_thread, always_on.value)

    return target_channel, target_thread


async def get_channel_and_thread(interaction: discord.Interaction, channel_id: str, thread_id: str = None):
    target_channel = interaction.guild.get_channel(int(channel_id)) if channel_id and channel_id.isdigit() else None
    target_thread = None
    if thread_id:
        target_thread = interaction.guild.get_channel(int(thread_id)) if thread_id.isdigit() else None
    return target_channel, target_thread


def delete_memory(memory_name_or_id: str, category_id: int | None = None) -> str:
    try:
        if category_id is None:
            return "Error: Category ID is required to delete a memory."
        deleted = delete_memory_record(memory_name_or_id, int(category_id))
        if deleted:
            return f"Memory '{memory_name_or_id}' deleted successfully."
        return f"Error: Memory '{memory_name_or_id}' not found in this category."
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        logger.error("Error deleting memory '%s': %s", memory_name_or_id, exc)
        return f"An error occurred while deleting memory '{memory_name_or_id}': {exc}"


async def list_thread_messages(_session, memory_id):
    return await asyncio.to_thread(fetch_memory_messages, memory_id)


async def delete_message(_session, _memory_id, _message_id):
    return False


async def reset_memory_history(memory_id: str) -> int:
    return await asyncio.to_thread(clear_memory_messages, memory_id)


async def lookup_memory_name(memory_id: str | None) -> str | None:
    if not memory_id:
        return None
    return await asyncio.to_thread(get_memory_name, memory_id)
