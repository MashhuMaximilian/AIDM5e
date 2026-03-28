# assistant_interactions.py

import asyncio
import logging

from ai_services.guild_api_keys import (
    raise_for_guild_gemini_exception,
    record_guild_gemini_key_success,
    use_guild_gemini_api_key,
)
from config import AIDM_PROMPT_PATH, client
from data_store.db_repository import get_memory_name
from discord_app.shared_functions import send_response_in_chunks
from .gemini_client import gemini_client


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


def _build_prompt(memory_name: str | None, user_message: str, context_block: str | None = None) -> str:
    memory_label = memory_name or "unassigned"
    prompt = (
        f"Current memory bucket: {memory_label}\n\n"
        "Persistent chat transcript history is disabled for this bot. "
        "Use the assigned memory bucket and the current request only.\n\n"
        f"Current user request:\n{user_message}"
    )
    if context_block:
        prompt = (
            f"Campaign reference context:\n{context_block}\n\n"
            "Use campaign reference context only when it is relevant to the current request. "
            "If the memory/current request and the campaign context conflict, say so clearly instead of silently merging them.\n\n"
            + prompt
        )
    return prompt


def _compose_system_prompt(system_prompt: str | None = None) -> str:
    if not system_prompt:
        return SYSTEM_PROMPT
    return f"{SYSTEM_PROMPT}\n\n{system_prompt.strip()}".strip()


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

        normalized_message = _normalize_user_message(user_message)
        memory_name = await asyncio.to_thread(get_memory_name, assigned_memory)
        prompt = _build_prompt(memory_name, normalized_message, context_block=context_block)
        guild = getattr(channel, "guild", None)
        guild_id = getattr(guild, "id", None)

        async with channel.typing():
            try:
                if guild_id is not None:
                    with use_guild_gemini_api_key(guild_id):
                        response_text = await asyncio.to_thread(
                            gemini_client.generate_text,
                            prompt,
                            _compose_system_prompt(system_prompt),
                            model_name,
                        )
                    await asyncio.to_thread(record_guild_gemini_key_success, guild_id)
                else:
                    response_text = await asyncio.to_thread(
                        gemini_client.generate_text,
                        prompt,
                        _compose_system_prompt(system_prompt),
                        model_name,
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
