"""Message editing, replying, and forwarding tools for the AIDM5e Discord bot.

All functions use text-based tool invocation markers: [AIDM-TOOL: name | arg1=value | arg2=value]
"""

import asyncio
import logging
import re
from typing import Any

import discord

from config import client


logger = logging.getLogger(__name__)


# Pattern to match tool invocations like [AIDM-TOOL: edit_message | message_id=123456 | new_content=Hello world]
TOOL_INVOCATION_RE = re.compile(
    r"\[AIDM-TOOL:\s*(\w+)\s*(?:\|(?:\s*\w+\s*=\s*(?:[^|\]]+))*)?\]",
    re.IGNORECASE,
)


async def edit_message(message_id: int, new_content: str, channel_id: int) -> bool:
    """Edit an existing message in a channel.
    
    Args:
        message_id: The Discord message ID to edit.
        new_content: The new content for the message.
        channel_id: The channel ID where the message exists.
    
    Returns:
        True if the edit was successful, False otherwise.
    """
    try:
        channel = client.get_channel(channel_id)
        if not channel:
            logger.error("edit_message: Could not find channel %s", channel_id)
            return False
        
        message = await channel.fetch_message(message_id)
        await message.edit(content=new_content)
        logger.info("Edited message %s in channel %s", message_id, channel_id)
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
                    preview = content["text"][:200] + "..." if len(content["text"]) > 200 else content["text"]
                    results.append(f"Fetched message {message_id}: {preview}")
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
