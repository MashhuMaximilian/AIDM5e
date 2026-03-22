from __future__ import annotations

import asyncio
from pathlib import Path

import discord
from discord import app_commands


def register(create_group, h) -> None:
    @create_group.command(name="player", description="Create or refresh a player character workspace.")
    @app_commands.describe(
        mode="Create from idea or import from source material.",
        character_name="Character name. Used for the thread name and card labels.",
        player_name="Optional player name to include in the draft.",
        note="Concept notes or extra instructions for the draft.",
        attachment="Optional character sheet, notes, or source file.",
        start="Message ID to start from when importing from a conversation.",
        end="Message ID to end at when importing from a conversation.",
        message_ids="Comma-separated message IDs to import.",
        last_n="Import the last n messages from the selected source.",
        channel="Optional source channel for message-based import.",
        thread="Optional source thread for message-based import.",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Start from Idea", value="idea"),
            app_commands.Choice(name="Import Sheet / Notes", value="import"),
        ]
    )
    async def create_player(
        interaction: discord.Interaction,
        mode: app_commands.Choice[str],
        character_name: str | None = None,
        player_name: str | None = None,
        note: str | None = None,
        attachment: discord.Attachment | None = None,
        start: str | None = None,
        end: str | None = None,
        message_ids: str | None = None,
        last_n: int | None = None,
        channel: str | None = None,
        thread: str | None = None,
    ):
        await h.send_command_ack(interaction, "Creating player workspace... this might take a couple minutes. Trust the process.")

        category = h.get_interaction_category(interaction)
        if category is None:
            raise ValueError("Run `/create player` inside a campaign category.")

        source_text, file_paths, source_label, temp_paths = await h.collect_player_source_material(
            interaction,
            note=note,
            attachment=attachment,
            start=start,
            end=end,
            message_ids=message_ids,
            last_n=last_n,
            channel=channel,
            thread=thread,
            resolve_source_target=h._resolve_context_source_target,
            build_context_material_from_messages=h._build_context_material_from_messages,
            describe_context_source=h._describe_context_source,
        )

        if mode.value == "import" and not any([attachment, source_text, note]):
            raise ValueError("Import mode needs an attachment, note, or selected messages to read from.")

        display_name = (character_name or "New Character").strip()
        thread_name = f"Character - {display_name}"
        sheets_channel = await h.ensure_character_sheets_channel(interaction, category)
        player_thread, created_thread = await h.find_or_create_player_thread(sheets_channel, thread_name)

        context = await asyncio.to_thread(
            h.get_or_create_campaign_context,
            interaction.guild.id,
            interaction.guild.name,
            category.id,
            category.name,
            h.DM_ROLE_NAME,
        )
        memory_name = f"player-{h.slugify_player_key(display_name)}"
        memory_id = await asyncio.to_thread(h.ensure_memory, context.campaign_id, memory_name)
        await asyncio.to_thread(h.ensure_thread_for_channel, sheets_channel.id, player_thread.id, player_thread.name, True)
        await asyncio.to_thread(h.assign_memory_to_thread, player_thread.id, memory_id)
        await asyncio.to_thread(h.set_thread_always_on, player_thread.id, True)

        try:
            request = h.PlayerWorkspaceRequest(
                mode=mode.value,
                character_name=character_name,
                player_name=player_name,
                source=h.SourceBundle(
                    note=note,
                    source_text=source_text,
                    file_paths=file_paths,
                    source_label=source_label,
                ),
                thread_name=thread_name,
            )
            bundle = await h.build_player_workspace(request, gemini=h.gemini_client)

            if created_thread:
                await player_thread.send(bundle.cards.welcome_text)
                if attachment is not None:
                    await player_thread.send(
                        f"Imported source file from `/create player`: `{attachment.filename}`",
                        file=await attachment.to_file(),
                    )

            await h.sync_workspace_slots(player_thread, bundle)
        finally:
            for temp_path in temp_paths:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    h.logger.warning("Failed to clean up temporary player import file %s", temp_path)

        action_label = "created" if created_thread else "updated"
        await h.send_interaction_message(
            interaction,
            f"Player workspace {action_label} in {player_thread.mention}.",
            ephemeral=True,
        )

    @create_player.autocomplete("channel")
    async def create_player_channel_autocomplete(interaction, current: str):
        return await h.channel_autocomplete(interaction, current)

    @create_player.autocomplete("thread")
    async def create_player_thread_autocomplete(interaction, current: str):
        return await h.thread_autocomplete(interaction, current)

    @create_group.command(name="npc", description="Create or refresh an NPC workspace.")
    @app_commands.describe(
        npc_name="NPC name. Used for the thread and card labels.",
        note="Optional notes or concept details for the NPC.",
    )
    async def create_npc(
        interaction: discord.Interaction,
        npc_name: str,
        note: str | None = None,
    ):
        await h.send_command_ack(interaction, "Creating NPC workspace... this should just take a moment.")

        display_name = (npc_name or "New NPC").strip()
        _, npc_thread, created_thread = await h._ensure_workspace_thread(
            interaction,
            display_name=display_name,
            thread_prefix="NPC",
            memory_prefix="npc",
            target_channel_name="npcs",
        )

        definition = h.WorkspaceDefinition(
            kind="npc",
            entity_name=display_name,
            user_note=(note or "").strip(),
            card_inventory_text=h._default_npc_card_inventory_text(),
            cascade_rules_text=h._default_npc_cascade_rules_text(),
            card_titles=list(h.NPC_DEFAULT_CARD_TITLES),
        )
        cards = h.build_npc_blank_cards(display_name)

        if created_thread:
            await npc_thread.send(h.build_workspace_welcome_text(definition))

        await h.sync_workspace_cards(npc_thread, cards)

        action_label = "created" if created_thread else "updated"
        await h.send_interaction_message(
            interaction,
            f"NPC workspace {action_label} in {npc_thread.mention}.",
            ephemeral=True,
        )

    @create_group.command(name="other", description="Create or refresh a custom workspace.")
    @app_commands.describe(
        entity_name="Entity name. Used for the thread and card labels.",
        note="What this workspace is for. Used to design the card inventory.",
    )
    async def create_other(
        interaction: discord.Interaction,
        entity_name: str,
        note: str | None = None,
    ):
        await h.send_command_ack(interaction, "Designing custom workspace... this might take a minute.")

        display_name = (entity_name or "New Entity").strip()
        if not (note or "").strip():
            raise ValueError("`/create other` needs a note describing what this workspace is for.")

        _, other_thread, created_thread = await h._ensure_workspace_thread(
            interaction,
            display_name=display_name,
            thread_prefix="Other",
            memory_prefix="other",
            target_channel_name="worldbuilding",
            reuse_channel_memory=True,
        )

        prepass_prompt = h.build_other_prepass_prompt(note)
        prepass_output = await asyncio.to_thread(h.gemini_client.generate_text, prepass_prompt)
        card_titles, card_inventory_text, cascade_rules_text = h.parse_other_prepass_output(prepass_output)

        definition = h.WorkspaceDefinition(
            kind="other",
            entity_name=display_name,
            user_note=(note or "").strip(),
            card_inventory_text=card_inventory_text,
            cascade_rules_text=cascade_rules_text,
            card_titles=card_titles,
        )
        cards = h.build_other_blank_cards(display_name, card_titles)

        if created_thread:
            await other_thread.send(h.build_workspace_welcome_text(definition))

        await h.sync_workspace_cards(other_thread, cards)

        action_label = "created" if created_thread else "updated"
        await h.send_interaction_message(
            interaction,
            f"Custom workspace {action_label} in {other_thread.mention}.",
            ephemeral=True,
        )
