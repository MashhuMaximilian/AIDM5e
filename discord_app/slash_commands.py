"""AI-callable wrappers for Discord slash commands.

This module provides async functions that the AI can call to perform
Discord operations like sending embeds, rolling dice, and managing context.
Each function accepts simple Python args and returns result strings.
"""

import asyncio
import logging
import random
import re
from typing import Any

import discord
from google.genai import types

from config import client
from data_store.db_repository import get_assigned_memory_id


logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================

def _parse_dice_string(dice_string: str) -> list[tuple[int, int]]:
    """Parse a dice string like '2d6+3' into a list of (count, sides) tuples.
    
    Args:
        dice_string: Dice notation string (e.g., '2d6+3', '1d20', 'd4')
        
    Returns:
        List of (count, sides) tuples for each dice group.
        
    Raises:
        ValueError: If the dice string is malformed.
    """
    dice_pattern = re.compile(r'(\d*)d(\d+)', re.IGNORECASE)
    matches = dice_pattern.findall(dice_string)
    
    if not matches:
        raise ValueError(f"Invalid dice string: '{dice_string}'. Use format like '2d6+3' or '1d20'.")
    
    result = []
    for count_str, sides_str in matches:
        count = int(count_str) if count_str else 1
        sides = int(sides_str)
        if count < 1 or count > 100:
            raise ValueError(f"Dice count must be between 1 and 100, got {count}.")
        if sides < 2 or sides > 100:
            raise ValueError(f"Dice sides must be between 2 and 100, got {sides}.")
        result.append((count, sides))
    
    return result


def _roll_dice(count: int, sides: int) -> list[int]:
    """Roll `count` dice with `sides` sides.
    
    Args:
        count: Number of dice to roll.
        sides: Number of sides per die.
        
    Returns:
        List of individual die results.
    """
    return [random.randint(1, sides) for _ in range(count)]


def _color_from_name(color_name: str) -> discord.Color:
    """Convert a color name or hex string to a discord.Color.
    
    Args:
        color_name: Color name (e.g., 'DarkBlue', 'Red') or hex (e.g., '#FF0000').
        
    Returns:
        discord.Color object.
    """
    color_map = {
        "darkblue": discord.Color.dark_blue(),
        "blue": discord.Color.blue(),
        "blurple": discord.Color.blurple(),
        "brandgreen": discord.Color.brand_green(),
        "brandred": discord.Color.brand_red(),
        "darkgreen": discord.Color.dark_green(),
        "darkgrey": discord.Color.dark_grey(),
        "darkergrey": discord.Color.darker_grey(),
        "darkred": discord.Color.dark_red(),
        "darkteal": discord.Color.dark_teal(),
        "fuchsia": discord.Color.fuchsia(),
        "gold": discord.Color.gold(),
        "green": discord.Color.green(),
        "grey": discord.Color.greyple(),
        "lightgrey": discord.Color.light_grey(),
        "lightergrey": discord.Color.lighter_grey(),
        "magenta": discord.Color.magenta(),
        "og_blurple": discord.Color(0x4F5899),
        "og_darkblurple": discord.Color(0x3A4C8A),
        "og_green": discord.Color(0x23A559),
        "og_red": discord.Color(0xDA373C),
        "og_yellow": discord.Color(0xF0B232),
        "purple": discord.Color.purple(),
        "random": discord.Color.random(),
        "red": discord.Color.red(),
        "teal": discord.Color.teal(),
        "yellow": discord.Color.yellow(),
    }
    
    normalized = color_name.strip().lower().replace(" ", "")
    
    # Check if it's a hex color
    if normalized.startswith("#"):
        try:
            hex_val = int(normalized[1:], 16)
            return discord.Color(hex_val)
        except ValueError:
            pass
    
    if normalized in color_map:
        return color_map[normalized]
    
    # Default to dark blue if not found
    logger.warning("Unknown color '%s', defaulting to DarkBlue", color_name)
    return discord.Color.dark_blue()


# =============================================================================
# AI-Callable Slash Command Wrappers
# =============================================================================

async def send_card(
    channel_id: int,
    title: str,
    content: str,
    color: str = "DarkBlue",
) -> str:
    """Send a formatted embed card to a channel.
    
    Args:
        channel_id: The Discord channel ID to send to.
        title: The embed title.
        content: The embed body text.
        color: Color name (e.g., 'DarkBlue', 'Red') or hex (e.g., '#FF0000').
        
    Returns:
        A summary string of what was sent.
    """
    logger.info("send_card: channel=%s, title='%s', color=%s", channel_id, title, color)
    
    try:
        channel = client.get_channel(channel_id)
        if not channel:
            return f"Error: Could not find channel {channel_id}."
        
        embed = discord.Embed(
            title=title,
            description=content,
            color=_color_from_name(color),
        )
        
        message = await channel.send(embed=embed)
        logger.info("send_card: Sent message %s to channel %s", message.id, channel_id)
        return f"Sent card '{title}' to channel {channel_id} as message {message.id}."
    
    except discord.HTTPException as e:
        logger.error("send_card: HTTP error sending to channel %s: %s", channel_id, e)
        return f"Error sending card: HTTP error {e}"
    except Exception as e:
        logger.error("send_card: Unexpected error sending to channel %s: %s", channel_id, e)
        return f"Error sending card: {e}"


async def roll_dice(dice_string: str) -> str:
    """Roll dice using standard notation (e.g. '2d6+3', '1d20').
    
    Args:
        dice_string: Dice notation string. Supports formats like:
            - '2d6+3' (two 6-sided dice plus 3)
            - '1d20' (one 20-sided die)
            - 'd4' (one 4-sided die, shorthand)
            - '2d6+1d8+5' (multiple groups)
            
    Returns:
        Human-readable result with individual dice and total.
    """
    logger.info("roll_dice: Rolling '%s'", dice_string)
    
    try:
        # Extract any bonus (e.g., +3 from '2d6+3')
        bonus = 0
        bonus_match = re.search(r'\+(\d+)$', dice_string.strip(), re.IGNORECASE)
        if bonus_match:
            bonus = int(bonus_match.group(1))
            dice_string = dice_string[:bonus_match.start()].strip()
        
        dice_groups = _parse_dice_string(dice_string)
        
        all_rolls = []
        group_summaries = []
        grand_total = bonus
        
        for count, sides in dice_groups:
            rolls = _roll_dice(count, sides)
            all_rolls.extend(rolls)
            group_total = sum(rolls)
            grand_total += group_total
            
            if count == 1:
                group_summaries.append(f"{sides}-sided: [{rolls[0]}]")
            else:
                group_summaries.append(f"{count}d{sides}: [{', '.join(str(r) for r in rolls)}] = {group_total}")
        
        if bonus > 0:
            group_summaries.append(f"bonus: {bonus}")
        
        result = f"Rolling {dice_string!r}:\n"
        result += " | ".join(group_summaries)
        result += f"\nTotal: {grand_total}"
        
        logger.info("roll_dice: Result for '%s' = %d", dice_string, grand_total)
        return result
    
    except ValueError as e:
        logger.warning("roll_dice: Invalid dice string '%s': %s", dice_string, e)
        return f"Invalid dice string: {e}"
    except Exception as e:
        logger.error("roll_dice: Unexpected error rolling '%s': %s", dice_string, e)
        return f"Error rolling dice: {e}"


async def context_add(thread_id: int, text: str) -> str:
    """Add text to the active memory context for a thread.
    
    Args:
        thread_id: The Discord thread ID to add context to.
        text: The text to add to the memory context.
        
    Returns:
        A summary string of what was done.
    """
    logger.info("context_add: thread=%s, text_length=%d", thread_id, len(text))
    
    try:
        # Get the thread to find its parent channel and category
        thread = client.get_channel(thread_id)
        if not thread:
            return f"Error: Could not find thread {thread_id}."
        
        if not isinstance(thread, discord.Thread):
            return f"Error: Channel {thread_id} is not a thread."
        
        # Get the parent channel (needed for category context)
        parent_channel = thread.parent
        if not parent_channel:
            return f"Error: Thread {thread_id} has no parent channel."
        
        category = parent_channel.category
        if not category:
            return f"Error: Thread {thread_id} has no category context."
        
        # Get the assigned memory for this thread
        memory_id = await asyncio.to_thread(
            get_assigned_memory_id,
            int(parent_channel.id),
            int(category.id),
            int(thread_id),
        )
        
        if not memory_id:
            return f"Error: No memory assigned to thread {thread_id}."
        
        # Build context entry message to send to the context channel
        # The actual context storage is handled by Discord messages in the context channel
        entry_text = f"[CONTEXT Add]\n{text}"
        
        # Find the context channel in the category
        context_channel = discord.utils.get(category.text_channels, name="context")
        if not context_channel:
            return f"Error: Context channel not found in category {category.name}."
        
        # Send the context entry
        message = await context_channel.send(entry_text)
        
        logger.info("context_add: Added context to thread %s, message %s", thread_id, message.id)
        return f"Added text to thread {thread_id} context. Stored in channel {context_channel.name} as message {message.id}."
    
    except discord.HTTPException as e:
        logger.error("context_add: HTTP error for thread %s: %s", thread_id, e)
        return f"Error adding context: HTTP error {e}"
    except Exception as e:
        logger.error("context_add: Unexpected error for thread %s: %s", thread_id, e)
        return f"Error adding context: {e}"


async def get_context(thread_id: int | str) -> str:
    """Get the current memory context for a thread.

    Args:
        thread_id: The Discord thread ID to get context for (int or numeric string).

    Returns:
        The current context text for the thread.
    """
    # Accept both int and string (Gemini may pass either)
    try:
        thread_id = int(thread_id)
    except (ValueError, TypeError):
        return f"Error: Invalid thread ID '{thread_id}'. Expected a numeric Discord thread ID (e.g. 1505887942822858764)."

    logger.info("get_context: thread=%s", thread_id)

    try:
        # Get the thread to find its parent channel and category
        thread = client.get_channel(thread_id)
        if not thread:
            return f"Error: Could not find thread {thread_id}."
        
        if not isinstance(thread, discord.Thread):
            return f"Error: Channel {thread_id} is not a thread."
        
        parent_channel = thread.parent
        if not parent_channel:
            return f"Error: Thread {thread_id} has no parent channel."
        
        category = parent_channel.category
        if not category:
            return f"Error: Thread {thread_id} has no category context."
        
        # Get the assigned memory for this thread
        memory_id = await asyncio.to_thread(
            get_assigned_memory_id,
            int(parent_channel.id),
            int(category.id),
            int(thread_id),
        )
        
        if not memory_id:
            return f"No memory assigned to thread {thread_id}."
        
        # Find the context channel
        context_channel = discord.utils.get(category.text_channels, name="context")
        if not context_channel:
            return f"Context channel not found in category {category.name}."
        
        # Collect context messages from the channel
        # Look for messages tagged with the thread's context
        context_messages = []
        async for message in context_channel.history(limit=50):
            if message.content.startswith("[CONTEXT"):
                context_messages.append(message.content)
        
        if not context_messages:
            return f"No context found for thread {thread_id}."
        
        return "Context for thread {thread_id}:\n\n" + "\n---\n".join(context_messages)
    
    except discord.HTTPException as e:
        logger.error("get_context: HTTP error for thread %s: %s", thread_id, e)
        return f"Error getting context: HTTP error {e}"
    except Exception as e:
        logger.error("get_context: Unexpected error for thread %s: %s", thread_id, e)
        return f"Error getting context: {e}"


async def reference_card(message_id: int, channel_id: int | None = None) -> str:
    """Look up a message by ID and return a summary of what card/data it contains.
    
    Args:
        message_id: The Discord message ID to look up.
        channel_id: Optional: The Discord channel ID. Required if not in current context.
        
    Returns:
        A formatted summary of the message's content.
    """
    from discord_app.message_tools import get_message_content
    
    logger.info("reference_card: message=%s, channel=%s", message_id, channel_id)
    
    if channel_id is None:
        return "Error: channel_id is required for reference_card."
    
    try:
        content = await get_message_content(message_id, channel_id)
        
        if not content["success"]:
            return f"Error: Could not fetch message {message_id}: {content.get('error', 'Unknown error')}"
        
        # Build a summary
        summary_parts = [f"Message {message_id} from {content['author']} at {content['timestamp']}"]
        
        if content["text"]:
            summary_parts.append(f"Text: {content['text'][:500]}")
            if len(content["text"]) > 500:
                summary_parts[-1] += "..."
        
        if content["embeds"]:
            for i, embed in enumerate(content["embeds"], 1):
                if embed.get("title"):
                    summary_parts.append(f"Embed {i} - Title: {embed['title']}")
                if embed.get("description"):
                    desc = embed['description'][:300]
                    summary_parts.append(f"Embed {i} - Description: {desc}")
                    if len(embed['description']) > 300:
                        summary_parts[-1] += "..."
                if embed.get("fields"):
                    summary_parts.append(f"Embed {i} - Fields: {len(embed['fields'])} field(s)")
        
        if content["attachments"]:
            summary_parts.append(f"Attachments: {len(content['attachments'])} file(s)")
            for att in content["attachments"]:
                summary_parts.append(f"  - {att['filename']} ({att.get('size', '?')} bytes)")
        
        return "\n".join(summary_parts)
    
    except Exception as e:
        logger.error("reference_card: Error fetching message %s: %s", message_id, e)
        return f"Error referencing card: {e}"


# =============================================================================
# Gemini Function Declarations for AI Tool Use
# =============================================================================

SLASH_TOOLS_DECLARATION = [
    types.FunctionDeclaration(
        name="send_card",
        description="Send a formatted embed card to a Discord channel.",
        parameters=types.Schema(
            type="object",
            properties={
                "channel_id": types.Schema(type="string", description="The Discord channel ID to send to."),
                "title": types.Schema(type="string", description="The embed title."),
                "content": types.Schema(type="string", description="The embed body text."),
                "color": types.Schema(type="string", description="Optional: Color name (e.g., 'DarkBlue', 'Red') or hex (e.g., '#FF0000'). Default 'DarkBlue'."),
            },
            required=["channel_id", "title", "content"],
        ),
    ),
    types.FunctionDeclaration(
        name="roll_dice",
        description="Roll dice using standard notation like '2d6+3' or '1d20'.",
        parameters=types.Schema(
            type="object",
            properties={
                "dice_string": types.Schema(type="string", description="Dice notation (e.g., '2d6+3', '1d20', 'd4'). Supports multiple groups like '2d6+1d8+5'."),
            },
            required=["dice_string"],
        ),
    ),
    types.FunctionDeclaration(
        name="context_add",
        description="Add text to the active memory context for a Discord thread. IMPORTANT: thread_id must be a numeric Discord thread ID (e.g. '1505887942822858764'), NOT a memory name like 'test2new'.",
        parameters=types.Schema(
            type="object",
            properties={
                "thread_id": types.Schema(type="string", description="The Discord thread ID as a numeric string (e.g. '1505887942822858764'). Do NOT use memory names."),
                "text": types.Schema(type="string", description="The text to add to the memory context."),
            },
            required=["thread_id", "text"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_context",
        description="Get the current memory context for a Discord thread. IMPORTANT: thread_id must be a numeric Discord thread ID (e.g. '1505887942822858764'), NOT a memory name like 'test2new'.",
        parameters=types.Schema(
            type="object",
            properties={
                "thread_id": types.Schema(type="string", description="The Discord thread ID as a numeric string (e.g. '1505887942822858764'). Do NOT use memory names like 'test2new'."),
            },
            required=["thread_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="reference_card",
        description="Look up a Discord message by ID and return a summary of its content.",
        parameters=types.Schema(
            type="object",
            properties={
                "message_id": types.Schema(type="string", description="The Discord message ID."),
                "channel_id": types.Schema(type="string", description="The Discord channel ID where the message exists."),
            },
            required=["message_id", "channel_id"],
        ),
    ),
]