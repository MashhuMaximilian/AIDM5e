# assistant_interactions.py

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable

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


def _build_prompt(memory_name: str | None, user_message: str) -> str:
    memory_label = memory_name or "unassigned"
    return (
        f"Current memory bucket: {memory_label}\n\n"
        "Persistent chat transcript history is disabled for this bot. "
        "Use the assigned memory bucket and the current request only.\n\n"
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
        memory_name = await asyncio.to_thread(get_memory_name, assigned_memory)
        prompt = _build_prompt(memory_name, normalized_message)

        async with channel.typing():
            response_text = await asyncio.to_thread(
                gemini_client.generate_text,
                prompt,
                SYSTEM_PROMPT,
                model_name,
            )

        if not response_text:
            return "No valid response received from Gemini."

        logger.info("Gemini responded in memory '%s': %s", assigned_memory, response_text[:100])
        if send_message:
            await send_response_in_chunks(channel, response_text)
        return response_text

    except Exception as exc:
        logger.error("Error during the Gemini interaction: %s", exc)
        return f"Error during the Gemini interaction: {exc}"


async def stream_assistant_response(
    user_message,
    channel_id,
    category_id=None,
    thread_id=None,
    assigned_memory=None,
    model_name=None,
    on_update: Callable[[str], Awaitable[None]] | None = None,
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
        memory_name = await asyncio.to_thread(get_memory_name, assigned_memory)
        prompt = _build_prompt(memory_name, normalized_message)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, str | Exception | None]] = asyncio.Queue()

        def worker() -> None:
            try:
                for chunk in gemini_client.generate_text_stream(
                    prompt,
                    SYSTEM_PROMPT,
                    model_name,
                ):
                    if not chunk:
                        continue
                    loop.call_soon_threadsafe(queue.put_nowait, ("chunk", chunk))
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))

        response_parts: list[str] = []
        worker_thread = threading.Thread(target=worker, daemon=True)

        async with channel.typing():
            worker_thread.start()
            while True:
                kind, payload = await queue.get()
                if kind == "chunk":
                    chunk = str(payload or "")
                    response_parts.append(chunk)
                    if on_update:
                        await on_update("".join(response_parts))
                    continue
                if kind == "error":
                    raise payload if isinstance(payload, Exception) else RuntimeError(str(payload))
                break

        worker_thread.join(timeout=0.1)
        response_text = "".join(response_parts).strip()
        if not response_text:
            return "No valid response received from Gemini."

        logger.info("Gemini streamed response in memory '%s': %s", assigned_memory, response_text[:100])
        return response_text

    except Exception as exc:
        logger.error("Error during the streamed Gemini interaction: %s", exc)
        return f"Error during the Gemini interaction: {exc}"
