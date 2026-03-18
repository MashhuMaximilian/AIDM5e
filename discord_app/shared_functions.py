import asyncio
import logging
import re

import discord

from config import client
from data_store.db_repository import (
    ensure_channel_for_category,
    ensure_thread_for_channel,
    get_or_create_campaign_context,
    is_always_on,
    set_channel_always_on,
    set_thread_always_on,
)


always_on_channels = {}
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
BULLET_ONLY_RE = re.compile(r"^\s*(?:[-*•]|o)\s*$")
LIST_ITEM_RE = re.compile(r"^(\s*)(?:[-*•]|o)\s+(.*\S.*)$")


def _normalize_list_formatting(response: str) -> str:
    """Clean up dense model-generated lists without touching code fences or quotes."""
    normalized_lines = []
    in_code_fence = False

    for raw_line in response.splitlines():
        stripped = raw_line.strip()

        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            normalized_lines.append(raw_line.rstrip())
            continue

        if in_code_fence or raw_line.lstrip().startswith(">"):
            normalized_lines.append(raw_line.rstrip())
            continue

        if BULLET_ONLY_RE.match(raw_line):
            continue

        list_match = LIST_ITEM_RE.match(raw_line)
        if list_match:
            indent = "  " if len(list_match.group(1)) >= 2 else ""
            normalized_lines.append(f"{indent}• {list_match.group(2).strip()}")
            continue

        normalized_lines.append(raw_line.rstrip())

    cleaned = "\n".join(normalized_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def format_for_discord(response: str) -> str:
    """Normalize model output to Discord-friendly formatting."""
    if not response:
        return response

    # Discord does not reliably render masked markdown links in bot content.
    response = MARKDOWN_LINK_RE.sub(lambda match: match.group(2), response)
    return _normalize_list_formatting(response)


async def set_always_on(channel_or_thread, always_on_value):
    always_on = bool(always_on_value)
    category = channel_or_thread.parent.category if isinstance(channel_or_thread, discord.Thread) else channel_or_thread.category
    await asyncio.to_thread(
        get_or_create_campaign_context,
        channel_or_thread.guild.id,
        channel_or_thread.guild.name,
        category.id,
        category.name,
    )

    if isinstance(channel_or_thread, discord.Thread):
        await asyncio.to_thread(
            ensure_channel_for_category,
            channel_or_thread.parent.category.id,
            channel_or_thread.parent.id,
            channel_or_thread.parent.name,
            False,
            False,
        )
        await asyncio.to_thread(
            ensure_thread_for_channel,
            channel_or_thread.parent.id,
            channel_or_thread.id,
            channel_or_thread.name,
            always_on,
        )
        await asyncio.to_thread(set_thread_always_on, channel_or_thread.id, always_on)
    else:
        await asyncio.to_thread(
            ensure_channel_for_category,
            channel_or_thread.category.id,
            channel_or_thread.id,
            channel_or_thread.name,
            always_on,
            False,
        )
        await asyncio.to_thread(set_channel_always_on, channel_or_thread.id, always_on)

    always_on_channels[channel_or_thread.id] = always_on
    if not always_on:
        always_on_channels.pop(channel_or_thread.id, None)

    status_message = "now always listening to all messages." if always_on else "now only responding when mentioned."
    await channel_or_thread.send(f"AI assistant is {status_message}")
    logging.info("%s %s always_on=%s", type(channel_or_thread).__name__, channel_or_thread.id, always_on)


async def check_always_on(channel_id, category_id, thread_id):
    try:
        return await asyncio.to_thread(is_always_on, channel_id, thread_id)
    except Exception as exc:
        logging.error("Failed to check always_on for category %s channel %s thread %s: %s", category_id, channel_id, thread_id, exc)
        return False


async def send_response_in_chunks(channel, response):
    if response is None:
        logging.error("Received None as response.")
        return
    response = format_for_discord(response)
    if len(response) > 2000:
        for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
            await channel.send(chunk)
    else:
        await channel.send(response)


async def send_response(interaction, response, channel_id=None, thread_id=None, backup_channel_name=None):
    target_channel = None

    if channel_id and thread_id is None:
        target_channel = client.get_channel(channel_id)
    elif thread_id:
        target_channel = client.get_channel(thread_id)
    else:
        category = interaction.channel.category
        if category:
            target_channel = discord.utils.get(category.text_channels, name=backup_channel_name) or interaction.channel

    if not target_channel:
        await interaction.followup.send("Error: Could not determine target channel.")
        return

    await send_response_in_chunks(target_channel, response)

    if target_channel != interaction.channel:
        await interaction.followup.send(f"Response sent to <#{target_channel.id}>.")
    else:
        await interaction.followup.send("See Below.")


async def send_interaction_message(interaction, content: str, **kwargs):
    """Send a reply through the initial interaction response when possible."""
    if interaction.response.is_done():
        return await interaction.followup.send(content, **kwargs)
    return await interaction.response.send_message(content, **kwargs)


async def send_command_ack(interaction, content: str = "Working...", **kwargs):
    """Acknowledge a potentially long-running command without showing the thinking state."""
    if interaction.response.is_done():
        return None
    return await interaction.response.send_message(content, ephemeral=True, **kwargs)


async def apply_always_on(target_channel, target_thread, always_on_value: str):
    if always_on_value == "on":
        if target_thread:
            await set_always_on(target_thread, True)
        elif target_channel:
            await set_always_on(target_channel, True)
    else:
        if target_thread:
            await set_always_on(target_thread, False)
        elif target_channel:
            await set_always_on(target_channel, False)
