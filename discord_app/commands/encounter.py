from __future__ import annotations

import asyncio

import discord
from discord import app_commands

from discord_app.helper_functions import get_interaction_category
from discord_app.player_workspace.prompting import build_encounter_workspace_system_prompt
from discord_app.workspace_threads import (
    discover_workspace_card_messages,
    parse_card_update_response,
    parse_workspace_thread,
    sync_workspace_cards,
)


def _card_body_from_message(message: discord.Message) -> str:
    return message.embeds[0].description if message.embeds else (message.content or "")


def _build_encounter_add_prompt(
    *,
    encounter_name: str,
    source_name: str,
    source_kind: str,
    count: int,
    role: str,
    note: str | None,
    encounter_cards: dict[str, str],
    source_cards: dict[str, str],
) -> str:
    encounter_block = "\n\n".join(
        f"### CURRENT CARD: {title}\n{body.strip() or 'Needs review.'}"
        for title, body in encounter_cards.items()
    )
    source_block = "\n\n".join(
        f"### SOURCE CARD: {title}\n{body.strip() or 'Needs review.'}"
        for title, body in source_cards.items()
    )
    optional_note = f"\nEncounter note from DM:\n{note.strip()}\n" if (note or "").strip() else ""
    return (
        f"You are updating the encounter workspace for {encounter_name}.\n\n"
        "The DM is adding a reusable source thread into this encounter as a local encounter snapshot.\n"
        "Update the encounter cards using the source material below.\n\n"
        "Rules:\n"
        "- This is a snapshot copy for the encounter, not a live sync.\n"
        "- Always update Enemy Roster.\n"
        "- Always update Balance & Threat.\n"
        "- Update Summary Card only if the encounter identity or quick summary changes materially.\n"
        "- Update Phases, Scripts & Triggers only if the role or note implies scripting relevance.\n"
        "- Keep the cards DM-usable and compact.\n"
        "- If source information is incomplete, preserve Needs review. where necessary.\n"
        "- Do not rewrite unaffected cards.\n"
        "- Return only updated card bodies using exactly this format:\n"
        "### CARD: Card Title\n"
        "Full card body\n\n"
        f"Source being added:\n- Name: {source_name}\n- Kind: {source_kind}\n- Count: {count}\n- Role: {role}\n"
        f"{optional_note}\n"
        f"Current encounter cards:\n{encounter_block}\n\n"
        f"Source cards:\n{source_block}\n"
    )


async def _source_thread_autocomplete(interaction: discord.Interaction, current: str):
    category = get_interaction_category(interaction)
    if category is None:
        return []

    choices: list[app_commands.Choice[str]] = []
    seen: set[int] = set()
    for channel_name in ("monsters", "npcs"):
        source_channel = discord.utils.get(category.text_channels, name=channel_name)
        if source_channel is None:
            continue

        threads = list(source_channel.threads)
        async for archived in source_channel.archived_threads(limit=100):
            threads.append(archived)

        for thread in threads:
            if thread.id in seen:
                continue
            seen.add(thread.id)
            if current.lower() not in thread.name.lower():
                continue
            label = f"{channel_name[:-1].title()}: {thread.name}"
            choices.append(app_commands.Choice(name=label[:100], value=str(thread.id)))
            if len(choices) >= 25:
                return choices

    return choices[:25]


def register(encounter_group, h) -> None:
    @encounter_group.command(name="add", description="Add a monster or NPC source thread into the current encounter.")
    @app_commands.describe(
        source_thread="Monster or NPC workspace thread to snapshot into this encounter.",
        count="How many of this source to add to the encounter.",
        role="Encounter role for this source, like boss, elite, support, or minion.",
        note="Optional encounter-specific note, such as phase relevance or local tweaks.",
    )
    async def encounter_add(
        interaction: discord.Interaction,
        source_thread: str,
        count: app_commands.Range[int, 1, 99] = 1,
        role: str = "support",
        note: str | None = None,
    ):
        await h.send_command_ack(interaction, "Adding source to encounter... this should just take a moment.")

        encounter_thread = interaction.channel
        if not isinstance(encounter_thread, discord.Thread):
            raise ValueError("Run `/encounter add` inside the encounter thread you want to update.")

        encounter_kind, encounter_name = parse_workspace_thread(encounter_thread.name)
        if encounter_kind != "encounter" or not encounter_name:
            raise ValueError("Run `/encounter add` inside an Encounter workspace thread.")

        try:
            source = interaction.guild.get_channel(int(source_thread)) or await interaction.guild.fetch_channel(int(source_thread))
        except (ValueError, discord.HTTPException):
            raise ValueError("Source thread not found.")

        if not isinstance(source, discord.Thread):
            raise ValueError("The selected source must be a monster or NPC workspace thread.")

        source_kind, source_name = parse_workspace_thread(source.name)
        if source_kind not in {"monster", "npc"} or not source_name:
            raise ValueError("The selected source must be a monster or NPC workspace thread.")

        encounter_messages = await discover_workspace_card_messages(encounter_thread)
        if not encounter_messages:
            raise ValueError("Could not locate the encounter cards in this thread.")

        source_messages = await discover_workspace_card_messages(source)
        if not source_messages:
            raise ValueError("Could not locate card messages in the selected source thread.")

        encounter_cards = {title: _card_body_from_message(message) for title, message in encounter_messages.items()}
        source_cards = {title: _card_body_from_message(message) for title, message in source_messages.items()}

        prompt = _build_encounter_add_prompt(
            encounter_name=encounter_name,
            source_name=source_name,
            source_kind=source_kind,
            count=count,
            role=(role or "support").strip(),
            note=note,
            encounter_cards=encounter_cards,
            source_cards=source_cards,
        )
        system_prompt = build_encounter_workspace_system_prompt(encounter_name)
        raw = await asyncio.to_thread(h.gemini_client.generate_text, prompt, system_prompt)
        updates = parse_card_update_response(raw)
        if not updates:
            raise ValueError("AIDM could not generate updated encounter cards from that source. Try again with a clearer note.")

        merged_cards = dict(encounter_cards)
        merged_cards.update(updates)
        await sync_workspace_cards(encounter_thread, merged_cards)

        updated_titles = ", ".join(updates.keys())
        await h.send_interaction_message(
            interaction,
            f"Added **{source_name}** ×{count} to {encounter_thread.mention}. Updated: {updated_titles}.",
            ephemeral=True,
        )

    @encounter_add.autocomplete("source_thread")
    async def encounter_add_source_autocomplete(interaction: discord.Interaction, current: str):
        return await _source_thread_autocomplete(interaction, current)
