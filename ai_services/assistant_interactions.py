# assistant_interactions.py

import asyncio
import logging
from pathlib import Path

from google.genai import types

from ai_services.guild_api_keys import (
    raise_for_guild_gemini_exception,
    record_guild_gemini_key_success,
    use_guild_gemini_api_key,
)
from config import AIDM_PROMPT_PATH, client
from data_store.db_repository import get_guild_tools_mode, get_memory_name
from discord_app.shared_functions import send_response_in_chunks
from .gemini_client import gemini_client, ALL_TOOLS_DECLARATION


logger = logging.getLogger(__name__)


# Restricted tool set for the follow-up turn: only edit_message, no get_context
# This prevents the AI from "escaping" to get_context while still allowing it to call edit_message
def _build_restricted_tools() -> list:
    """Build a restricted tools list containing only edit_message declarations."""
    try:
        from discord_app.message_tools import TOOLS_DECLARATION
        edit_only = [d for d in TOOLS_DECLARATION if d.name == "edit_message"]
        if edit_only:
            return [types.Tool(function_declarations=edit_only)]
    except ImportError:
        pass
    return []


_FOLLOWUP_TOOLS = _build_restricted_tools()


_MESSAGE_TOOLS_PATH = Path(__file__).parent.parent / "prompts" / "system" / "message_tools_prompt.txt"
try:
    SYSTEM_PROMPT = AIDM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    _MESSAGE_TOOLS_PROMPT = _MESSAGE_TOOLS_PATH.read_text(encoding="utf-8").strip()
except FileNotFoundError:
    SYSTEM_PROMPT = "You are AIDM, an AI Dungeon Master for D&D 5e."
    _MESSAGE_TOOLS_PROMPT = ""


async def _execute_function_call(func_name: str, args: dict, channel) -> str:
    """Execute a Gemini function call and return the result string."""
    try:
        # Import actual functions from message_tools and slash_commands
        from discord_app.message_tools import (
            edit_message,
            reply_to_message,
            forward_message,
            get_message_content,
            find_message_by_title,
        )
        from discord_app.slash_commands import (
            send_card,
            roll_dice,
            context_add,
            get_context,
            reference_card,
        )

        func_map = {
            "edit_message": edit_message,
            "reply_to_message": reply_to_message,
            "forward_message": forward_message,
            "get_message_content": get_message_content,
            "find_message_by_title": find_message_by_title,
            "send_card": send_card,
            "roll_dice": roll_dice,
            "context_add": context_add,
            "get_context": get_context,
            "reference_card": reference_card,
        }

        func = func_map.get(func_name)
        if func is None:
            return f"Error: Unknown function '{func_name}'"

        # Call the function with appropriate args
        if func_name in ("edit_message",):
            message_id = int(args["message_id"])
            channel_id = int(args.get("channel_id", channel.id))
            new_content = args["new_content"]
            embed_title = args.get("embed_title")
            embed_description = args.get("embed_description")
            embed_color = None
            if args.get("embed_color"):
                try:
                    embed_color = int(args["embed_color"], 16)
                except ValueError:
                    pass
            result = await edit_message(
                message_id, new_content, channel_id,
                embed_title=embed_title,
                embed_description=embed_description,
                embed_color=embed_color,
            )
            if result:
                # Fetch the edited message to confirm actual content
                try:
                    ch = client.get_channel(channel_id)
                    msg = await ch.fetch_message(message_id)
                    return f"Successfully edited message {message_id}. New content: {msg.content}"
                except Exception:
                    return f"Successfully edited message {message_id}."
            else:
                return f"Failed to edit message {message_id}."
        elif func_name == "reply_to_message":
            result = await reply_to_message(
                int(args["message_id"]),
                args["content"],
                int(args.get("channel_id", channel.id)),
                args.get("mention", False),
            )
            return f"Replied to message {args['message_id']}" if result else f"Failed to reply to message {args['message_id']}"
        elif func_name == "forward_message":
            result = await forward_message(
                int(args["message_id"]),
                int(args["target_channel_id"]),
                int(args.get("channel_id", channel.id)),
            )
            return f"Forwarded message {args['message_id']} to channel {args['target_channel_id']}" if result else f"Failed to forward message {args['message_id']}"
        elif func_name == "get_message_content":
            result = await get_message_content(
                int(args["message_id"]),
                int(args.get("channel_id", channel.id)),
            )
            if not result["success"]:
                return f"Failed to get message {args['message_id']}: {result.get('error', 'unknown error')}"
            parts = [f"Message ID: {args['message_id']} | Author: {result['author']} | Timestamp: {result['timestamp']}"]
            if result.get("text"):
                parts.append(f"--- Message Text ---\n{result['text']}")
            # Include FULL card body with a clear header so the follow-up prompt can extract it
            if result.get("embeds"):
                for i, e in enumerate(result["embeds"]):
                    parts.append(f"\n--- CARD {i+1} BODY (copy this EXACTLY, only modify what user requested) ---")
                    if e.get("title"):
                        parts.append(f"Title: {e['title']}")
                    if e.get("description"):
                        parts.append(f"Body:\n{e['description']}")
                    if e.get("color"):
                        parts.append(f"Color: #{e['color']:06x}")
                    if e.get("fields"):
                        for f in e["fields"]:
                            parts.append(f"Field: {f['name']} = {f['value']}")
            parts.append(f"\n--- END CARD DATA ---")
            parts.append(f"Attachments: {len(result['attachments'])}")
            return "\n".join(parts)
        elif func_name == "find_message_by_title":
            result = await find_message_by_title(
                int(args.get("channel_id", channel.id)),
                args["title_search"],
            )
            if not result.get("found"):
                return f"Card not found: {result.get('error', 'unknown error')}"
            return (
                f"Found card: '{result['title']}' "
                f"with message_id={result['message_id']}. "
                f"Use edit_message(message_id={result['message_id']}, ...) to update it."
            )
        elif func_name == "send_card":
            result = await send_card(
                int(args["channel_id"]),
                args["title"],
                args["content"],
                args.get("color"),
            )
            return f"Sent card to channel {args['channel_id']}" if result else f"Failed to send card to channel {args['channel_id']}"
        elif func_name == "roll_dice":
            result = await roll_dice(args["dice_string"])
            return result
        elif func_name == "context_add":
            result = await context_add(
                int(args["thread_id"]),
                args["text"],
            )
            return result if result else f"Failed to add context to thread {args['thread_id']}"
        elif func_name == "get_context":
            result = await get_context(args["thread_id"])
            return result if result else f"No context found for thread {args['thread_id']}"
        elif func_name == "reference_card":
            result = await reference_card(
                int(args["message_id"]),
                int(args["channel_id"]),
            )
            return result if result else f"Failed to reference message {args['message_id']}"
        else:
            # Generic call for any other function
            result = await func(**args)
            return str(result) if result is not None else "Function executed"

    except Exception as exc:
        logger.error("Error executing function call '%s': %s", func_name, exc)
        return f"Error executing {func_name}: {exc}"


async def handle_function_calls(response, channel) -> str:
    """Handle function calls from Gemini response and return a summary of results.

    Args:
        response: The raw Gemini response object.
        channel: The Discord channel context.

    Returns:
        A string summary of all function call results.
    """
    function_calls = gemini_client.parse_function_calls(response)
    if not function_calls:
        return ""

    results = []
    for call in function_calls:
        func_name = call.get("name", "")
        args = call.get("args", {})
        logger.info("Executing function call: %s with args %s", func_name, args)
        result = await _execute_function_call(func_name, args, channel)
        results.append(f"[message_id: {args.get('message_id', 'unknown')}] {func_name}: {result}")

    return "\n".join(results)


async def handle_function_calls_from_dicts(calls: list[dict], channel) -> str:
    """Handle a list of already-parsed function call dicts and return a summary of results.

    Args:
        calls: List of dicts with 'name' and 'args' keys (already parsed from response).
        channel: The Discord channel context.

    Returns:
        A string summary of all function call results.
    """
    if not calls:
        return ""

    results = []
    for call in calls:
        func_name = call.get("name", "")
        args = call.get("args", {})
        logger.info("Executing function call from dicts: %s with args %s", func_name, args)
        result = await _execute_function_call(func_name, args, channel)
        results.append(f"[message_id: {args.get('message_id', 'unknown')}] {func_name}: {result}")

    return "\n".join(results)


def _normalize_user_message(user_message) -> tuple[str, list[str]]:
    """Normalize user message into (text, image_urls) tuple.
    
    Returns the cleaned text and any extracted image URLs for proper
    Gemini vision processing (not text URLs).
    """
    image_urls: list[str] = []
    text_parts: list[str] = []

    if isinstance(user_message, str):
        return user_message, []

    if isinstance(user_message, list):
        for item in user_message:
            if not isinstance(item, dict):
                text_parts.append(str(item))
                continue
            item_type = item.get("type")
            if item_type == "text":
                text_parts.append(item.get("text", ""))
            elif item_type == "image_url":
                image_url = item.get("image_url", {}).get("url")
                if image_url:
                    image_urls.append(image_url)
        return "\n".join(part for part in text_parts if part), image_urls

    return str(user_message), []


def _build_prompt(
    memory_name: str | None,
    user_message: str,
    context_block: str | None = None,
    conversation_history: str | None = None,
) -> str:
    memory_label = memory_name or "unassigned"
    parts = []

    if conversation_history:
        parts.append(
            f"--- Recent Conversation ---\n{conversation_history}\n--- End Recent Conversation ---\n"
        )

    parts.append(f"Current memory bucket: {memory_label}")
    parts.append("Use the assigned memory bucket, conversation history, and the current request.\n")

    if context_block:
        parts.append(
            f"Campaign reference context:\n{context_block}\n\n"
            "Use campaign reference context only when it is relevant to the current request. "
            "If the memory/current request and the campaign context conflict, say so clearly instead of silently merging them.\n"
        )

    parts.append(f"Current user request:\n{user_message}")
    return "\n".join(parts)


def _compose_system_prompt(system_prompt: str | None = None) -> str:
    parts = []
    if SYSTEM_PROMPT:
        parts.append(SYSTEM_PROMPT)
    if _MESSAGE_TOOLS_PROMPT:
        parts.append(_MESSAGE_TOOLS_PROMPT)
    if system_prompt:
        parts.append(system_prompt.strip())
    return "\n\n".join(parts)


async def get_assistant_response(
    user_message,
    channel_id,
    category_id=None,
    thread_id=None,
    assigned_memory=None,
    send_message=False,
    model_name=None,
    context_block: str | None = None,
    system_prompt: str | None = None,
    conversation_history: str | None = None,
    use_reasoning: bool = False,
    thinking_budget: int = 1024,
    image_urls: list | None = None,
):
    try:
        target_id = thread_id or channel_id
        channel = client.get_channel(target_id)
        if channel is None:
            error_message = f"Error: Channel with ID {target_id} not found."
            logger.error(error_message)
            return error_message

        if not assigned_memory:
            error_message = "Assigned memory ID is invalid or empty."
            logger.error(error_message)
            return error_message

        normalized_message, parsed_image_urls = _normalize_user_message(user_message)
        # Prefer parsed URLs from structured message, fall back to explicit parameter
        all_image_urls = parsed_image_urls if parsed_image_urls else (image_urls or [])
        logger.debug("Image URLs being sent to Gemini: explicit=%s, parsed=%s, merged=%s", image_urls, parsed_image_urls, all_image_urls)
        memory_name = await asyncio.to_thread(get_memory_name, assigned_memory)
        prompt = _build_prompt(memory_name, normalized_message, context_block=context_block, conversation_history=conversation_history)
        guild = getattr(channel, "guild", None)
        guild_id = getattr(guild, "id", None)

        # Check guild tools mode — if 'off', pass no tools (chat-only mode)
        if guild_id is not None:
            tools_mode = await asyncio.to_thread(get_guild_tools_mode, guild_id)
        else:
            tools_mode = 'on'

        effective_tools = ALL_TOOLS_DECLARATION if (tools_mode == 'on' and ALL_TOOLS_DECLARATION) else None
        if effective_tools:
            # Raw response path — enables function call detection
            response_text = None
            try:
                if use_reasoning:
                    if guild_id is not None:
                        with use_guild_gemini_api_key(guild_id):
                            response = await asyncio.to_thread(
                                gemini_client.generate_text_with_reasoning_raw,
                                prompt,
                                _compose_system_prompt(system_prompt),
                                model_name,
                                thinking_budget=thinking_budget,
                                tools=effective_tools,
                                image_urls=all_image_urls or None,
                            )
                        await asyncio.to_thread(record_guild_gemini_key_success, guild_id)
                    else:
                        response = await asyncio.to_thread(
                            gemini_client.generate_text_with_reasoning_raw,
                            prompt,
                            _compose_system_prompt(system_prompt),
                            model_name,
                            thinking_budget=thinking_budget,
                            tools=effective_tools,
                            image_urls=all_image_urls or None,
                        )
                else:
                    # Non-reasoning path: use generate_text with return_raw_response=True
                    if guild_id is not None:
                        with use_guild_gemini_api_key(guild_id):
                            response = await asyncio.to_thread(
                                gemini_client.generate_text,
                                prompt,
                                _compose_system_prompt(system_prompt),
                                model_name,
                                tools=effective_tools,
                                return_raw_response=True,
                                image_urls=all_image_urls or None,
                            )
                        await asyncio.to_thread(record_guild_gemini_key_success, guild_id)
                    else:
                        response = await asyncio.to_thread(
                            gemini_client.generate_text,
                            prompt,
                            _compose_system_prompt(system_prompt),
                            model_name,
                            tools=effective_tools,
                            return_raw_response=True,
                            image_urls=all_image_urls or None,
                        )
            except Exception as exc:
                if guild_id is not None:
                    await asyncio.to_thread(raise_for_guild_gemini_exception, guild_id, exc)
                raise

            # Check for function calls in response
            function_calls = gemini_client.parse_function_calls(response)
            if function_calls:
                logger.info("Function calls detected: %s", function_calls)
                tool_results = await handle_function_calls(response, channel)
                if tool_results:
                    # Build the explicit directive with examples — the AI must act, not narrate
                    mentioned_ids = []
                    for line in tool_results.split('\n'):
                        if '[message_id:' in line:
                            mid = line.split('[message_id:')[1].split(']')[0].strip()
                            if mid not in mentioned_ids:
                                mentioned_ids.append(mid)

                    ids_examples = ", ".join(f"`{mid}`" for mid in mentioned_ids) if mentioned_ids else "[message_id]"

                    # Extract card bodies from tool results for injection into follow-up prompt
                    card_bodies = []
                    in_card = False
                    current_card = []
                    for line in tool_results.split('\n'):
                        if '--- CARD' in line and 'BODY' in line:
                            in_card = True
                            current_card = [line]
                        elif in_card:
                            if line.strip() == '--- END CARD DATA ---':
                                card_bodies.append('\n'.join(current_card))
                                in_card = False
                                current_card = []
                            else:
                                current_card.append(line)
                    
                    card_injection = ""
                    if card_bodies:
                        card_injection = (
                            "\n\n" + "\n\n".join(card_bodies) + "\n\n"
                            "CARD CONTENT ABOVE — copy it into your edit_message call. "
                            "You MUST preserve every field from the card body above except the ones the user explicitly changed. "
                            "If you see HP or stat values in the card above, copy them exactly — do not recalculate or generate new values.\n\n"
                            "VERIFICATION STEP before you call edit_message:\n"
                            "  1. Confirm your embed_description contains EVERY field from the card body above\n"
                            "  2. Confirm the values you want to change are correct\n"
                            "  3. Confirm unchanged values are IDENTICAL to what is in the card body above\n\n"
                        )
                    
                    follow_up_prompt = (
                        f"{prompt}\n\n"
                        f"Tool results:\n{tool_results}\n\n"
                        "EXPLICIT INSTRUCTION: You have just read the content of message(s) with ID(s): "
                        f"{ids_examples}. These are Discord cards you need to update.{card_injection}"
                        "Action required: For EACH message that needs updating, you MUST call "
                        "the `edit_message` tool with the correct message_id — do NOT call "
                        "`get_message_content` again, you already have the content.\n\n"
                        "Correct sequence:\n"
                        "  1. Call `edit_message` for each message ID from the tool results above\n"
                        "  2. Stop calling tools once all edits are done\n"
                        "  3. Give a one-line confirmation\n\n"
                        "Do NOT: re-read content, ask questions, narrate character stats, "
                        "or send new messages. ONLY call `edit_message` then confirm.\n\n"
                        "Example of wrong behavior: \"Veton takes 80 damage! Here's the updated card...\"\n"
                        "Example of correct behavior: call `edit_message(message_id=150..., embed_title=..., embed_description=...)` then say \"Cards updated.\"\n\n"
                        "IMPORTANT — answering questions vs. new edit requests:\n"
                        "  - If the user's message asks a question (? or what/how/why/who/where/when/can/could), ANSWER DIRECTLY from the card content and conversation above. Do NOT call `edit_message` or any other tool. The card content you just read is sufficient to answer.\n"
                        "  - Only call `edit_message` if the user explicitly asks to update, change, add, or edit something in a card.\n"
                        "  - When answering a question, reference the card content directly — do not mention tool calls or internal IDs.\n"
                    )
                    async with channel.typing():
                        if guild_id is not None:
                            with use_guild_gemini_api_key(guild_id):
                                follow_up_response = await asyncio.to_thread(
                                    gemini_client.generate_text,
                                    follow_up_prompt,
                                    _compose_system_prompt(system_prompt),
                                    model_name,
                                    tools=_FOLLOWUP_TOOLS if _FOLLOWUP_TOOLS else None,
                                    return_raw_response=True,
                                )
                            await asyncio.to_thread(record_guild_gemini_key_success, guild_id)
                        else:
                            follow_up_response = await asyncio.to_thread(
                                gemini_client.generate_text,
                                follow_up_prompt,
                                _compose_system_prompt(system_prompt),
                                model_name,
                                tools=_FOLLOWUP_TOOLS if _FOLLOWUP_TOOLS else None,
                                return_raw_response=True,
                            )
                        # Parse and handle any follow-up function calls (e.g. edit_message after reading)
                        extra_calls = gemini_client.parse_function_calls(follow_up_response)
                        if extra_calls:
                            logger.info("Follow-up function calls: %s", extra_calls)
                            # Block get_context — it's the wrong tool for this context and indicates the AI
                            # is hallucinating context instead of using the card content from the tool results above
                            edit_calls = [c for c in extra_calls if c["name"] == "edit_message"]
                            context_calls = [c for c in extra_calls if c["name"] == "get_context"]
                            if context_calls:
                                logger.warning(
                                    "Follow-up AI tried to call get_context (message_id=%s) instead of edit_message. "
                                    "Tool results already contain the card content — get_context is wrong tool here. "
                                    "Ignoring get_context calls, processing edit_message only.",
                                    context_calls[0]["args"].get("thread_id"),
                                )
                            if edit_calls:
                                extra_results = await handle_function_calls_from_dicts(edit_calls, channel)
                            else:
                                extra_results = ""
                            if extra_results:
                                follow_up_prompt2 = (
                                    f"Previous tool results:\n{extra_results}\n\n"
                                    "FINAL INSTRUCTION: All edits should now be complete. "
                                    "If any `edit_message` calls were made above, confirm what was changed "
                                    "with a single short reply (e.g. 'Updated 2 cards.'). "
                                    "Do NOT narrate, describe stats, or generate new content."
                                )
                                async with channel.typing():
                                    if guild_id is not None:
                                        with use_guild_gemini_api_key(guild_id):
                                            response_text = await asyncio.to_thread(
                                                gemini_client.generate_text,
                                                follow_up_prompt2,
                                                _compose_system_prompt(system_prompt),
                                                model_name,
                                            )
                                        await asyncio.to_thread(record_guild_gemini_key_success, guild_id)
                                    else:
                                        response_text = await asyncio.to_thread(
                                            gemini_client.generate_text,
                                            follow_up_prompt2,
                                            _compose_system_prompt(system_prompt),
                                            model_name,
                                        )
                            else:
                                response_text = (follow_up_response.text or "").strip() if hasattr(follow_up_response, "text") else str(follow_up_response)
                        else:
                            response_text = (follow_up_response.text or "").strip() if hasattr(follow_up_response, "text") else str(follow_up_response)
                else:
                    response_text = (response.text or "").strip() if hasattr(response, "text") else str(response)
            else:
                response_text = (response.text or "").strip() if hasattr(response, "text") else str(response)
        else:
            # No tools — plain text generation
            response_text = None
            try:
                if guild_id is not None:
                    with use_guild_gemini_api_key(guild_id):
                        response_text = await asyncio.to_thread(
                            gemini_client.generate_text,
                            prompt,
                            _compose_system_prompt(system_prompt),
                            model_name,
                            image_urls=all_image_urls or None,
                        )
                    await asyncio.to_thread(record_guild_gemini_key_success, guild_id)
                else:
                    response_text = await asyncio.to_thread(
                        gemini_client.generate_text,
                        prompt,
                        _compose_system_prompt(system_prompt),
                        model_name,
                        image_urls=all_image_urls or None,
                    )
            except Exception as exc:
                if guild_id is not None:
                    await asyncio.to_thread(raise_for_guild_gemini_exception, guild_id, exc)
                raise

        if not response_text:
            return "No valid response received from Gemini."

        logger.info("Gemini responded in memory '%s': %s", assigned_memory, response_text[:100])
        if send_message:
            await send_response_in_chunks(channel, response_text)
        return response_text

    except Exception as exc:
        logger.error("Error during the Gemini interaction: %s", exc)
        if isinstance(exc, ValueError):
            return str(exc)
        return f"Error during the Gemini interaction: {exc}"
