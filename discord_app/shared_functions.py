import asyncio
import logging
import re
from datetime import datetime

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
sent_messages: dict[int, list[dict]] = {}  # channel_id -> list of sent message records
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


async def send_response_in_chunks(channel, response, description: str | None = None):
    if response is None:
        logging.error("Received None as response.")
        return None

    channel_id = channel.id
    sent_ids: list[int] = []

    # Handle dict response with embed data
    if isinstance(response, dict):
        text_content = response.get("text", "")
        embed = response.get("embed")
        if text_content and embed:
            # Send embed with text content
            if len(text_content) > 2000:
                for chunk in [text_content[i:i + 2000] for i in range(0, len(text_content), 2000)]:
                    msg = await channel.send(chunk, embed=embed)
                    sent_ids.append(msg.id)
            else:
                msg = await channel.send(text_content, embed=embed)
                sent_ids.append(msg.id)
            _record_sent_messages(channel_id, sent_ids, description)
            return sent_ids[-1] if sent_ids else None
        elif embed:
            msg = await channel.send(embed=embed)
            sent_ids.append(msg.id)
            _record_sent_messages(channel_id, sent_ids, description)
            return sent_ids[-1] if sent_ids else None
        elif text_content:
            response = text_content
        else:
            logging.warning("Received dict response with no text or embed: %s", response)
            return None

    response = format_for_discord(str(response))
    if len(response) > 2000:
        for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
            msg = await channel.send(chunk)
            sent_ids.append(msg.id)
    else:
        msg = await channel.send(response)
        sent_ids.append(msg.id)

    _record_sent_messages(channel_id, sent_ids, description)
    return sent_ids[-1] if sent_ids else None


def _record_sent_messages(channel_id: int, message_ids: list[int], description: str | None) -> None:
    """Record sent message IDs for later retrieval."""
    if channel_id not in sent_messages:
        sent_messages[channel_id] = []
    for msg_id in message_ids:
        record = {
            "message_id": msg_id,
            "channel_id": channel_id,
            "timestamp": datetime.utcnow().isoformat(),
            "description": (description or "")[:100],
        }
        sent_messages[channel_id].append(record)


def get_sent_messages(channel_id: int, thread_id: int | None = None) -> list[dict]:
    """Get all sent message records for a channel (optionally filtered by thread)."""
    records = sent_messages.get(channel_id, [])
    if thread_id is not None:
        # For thread messages, the channel_id is the parent channel,
        # but messages are sent in the thread. We track by parent channel.
        return records  # Could filter by thread_id if stored in record
    return records


def get_last_sent_message(channel_id: int, thread_id: int | None = None) -> dict | None:
    """Get the most recent sent message record for a channel."""
    records = sent_messages.get(channel_id, [])
    return records[-1] if records else None


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
    try:
        if interaction.response.is_done():
            return await interaction.followup.send(content, **kwargs)
        return await interaction.response.send_message(content, **kwargs)
    except discord.NotFound:
        # Interaction expired or invalid — fall back to followup if possible
        try:
            return await interaction.followup.send(content, **kwargs)
        except discord.NotFound:
            return None


async def send_command_ack(interaction, content: str = "Working...", **kwargs):
    """Acknowledge a potentially long-running command without showing the thinking state."""
    if interaction.response.is_done():
        logging.warning(f"Interaction response already done for send_command_ack: {interaction.id}")
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
