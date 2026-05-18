"""
Persistent conversation history for the Discord bot.
Provides utilities to fetch recent messages, build conversation context,
and format messages for AI consumption.
"""

import logging
from datetime import datetime

import discord

logger = logging.getLogger(__name__)

# Maximum content length before truncation
MAX_CONTENT_LENGTH = 1000


async def get_recent_messages(
    channel: discord.abc.Messageable,
    limit: int = 20,
) -> list[dict]:
    """
    Fetch the last `limit` messages from a channel.

    Args:
        channel: Discord channel or thread to fetch from.
        limit: Maximum number of messages to retrieve.

    Returns:
        List of dicts with keys: author (display_name), content (text),
        id (message ID), timestamp (ISO string), reference (message ID this
        replies to, if any), attachments (list of {filename, url} dicts),
        embeds (list of embed descriptions).
    """
    try:
        messages = []
        async for msg in channel.history(limit=limit):
            embeds_description = []
            for embed in msg.embeds:
                if embed.description:
                    embeds_description.append(embed.description[:500])
                elif embed.title:
                    embeds_description.append(embed.title[:500])

            attachments_data = []
            for attachment in msg.attachments:
                attachments_data.append({
                    "filename": attachment.filename,
                    "url": attachment.url,
                })

            reference_id = None
            if msg.reference and msg.reference.message_id:
                reference_id = msg.reference.message_id

            messages.append({
                "author": msg.author.display_name,
                "content": msg.content,
                "id": msg.id,
                "timestamp": msg.created_at.isoformat() if msg.created_at else None,
                "reference": reference_id,
                "attachments": attachments_data,
                "embeds": embeds_description,
            })

        return messages

    except Exception as exc:
        logger.error("Failed to fetch recent messages: %s", exc)
        return []


async def build_conversation_context(
    channel: discord.abc.Messageable,
    current_message: discord.Message,
    lookback: int = 20,
) -> str:
    """
    Build a formatted string of recent messages suitable to prepend to a prompt.

    Args:
        channel: Discord channel or thread.
        current_message: The current message being processed.
        lookback: Number of previous messages to include.

    Returns:
        Formatted string with messages as `[author]: content` lines.
        Skips messages from the bot itself. Includes reply indicators.
        Returns empty string if no messages.
    """
    try:
        # Get bot user ID from the current message's guild
        bot_user_id = None
        if current_message.guild:
            bot_user_id = current_message.guild.me.id

        # Fetch and filter messages
        filtered = []
        seen_ids = set()

        async for msg in channel.history(limit=lookback + 5):
            # Skip the current message itself
            if msg.id == current_message.id:
                continue

            # Bot messages: only skip after first 3 (so AI sees its own recent sent messages,
            # which is critical for edit_message to work). Cap at 3 to avoid token bloat.
            if bot_user_id and msg.author.id == bot_user_id:
                try:
                    bot_count = getattr(channel, '_bot_msg_count', 0)
                    if bot_count >= 3:
                        continue
                    setattr(channel, '_bot_msg_count', bot_count + 1)
                except (AttributeError, TypeError):
                    # channel doesn't support setattr (e.g. Thread object) — use a dict instead
                    break

            # Skip duplicates
            if msg.id in seen_ids:
                continue
            seen_ids.add(msg.id)

            # Truncate very long content
            content = msg.content
            if len(content) > MAX_CONTENT_LENGTH:
                content = content[:MAX_CONTENT_LENGTH] + "..."

            reference_note = ""
            if msg.reference and msg.reference.message_id:
                reference_note = f" (reply to message_id:{msg.reference.message_id})"

            # Include embeds as text if meaningful
            embed_note = ""
            if msg.embeds:
                for embed in msg.embeds:
                    if embed.title:
                        embed_note += f" [embed: {embed.title[:200]}]"

            filtered.append(f"[{msg.author.display_name}]: {content}{reference_note}{embed_note} [message_id:{msg.id}]")

        # Reverse to chronological order (oldest first)
        filtered.reverse()

        if not filtered:
            return ""

        return "\n".join(filtered)

    except Exception as exc:
        logger.error("Failed to build conversation context: %s", exc)
        return ""


def format_conversation_for_ai(messages: list[dict]) -> str:
    """
    Format a list of message dicts for AI consumption.

    Args:
        messages: List of message dicts from get_recent_messages or similar.

    Returns:
        A formatted string with a header line and each message on its own line
        as `[display_name]: message content`. No bot messages included.
    """
    if not messages:
        return ""

    lines = [f"--- Recent Conversation (last {len(messages)} messages) ---\n"]

    for msg in messages:
        author = msg.get("author", "unknown")
        content = msg.get("content", "")

        # Skip empty content
        if not content:
            continue

        # Truncate long content
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "..."

        # Include attachments info if any
        attachments = msg.get("attachments", [])
        if attachments:
            attachment_info = ", ".join(a.get("filename", "") for a in attachments if a.get("filename"))
            if attachment_info:
                content = f"{content} [attachments: {attachment_info}]"

        # Include reference if present
        reference = msg.get("reference")
        if reference:
            content = f"{content} (reply to message_id:{reference})"

        lines.append(f"[{author}]: {content}")

    lines.append("--- End Recent Conversation ---")
    return "\n".join(lines)