# assistant_interactions.py

import asyncio
import logging

from config import AIDM_PROMPT_PATH, client
from db_repository import append_memory_message, fetch_memory_messages, get_memory_name
from gemini_client import gemini_client
from shared_functions import send_response_in_chunks


logger = logging.getLogger(__name__)


try:
    SYSTEM_PROMPT = AIDM_PROMPT_PATH.read_text(encoding="utf-8").strip()
except FileNotFoundError:
    SYSTEM_PROMPT = "You are AIDM, an AI Dungeon Master for D&D 5e."


def _normalize_user_message(user_message) -> str:
    if isinstance(user_message, str):
        return user_message

    if isinstance(user_message, list):
        parts = []
        for item in user_message:
            if not isinstance(item, dict):
                parts.append(str(item))
                continue
            item_type = item.get("type")
            if item_type == "text":
                parts.append(item.get("text", ""))
            elif item_type == "image_url":
                image_url = item.get("image_url", {}).get("url")
                if image_url:
                    parts.append(f"[User attached image: {image_url}]")
        return "\n".join(part for part in parts if part)

    return str(user_message)


def _build_prompt(memory_name: str | None, history: list[dict], user_message: str) -> str:
    history_lines = []
    for entry in history:
        role = entry["role"].upper()
        speaker = entry.get("source_display_name")
        if speaker and entry["role"] == "user":
            history_lines.append(f"{role} ({speaker}): {entry['content']}")
        else:
            history_lines.append(f"{role}: {entry['content']}")

    history_block = "\n".join(history_lines) if history_lines else "No prior memory."
    memory_label = memory_name or "unassigned"
    return (
        f"Current memory bucket: {memory_label}\n\n"
        f"Prior conversation memory:\n{history_block}\n\n"
        f"Current user request:\n{user_message}"
    )


async def get_assistant_response(
    user_message,
    channel_id,
    category_id=None,
    thread_id=None,
    assigned_memory=None,
    send_message=False,
    model_name=None,
):
    try:
        channel = client.get_channel(channel_id)
        if channel is None:
            error_message = f"Error: Channel with ID {channel_id} not found."
            logger.error(error_message)
            return error_message

        if not assigned_memory:
            error_message = "Assigned memory ID is invalid or empty."
            logger.error(error_message)
            return error_message

        normalized_message = _normalize_user_message(user_message)
        history = await asyncio.to_thread(fetch_memory_messages, assigned_memory, 40)
        memory_name = await asyncio.to_thread(get_memory_name, assigned_memory)
        prompt = _build_prompt(memory_name, history, normalized_message)

        async with channel.typing():
            response_text = await asyncio.to_thread(
                gemini_client.generate_text,
                prompt,
                SYSTEM_PROMPT,
                model_name,
            )

        if not response_text:
            return "No valid response received from Gemini."

        await asyncio.to_thread(
            append_memory_message,
            assigned_memory,
            "user",
            normalized_message,
            channel_id,
            thread_id,
            None,
            None,
        )
        await asyncio.to_thread(
            append_memory_message,
            assigned_memory,
            "assistant",
            response_text,
            channel_id,
            thread_id,
            None,
            None,
        )

        logger.info("Gemini responded in memory '%s': %s", assigned_memory, response_text[:100])
        if send_message:
            await send_response_in_chunks(channel, response_text)
        return response_text

    except Exception as exc:
        logger.error("Error during the Gemini interaction: %s", exc)
        return f"Error during the Gemini interaction: {exc}"
