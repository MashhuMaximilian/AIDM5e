"""Message editing, replying, and forwarding tools for the AIDM5e Discord bot.

All functions use text-based tool invocation markers: [AIDM-TOOL: name | arg1=value | arg2=value]
"""

import asyncio
import logging
import re
from typing import Any

from google.genai import types
import discord

from config import client


logger = logging.getLogger(__name__)


# Truncation markers that indicate an abruptly ended description
_TRUNCATION_MARKERS = ('---', '### ', '`', '**', '[')


def _detect_and_merge_truncated_description(
    new_description: str | None,
    current_description: str | None,
) -> str | None:
    """Detect if new_description appears truncated and merge with current if needed.

    A description is considered truncated if:
    1. It ends with incomplete markers ('---', '### ', '`', '**', '[')
    2. OR it is less than 25% of current_description's length (i.e., AI sent a partial
       update like just the HP line without the full card — we must merge to avoid
       losing the rest of the card)
    3. OR new_description is a strict prefix of current_description (matching byte-for-byte
       at the start) and current_description doesn't end with truncation markers (this
       catches the case where the AI started generating the new card but stopped mid-output)

    When truncated, finds the longest common prefix and appends the missing tail
    from current_description, then closes any unclosed code blocks.

    However, when lcp_end == 0 (no shared prefix) and the new description is a
    short partial (just one section like HP bar), blind concatenation would corrupt
    the card by prepending the partial to the full card. In this case, we detect
    which section the partial belongs to and REPLACE only that section in current,
    rather than blindly prepending.

    Returns the (possibly merged) description to use.
    """
    if new_description is None:
        return current_description

    if not current_description:
        return new_description

    ends_incomplete = any(new_description.endswith(marker) for marker in _TRUNCATION_MARKERS)
    # If new is less than 25% of current, it's a partial update — must merge to avoid data loss
    too_short = len(new_description) < 0.25 * len(current_description)

    # True if new is a strict prefix of current (byte-for-byte match at start, then diverges)
    new_is_prefix_of_current = (
        len(new_description) < len(current_description)
        and current_description.startswith(new_description)
    )

    # Truncated if:
    # - ends with incomplete markers (---, ###, `, etc.)
    # - OR too short relative to current (partial update like just HP line)
    # - OR new is a strict prefix of current (AI started writing new card but stopped)
    is_truncated = ends_incomplete or too_short or new_is_prefix_of_current

    if not is_truncated:
        return new_description

    # Find longest common prefix to determine where new diverges from current
    lcp_end = 0
    min_len = min(len(new_description), len(current_description))
    for i in range(min_len):
        if new_description[i] == current_description[i]:
            lcp_end = i + 1
        else:
            break

    # CASE: lcp_end == 0 with a short partial update.
    # Blind concatenation (partial + full card) would corrupt the card.
    # Instead, find which section the partial belongs to and replace only that section.
    if lcp_end == 0 and too_short and len(new_description) < 200:
        partial = new_description.strip()

        # Try to find a matching section in current by looking for the partial's
        # first significant line. Check for section headers or HP/resource patterns.
        # Strategy: find lines in current that partially match the beginning of partial.
        partial_first_line = partial.split('\n')[0].strip()

        if partial_first_line:
            # For HP/resource partials: find the line in current that starts the same way
            # and replace from there to the next section boundary (---, ###, or end)
            current_lines = current_description.split('\n')
            for i, line in enumerate(current_lines):
                # Check if this line starts the same way as the partial's first line
                # (allowing for leading whitespace/bullets differences)
                line_stripped = line.strip()
                if line_stripped and partial_first_line.strip():
                    # Check if partial's first line appears as a substring at the start of this line
                    if line_stripped.startswith(partial_first_line.strip()[:10]) or \
                       (len(partial_first_line) > 5 and partial_first_line[:10] in line_stripped):
                        # Found the section. Replace from this line to the next section marker or end.
                        # Find next section boundary
                        j = i + 1
                        section_end = len(current_lines)
                        while j < len(current_lines):
                            next_line = current_lines[j].strip()
                            if next_line.startswith('---') or next_line.startswith('### '):
                                section_end = j
                                break
                            j += 1

                        # Replace section with partial
                        new_section = partial.rstrip('\n')
                        merged_lines = current_lines[:i] + [new_section] + current_lines[section_end:]
                        merged = '\n'.join(merged_lines)

                        # Fix unclosed code blocks
                        if merged.count('```') % 2 != 0:
                            merged += '\n```'

                        return merged

        # If we couldn't find a matching section, preserve current entirely
        # Don't risk corruption by blindly concatenating
        return current_description

    # Standard case: merge using longest common prefix
    # Append the missing tail from current
    merged = new_description + current_description[lcp_end:]

    # Fix unclosed code blocks: if odd number of ``` in merged, append closing ```
    if merged.count('```') % 2 != 0:
        merged += '\n```'

    return merged


# Pattern to match tool invocations like [AIDM-TOOL: edit_message | message_id=123456 | new_content=Hello world]
TOOL_INVOCATION_RE = re.compile(
    r"\[AIDM-TOOL:\s*(\w+)\s*(?:\|(?:\s*\w+\s*=\s*(?:[^|\]]+))*)?\]",
    re.IGNORECASE,
)


async def edit_message(
    message_id: int,
    new_content: str,
    channel_id: int,
    *,
    embed_title: str | None = None,
    embed_description: str | None = None,
    embed_color: int | None = None,
) -> bool:
    """Edit an existing message in a channel, including optionally updating its embed.

    Args:
        message_id: The Discord message ID to edit.
        new_content: The new content for the message (plain text, the line above the card).
        channel_id: The channel ID where the message exists.
        embed_title: Optional new title for the embed card.
        embed_description: Optional new description/body for the embed card.
        embed_color: Optional color as an integer (e.g. 0x1f8b4c for green, 0xe74c3c for red).
                     Common colors: DarkGreen=0x1f8b4c, Red=0xe74c3c, DarkBlue=0x3498db, Gold=0xf1c40f.

    Returns:
        True if the edit was successful, False otherwise.
    """
    try:
        channel = client.get_channel(channel_id)
        if not channel:
            logger.error("edit_message: Could not find channel %s", channel_id)
            return False

        message = await channel.fetch_message(message_id)

        edit_kwargs: dict[str, str | discord.Embed | None] = {"content": new_content}

        # Build updated embed if any embed params are provided
        embed: discord.Embed | None = None
        if embed_title is not None or embed_description is not None:
            current_embed = message.embeds[0] if message.embeds else None
            embed = discord.Embed()
            if current_embed:
                # Title: preserve current title only when None is explicitly passed
                embed.title = current_embed.title if embed_title is None else embed_title
                embed.description = _detect_and_merge_truncated_description(
                    embed_description, current_embed.description
                )
                embed.color = discord.Color(embed_color) if embed_color is not None else current_embed.color
                # Always preserve fields from current embed when we have one
                for field in current_embed.fields:
                        embed.add_field(name=field.name, value=field.value, inline=field.inline)
                if current_embed.footer:
                    embed.set_footer(text=current_embed.footer.text, icon_url=current_embed.footer.icon_url)
                if current_embed.thumbnail:
                    embed.set_thumbnail(url=current_embed.thumbnail.url)
                if current_embed.image:
                    embed.set_image(url=current_embed.image.url)
            else:
                embed.title = embed_title or "Card"
                embed.description = embed_description or new_content or "No content"
                if embed_color is not None:
                    embed.color = discord.Color(embed_color)
            edit_kwargs["embed"] = embed

        await message.edit(**edit_kwargs)
        logger.info("Edited message %s in channel %s (embed=%s)", message_id, channel_id, bool(embed))
        return True

    except discord.NotFound:
        logger.warning("edit_message: Message %s not found in channel %s", message_id, channel_id)
        return False
    except discord.HTTPException as e:
        logger.error("edit_message: HTTP error editing message %s in channel %s: %s", message_id, channel_id, e)
        return False
    except Exception as e:
        logger.error("edit_message: Unexpected error editing message %s in channel %s: %s", message_id, channel_id, e)
        return False


async def reply_to_message(
    message_id: int,
    content: str,
    channel_id: int,
    mention: bool = False,
) -> discord.Message | None:
    """Reply to an existing message.
    
    Args:
        message_id: The Discord message ID to reply to.
        content: The reply content.
        channel_id: The channel ID where the message exists.
        mention: Whether to mention the original message author.
    
    Returns:
        The sent Message object, or None if failed.
    """
    try:
        channel = client.get_channel(channel_id)
        if not channel:
            logger.error("reply_to_message: Could not find channel %s", channel_id)
            return None
        
        original_message = await channel.fetch_message(message_id)
        reply = await channel.send(
            content=content,
            reference=original_message.to_reference(),
            mention_author=mention,
        )
        logger.info("Replied to message %s in channel %s with message %s", message_id, channel_id, reply.id)
        return reply
    
    except discord.NotFound:
        logger.warning("reply_to_message: Message %s not found in channel %s", message_id, channel_id)
        return None
    except discord.HTTPException as e:
        logger.error("reply_to_message: HTTP error replying to message %s in channel %s: %s", message_id, channel_id, e)
        return None
    except Exception as e:
        logger.error("reply_to_message: Unexpected error replying to message %s in channel %s: %s", message_id, channel_id, e)
        return None


async def forward_message(
    message_id: int,
    target_channel_id: int,
    channel_id: int,
    include_context: bool = True,
) -> discord.Message | None:
    """Forward a message to another channel.
    
    Args:
        message_id: The source message ID to forward.
        target_channel_id: The target channel ID to forward to.
        channel_id: The source channel ID where the message exists.
        include_context: Whether to include author and timestamp context.
    
    Returns:
        The forwarded Message object, or None if failed.
    """
    try:
        source_channel = client.get_channel(channel_id)
        if not source_channel:
            logger.error("forward_message: Could not find source channel %s", channel_id)
            return None
        
        target_channel = client.get_channel(target_channel_id)
        if not target_channel:
            logger.error("forward_message: Could not find target channel %s", target_channel_id)
            return None
        
        original_message = await source_channel.fetch_message(message_id)
        
        # Build forward content
        content_parts = []
        if include_context:
            author_name = original_message.author.display_name
            timestamp = original_message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content_parts.append(f"Forwarded from {author_name} ({timestamp}):")
            content_parts.append("")
        
        if original_message.content:
            content_parts.append(original_message.content)
        
        # Handle embeds
        embeds = list(original_message.embeds) if original_message.embeds else []
        
        # Handle attachments
        attachments = []
        for attachment in original_message.attachments:
            attachments.append(f"[Attached file: {attachment.filename}]({attachment.url})")
        
        if attachments:
            content_parts.append("")
            content_parts.extend(attachments)
        
        full_content = "\n".join(content_parts)
        
        if embeds:
            forwarded = await target_channel.send(content=full_content, embeds=embeds)
        else:
            forwarded = await target_channel.send(full_content)
        
        logger.info("Forwarded message %s from channel %s to channel %s as message %s",
                    message_id, channel_id, target_channel_id, forwarded.id)
        return forwarded
    
    except discord.NotFound:
        logger.warning("forward_message: Message %s or channel not found", message_id)
        return None
    except discord.HTTPException as e:
        logger.error("forward_message: HTTP error forwarding message %s: %s", message_id, e)
        return None
    except Exception as e:
        logger.error("forward_message: Unexpected error forwarding message %s: %s", message_id, e)
        return None


async def get_message_content(message_id: int, channel_id: int) -> dict[str, Any]:
    """Get the content and metadata of a message.
    
    Args:
        message_id: The Discord message ID.
        channel_id: The channel ID where the message exists.
    
    Returns:
        A dict containing:
        - text: The message text content
        - embeds: List of embed dicts
        - attachments: List of attachment URLs
        - author: Author name
        - author_id: Author ID
        - timestamp: ISO timestamp string
        - success: Whether the fetch was successful
        - error: Error message if failed
    """
    result = {
        "text": "",
        "embeds": [],
        "attachments": [],
        "author": "",
        "author_id": None,
        "timestamp": "",
        "success": False,
        "error": None,
    }
    
    try:
        channel = client.get_channel(channel_id)
        if not channel:
            result["error"] = f"Could not find channel {channel_id}"
            logger.error("get_message_content: %s", result["error"])
            return result
        
        message = await channel.fetch_message(message_id)
        
        result["text"] = message.content or ""
        result["author"] = message.author.display_name
        result["author_id"] = message.author.id
        result["timestamp"] = message.created_at.isoformat()
        result["success"] = True
        
        for embed in message.embeds:
            embed_dict = {
                "title": embed.title,
                "description": embed.description,
                "color": embed.color.value if embed.color else None,
                "fields": [{"name": f.name, "value": f.value, "inline": f.inline} for f in embed.fields] if embed.fields else [],
            }
            result["embeds"].append(embed_dict)
        
        for attachment in message.attachments:
            result["attachments"].append({
                "filename": attachment.filename,
                "url": attachment.url,
                "size": attachment.size,
            })
        
        logger.info("Fetched message %s content from channel %s", message_id, channel_id)
        return result
    
    except discord.NotFound:
        result["error"] = f"Message {message_id} not found in channel {channel_id}"
        logger.warning("get_message_content: %s", result["error"])
        return result
    except discord.HTTPException as e:
        result["error"] = f"HTTP error fetching message: {e}"
        logger.error("get_message_content: %s", result["error"])
        return result
    except Exception as e:
        result["error"] = f"Unexpected error: {e}"
        logger.error("get_message_content: %s", result["error"])
        return result


def parse_ai_tool_invocation(text: str) -> list[dict[str, Any]]:
    """Parse tool invocations from AI response text.
    
    Args:
        text: The AI response text that may contain tool invocations.
    
    Returns:
        A list of dicts, each containing:
        - name: The tool name (e.g., "edit_message")
        - args: Dict of argument name -> value
        - raw: The raw invocation string
        - start: Start index in text
        - end: End index in text
    """
    invocations = []
    
    for match in TOOL_INVOCATION_RE.finditer(text):
        name = match.group(1).strip().lower()
        raw = match.group(0)
        
        args: dict[str, str] = {}
        args_str = match.group(0)[match.end(1):].strip()
        
        if args_str.startswith("|"):
            args_str = args_str[1:].strip()
        
        if args_str:
            arg_matches = re.findall(r"(\w+)\s*=\s*([^|\]]+)", args_str, re.IGNORECASE)
            for arg_name, arg_value in arg_matches:
                args[arg_name.strip().lower()] = arg_value.strip()
        
        invocations.append({
            "name": name,
            "args": args,
            "raw": raw,
            "start": match.start(),
            "end": match.end(),
        })
    
    return invocations


async def execute_tool_invocations(invocations: list[dict[str, Any]], channel: discord.abc.Messageable) -> str:
    """Execute parsed tool invocations and return a summary.
    
    Args:
        invocations: List of parsed invocations from parse_ai_tool_invocation.
        channel: The Discord channel to use for context.
    
    Returns:
        A summary string of what was executed and the results.
    """
    if not invocations:
        return ""
    
    results = []
    
    for invocation in invocations:
        name = invocation["name"]
        args = invocation["args"]
        
        try:
            if name == "edit_message":
                message_id = int(args.get("message_id", 0))
                new_content = args.get("new_content", "")
                channel_id = int(args.get("channel_id", channel.id))
                
                success = await edit_message(message_id, new_content, channel_id)
                if success:
                    results.append(f"Edited message {message_id}")
                else:
                    results.append(f"Failed to edit message {message_id}")
            
            elif name == "reply_to_message":
                message_id = int(args.get("message_id", 0))
                content = args.get("content", "")
                channel_id = int(args.get("channel_id", channel.id))
                mention = args.get("mention", "").lower() in ("true", "1", "yes")
                
                reply = await reply_to_message(message_id, content, channel_id, mention)
                if reply:
                    results.append(f"Replied to message {message_id} with message {reply.id}")
                else:
                    results.append(f"Failed to reply to message {message_id}")
            
            elif name == "forward_message":
                message_id = int(args.get("message_id", 0))
                target_channel_id = int(args.get("target_channel_id", 0))
                source_channel_id = int(args.get("channel_id", channel.id))
                
                forwarded = await forward_message(message_id, target_channel_id, source_channel_id)
                if forwarded:
                    results.append(f"Forwarded message {message_id} to channel {target_channel_id}")
                else:
                    results.append(f"Failed to forward message {message_id}")
            
            elif name == "get_message_content":
                message_id = int(args.get("message_id", 0))
                source_channel_id = int(args.get("channel_id", channel.id))
                
                content = await get_message_content(message_id, source_channel_id)
                if content["success"]:
                    # Include full card content — embed descriptions are critical for card edits
                    display_parts = [f"Message ID: {message_id}"]
                    if content.get("text"):
                        display_parts.append(f"Message content:\n{content['text']}")
                    # Include full embed descriptions (not truncated — AI needs the full card text)
                    if content.get("embeds"):
                        for i, embed in enumerate(content["embeds"]):
                            if embed.get("title"):
                                display_parts.append(f"Embed {i+1} title: {embed['title']}")
                            if embed.get("description"):
                                display_parts.append(f"Embed {i+1} description:\n{embed['description']}")
                            if embed.get("color"):
                                display_parts.append(f"Embed {i+1} color: #{embed['color']:06x}")
                    results.append("\n".join(display_parts))
                else:
                    results.append(f"Failed to fetch message {message_id}: {content.get('error')}")
            
            else:
                results.append(f"Unknown tool: {name}")
        
        except ValueError as e:
            results.append(f"Invalid arguments for {name}: {e}")
        except Exception as e:
            results.append(f"Error executing {name}: {e}")
    
    summary = "Tool execution results:\n" + "\n".join(f"- {r}" for r in results)
    logger.info("Executed %d tool invocations: %s", len(invocations), results)

    return summary


# =============================================================================
# Gemini Function Declarations for AI Tool Use
# =============================================================================

TOOLS_DECLARATION = [
    types.FunctionDeclaration(
        name="edit_message",
        description="""Edit an existing message AND its embed card in a Discord channel.

HOW TO USE FOR CHARACTER CARD EDITS — FOLLOW THIS EXACT SEQUENCE:
1. FIRST call get_message_content to read the current card
2. The card body will be returned with a "--- CARD BODY ---" section
3. Copy the EXACT text from the "Body:" section — do not summarize or rephrase it
4. Modify ONLY the specific field the user requested (e.g. HP value, conditions list)
5. Paste the copied body into embed_description and only change what was asked
6. Call edit_message with the complete embed_description

CRITICAL — DO NOT HALLUCINATE VALUES:
- Do NOT generate any stat, number, or value that wasn't in the card you read
- Do NOT recalculate HP, AC, ability scores, or any other field
- Copy every value directly from the card body you read
- If you see "HP: 130/130" in the card, you MUST preserve "130/130" for all unchanged fields

CORRECT EXAMPLE:
  - Card body shows: "HP: 130/130 | AC: 16 | STR: 18"
  - User says: "Veton took 80 damage"
  - You call: edit_message(message_id=..., embed_description="...HP: 50/130...AC: 16...STR: 18...")
  - Notice HP changed to 50/130 but AC and STR are copied exactly from the card

INCORRECT EXAMPLE:
  - Card body shows: "HP: 130/130 | AC: 16 | STR: 18"
  - User says: "Veton took 80 damage"
  - You call: edit_message(message_id=..., embed_description="...HP: 50/180...AC: 15...STR: 16...")
  - WRONG: AC and STR values were invented, not copied from the card

SEND THE FULL CARD: The embed_description must be the complete card body with only the requested changes. Never send only the changed fields.

If the user says "add Poisoned condition" — copy the entire card body and add Poisoned to the conditions section, keeping everything else identical.
If the user says "Veton took 60 damage" — copy the entire card body, reduce only the HP value, keep every other field exactly the same.""",
        parameters=types.Schema(
            type="object",
            properties={
                "message_id": types.Schema(type="string", description="The Discord message ID to edit."),
                "new_content": types.Schema(type="string", description="The new plain-text content for the message (line above the card)."),
                "channel_id": types.Schema(type="string", description="Optional: The Discord channel ID where the message exists. Defaults to current channel."),
                "embed_title": types.Schema(type="string", description="Optional: New title for the embed card."),
                "embed_description": types.Schema(type="string", description="Optional: New body/description text for the embed card. Must be the complete updated card — copy all existing content and only modify what the user requested."),
                "embed_color": types.Schema(type="string", description="Optional: Color as hex string (e.g. '0x1f8b4c' for green, '0xe74c3c' for red, '0x3498db' for blue)."),
            },
            required=["message_id", "new_content"],
        ),
    ),
    types.FunctionDeclaration(
        name="reply_to_message",
        description="Reply to an existing Discord message.",
        parameters=types.Schema(
            type="object",
            properties={
                "message_id": types.Schema(type="string", description="The Discord message ID to reply to."),
                "content": types.Schema(type="string", description="The reply content."),
                "channel_id": types.Schema(type="string", description="Optional: The Discord channel ID. Defaults to current channel."),
                "mention": types.Schema(type="boolean", description="Optional: Whether to mention the original message author. Default false."),
            },
            required=["message_id", "content"],
        ),
    ),
    types.FunctionDeclaration(
        name="forward_message",
        description="Forward a Discord message to another channel.",
        parameters=types.Schema(
            type="object",
            properties={
                "message_id": types.Schema(type="string", description="The source message ID to forward."),
                "target_channel_id": types.Schema(type="string", description="The target channel ID to forward to."),
                "channel_id": types.Schema(type="string", description="Optional: The source channel ID. Defaults to current channel."),
            },
            required=["message_id", "target_channel_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_message_content",
        description="Read a Discord message's content and metadata.",
        parameters=types.Schema(
            type="object",
            properties={
                "message_id": types.Schema(type="string", description="The Discord message ID."),
                "channel_id": types.Schema(type="string", description="Optional: The Discord channel ID. Defaults to current channel."),
            },
            required=["message_id"],
        ),
    ),
]
