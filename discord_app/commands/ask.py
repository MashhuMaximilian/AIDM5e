from __future__ import annotations

from discord import app_commands


def register(ask_group, h) -> None:
    @ask_group.command(name="campaign", description="Campaign info lookup. Defaults to #telldm if no target is set.")
    @app_commands.describe(
        query="What you want to know.",
        channel="Optional target channel. Defaults to #telldm in this category.",
        thread="Optional target thread. Overrides the channel target when set.",
        use_context="Whether to include campaign context from #context."
    )
    @app_commands.choices(
        query_type=[
            app_commands.Choice(name="Check Status", value="checkstatus"),
            app_commands.Choice(name="Homebrew", value="homebrew"),
            app_commands.Choice(name="NPC", value="npc"),
            app_commands.Choice(name="Inventory", value="inventory"),
            app_commands.Choice(name="Roll Check", value="rollcheck")
        ],
        use_context=h.USE_CONTEXT_CHOICES,
    )
    async def tellme(
        interaction,
        query_type: app_commands.Choice[str],
        query: str,
        channel: str = None,
        thread: str = None,
        use_context: app_commands.Choice[str] | None = None,
    ):
        await h.process_query_command(
            interaction,
            query_type,
            query,
            backup_channel_name="telldm",
            channel=channel,
            thread=thread,
            use_context=use_context.value if use_context else None,
            default_context_when_auto=True,
        )

    @tellme.autocomplete('channel')
    async def tellme_channel_autocomplete(interaction, current: str):
        choices = await h.channel_autocomplete(interaction, current)
        return choices[:25]

    @tellme.autocomplete('thread')
    async def tellme_thread_autocomplete(interaction, current: str):
        return await h.thread_autocomplete(interaction, current)

    @ask_group.command(name="dm", description="Rules and lore lookup. Defaults to #telldm if no target is set.")
    @app_commands.describe(
        query="Your rules, lore, or adjudication question.",
        channel="Optional target channel. Defaults to #telldm in this category.",
        thread="Optional target thread. Overrides the channel target when set.",
        use_context="Whether to include campaign context from #context."
    )
    @app_commands.choices(
        query_type=[
            app_commands.Choice(name="Spell", value="spell"),
            app_commands.Choice(name="Game Mechanics", value="game_mechanics"),
            app_commands.Choice(name="Monsters & Creatures", value="monsters_creatures"),
            app_commands.Choice(name="World Lore & History", value="world_lore_history"),
            app_commands.Choice(name="Item", value="item"),
            app_commands.Choice(name="Conditions & Effects", value="conditions_effects"),
            app_commands.Choice(name="Rules Clarifications", value="rules_clarifications"),
            app_commands.Choice(name="Race or Class", value="race_class")
        ],
        use_context=h.USE_CONTEXT_CHOICES,
    )
    async def askdm(
        interaction,
        query_type: app_commands.Choice[str],
        query: str,
        channel: str = None,
        thread: str = None,
        use_context: app_commands.Choice[str] | None = None,
    ):
        await h.process_query_command(
            interaction,
            query_type,
            query,
            backup_channel_name="telldm",
            channel=channel,
            thread=thread,
            use_context=use_context.value if use_context else None,
            default_context_when_auto=False,
        )

    @askdm.autocomplete('channel')
    async def askdm_channel_autocomplete(interaction, current: str):
        choices = await h.channel_autocomplete(interaction, current)
        return choices[:25]

    @askdm.autocomplete('thread')
    async def askdm_thread_autocomplete(interaction, current: str):
        return await h.thread_autocomplete(interaction, current)
