from __future__ import annotations

from types import SimpleNamespace

import discord
from discord import app_commands
from psycopg import errors as pg_errors


def build_helpers(module_globals: dict, get_assistant_response):
    data = {key: value for key, value in module_globals.items() if not key.startswith("__")}
    data["get_assistant_response"] = get_assistant_response
    return SimpleNamespace(**data)


def register_tree_error_handler(tree, h) -> None:
    @tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        original = error.original if isinstance(error, app_commands.CommandInvokeError) else error
        h.logger.exception("Application command error: %s", original)

        if isinstance(original, pg_errors.UniqueViolation):
            message = (
                "Cannot complete that command because an item with the same unique value already exists "
                "in this campaign. If you were creating a channel or thread, choose a different name "
                "or reuse the existing one."
            )
        elif isinstance(original, ValueError):
            message = str(original)
        elif isinstance(original, discord.Forbidden):
            message = "I do not have permission to complete that command in Discord."
        else:
            command_name = interaction.command.qualified_name if interaction.command else "that command"
            message = f"Could not complete `{command_name}` because of an internal error. Please try again now or later."

        try:
            await h.send_interaction_message(interaction, message, ephemeral=True)
        except Exception:
            h.logger.exception("Failed to send app command error message.")
