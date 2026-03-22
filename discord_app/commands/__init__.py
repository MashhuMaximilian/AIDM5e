from __future__ import annotations

from discord import app_commands

from . import ask, channel, context, create, generate, memory, settings, standalone
from ._base import build_helpers, register_tree_error_handler


def setup_commands(tree, get_assistant_response, module_globals: dict) -> None:
    h = build_helpers(module_globals, get_assistant_response)

    ask_group = app_commands.Group(name="ask", description="Rules and lore commands.")
    channel_group = app_commands.Group(name="channel", description="Channel and thread commands.")
    memory_group = app_commands.Group(name="memory", description="Memory management commands.")
    context_group = app_commands.Group(name="context", description="Context helpers for summaries and transcripts.")
    settings_group = app_commands.Group(name="settings", description="Campaign settings commands.")
    generate_group = app_commands.Group(name="generate", description="Image and media generation commands.")
    create_group = app_commands.Group(name="create", description="Character creation workflows.")

    standalone.register(tree, h)
    create.register(create_group, h)
    ask.register(ask_group, h)
    channel.register(channel_group, h)
    memory.register(memory_group, h)
    settings.register(settings_group, h)
    context.register(context_group, h)
    generate.register(generate_group, h)

    register_tree_error_handler(tree, h)

    tree.add_command(ask_group)
    tree.add_command(channel_group)
    tree.add_command(context_group)
    tree.add_command(create_group)
    tree.add_command(memory_group)
    tree.add_command(settings_group)
    tree.add_command(generate_group)
