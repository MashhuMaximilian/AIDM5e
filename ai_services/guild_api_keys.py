from __future__ import annotations

from contextlib import contextmanager

from ai_services.gemini_client import is_gemini_auth_error, use_gemini_api_key
from data_store.db_repository import (
    get_guild_api_key,
    mark_guild_api_key_invalid,
    mark_guild_api_key_valid,
)


GEMINI_PROVIDER = "gemini"


def build_missing_guild_api_key_message() -> str:
    return (
        "This server does not have a Gemini API key configured yet. "
        "A server owner or admin can add one with `/settings global set-api-key`."
    )


def build_invalid_guild_api_key_message() -> str:
    return (
        "The configured Gemini API key for this server looks invalid. "
        "A server owner or admin should update it with `/settings global rotate-api-key` "
        "or `/settings global set-api-key`."
    )


def get_required_guild_gemini_api_key(discord_guild_id: int) -> str:
    api_key = get_guild_api_key(discord_guild_id, provider=GEMINI_PROVIDER)
    if not api_key:
        raise ValueError(build_missing_guild_api_key_message())
    return api_key


@contextmanager
def use_guild_gemini_api_key(discord_guild_id: int):
    api_key = get_required_guild_gemini_api_key(discord_guild_id)
    with use_gemini_api_key(api_key):
        yield api_key


def record_guild_gemini_key_success(discord_guild_id: int) -> None:
    mark_guild_api_key_valid(discord_guild_id, provider=GEMINI_PROVIDER)


def mark_guild_gemini_key_auth_failure(discord_guild_id: int, exc: Exception) -> bool:
    if not is_gemini_auth_error(exc):
        return False
    message = str(exc).strip() or "Gemini rejected the configured API key."
    mark_guild_api_key_invalid(discord_guild_id, provider=GEMINI_PROVIDER, error_message=message[:500])
    return True


def raise_for_guild_gemini_exception(discord_guild_id: int, exc: Exception) -> None:
    if mark_guild_gemini_key_auth_failure(discord_guild_id, exc):
        raise ValueError(build_invalid_guild_api_key_message()) from exc
    raise exc
