# bot_commands.py

import asyncio
import io
import logging
from pathlib import Path

import discord
from discord import app_commands
from psycopg import errors as pg_errors

from ai_services.gemini_client import gemini_client
from ai_services.scene_pipeline import scene_pipeline
from ai_services.context_compiler import (
    ContextAsset,
    build_context_entry_messages,
    compile_context_packet_from_category,
)
from content_retrieval import extract_attachment_text, format_message_text, select_messages
from config import DM_ROLE_NAME
from data_store.db_repository import (
    assign_memory_to_channel,
    assign_memory_to_thread,
    build_thread_data_snapshot,
    ensure_channel_for_category,
    ensure_memory,
    ensure_thread_for_channel,
    fetch_memory_details,
    get_campaign_image_settings,
    get_or_create_campaign_context,
    set_thread_always_on,
    update_campaign_image_settings,
)
from data_store.memory_management import *
from prompts.summary_prompts import build_feedback_prompt
from discord_app.player_workspace import (
    PlayerWorkspaceRequest,
    SourceBundle,
    build_player_workspace,
    collect_player_source_material,
    ensure_character_sheets_channel,
    find_or_create_player_thread,
    sync_workspace_slots,
    slugify_player_key,
)
from discord_app.player_workspace.prompting import (
    build_npc_workspace_system_prompt,
    build_other_prepass_prompt,
    build_other_workspace_system_prompt,
    build_player_workspace_system_prompt,
)
from discord_app.workspace_threads import (
    NPC_DEFAULT_CARD_TITLES,
    WorkspaceDefinition,
    build_npc_blank_cards,
    build_other_blank_cards,
    build_workspace_welcome_text,
    parse_other_prepass_output,
    sync_workspace_cards,
)

from .helper_functions import *
from .shared_functions import *
from .shared_functions import apply_always_on, send_response_in_chunks
from .commands import setup_commands as register_command_modules

    # Set up logging (you can configure this as needed)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


HELP_TOPICS = (
    ("overview", "Overview"),
    ("invite", "Invite"),
    ("context", "Context"),
    ("settings", "Settings"),
    ("ask", "Ask"),
    ("channel", "Channel"),
    ("memory", "Memory"),
    ("reference", "Reference"),
    ("feedback", "Feedback"),
)

CONTEXT_SCOPE_CHOICES = [
    app_commands.Choice(name="Public Evergreen", value="public"),
    app_commands.Choice(name="Session Only", value="session"),
    app_commands.Choice(name="DM Private", value="dm"),
]

CONTEXT_WRITE_ACTION_CHOICES = [
    app_commands.Choice(name="Replace", value="replace"),
    app_commands.Choice(name="Append", value="append"),
]

IMAGE_MODE_CHOICES = [
    app_commands.Choice(name="Off", value="off"),
    app_commands.Choice(name="Auto", value="auto"),
]

IMAGE_QUALITY_CHOICES = [
    app_commands.Choice(name="Auto", value="auto"),
    app_commands.Choice(name="Fast", value="fast"),
    app_commands.Choice(name="HQ", value="hq"),
]

IMAGE_SOURCE_MODE_CHOICES = [
    app_commands.Choice(name="Latest Summary", value="latest_summary"),
    app_commands.Choice(name="Message IDs", value="message_ids"),
    app_commands.Choice(name="Last N Messages", value="last_n"),
    app_commands.Choice(name="Custom Prompt", value="custom_prompt"),
]

IMAGE_ASPECT_RATIO_CHOICES = [
    app_commands.Choice(name="Auto", value="auto"),
    app_commands.Choice(name="1:1", value="1:1"),
    app_commands.Choice(name="3:4", value="3:4"),
    app_commands.Choice(name="4:3", value="4:3"),
    app_commands.Choice(name="9:16", value="9:16"),
    app_commands.Choice(name="16:9", value="16:9"),
]

USE_CONTEXT_CHOICES = [
    app_commands.Choice(name="Auto", value="auto"),
    app_commands.Choice(name="On", value="on"),
    app_commands.Choice(name="Off", value="off"),
]

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _get_category_channel_mention(category: discord.CategoryChannel, channel_name: str, fallback_prefix: str = "#") -> str:
    channel = discord.utils.get(category.channels, name=channel_name)
    return channel.mention if channel else f"{fallback_prefix}{channel_name}"


def _build_help_text(topic: str) -> str:
    if topic == "invite":
        return (
            "**/invite**\n"
            "Use this in any text channel inside a campaign category.\n"
            "It scaffolds the default AIDM layout for that category, including `#context`, `#dm-planning`, "
            "`#session-summary`, and `session-voice`.\n\n"
            "**Typical flow**\n"
            "• Create a category and one starter text channel.\n"
            "• Run `/invite` there.\n"
            "• Read the onboarding post in that same channel.\n"
            "• Use `/help topic:Context` to start loading roster and session guidance."
        )
    if topic == "context":
        return (
            "**/context**\n"
            "Use this to store context that later helps transcripts, summaries, and future visual tooling.\n\n"
            "**Main commands**\n"
            "• `/context add`: add or replace context from notes or selected messages\n"
            "• `/context clear`: clear one scope\n"
            "• `/context list`: inspect the current runtime view of each scope\n\n"
            "**Scopes**\n"
            "• `Public Evergreen`: long-lived campaign facts like roster, spellings, factions, locations.\n"
            "• `Session Only`: current or next-session guidance. It stays active until you replace it or clear it; there is no automatic expiry.\n"
            f"• `DM Private`: DM-only context. Only members with the `{DM_ROLE_NAME}` role can edit it.\n\n"
            "**Good inputs**\n"
            "• Manual notes\n"
            "• `last_n` recent messages from a channel like `#gameplay`\n"
            "• specific `message_ids`\n"
            "• clarifications, art refs, and later image references\n"
            "• optional human-friendly tags like `roster`, `npc`, `location`, `scene`, `style`\n\n"
            "**Examples**\n"
            "• `/context add scope:Public Evergreen action:Append note:<party roster> tags:roster,spelling`\n"
            "• `/context add scope:Session Only action:Replace channel:#gameplay last_n:20`\n"
            "• `/context clear scope:Session Only`"
        )
    if topic == "settings":
        return (
            "**/settings**\n"
            "Use `/settings images` to control automatic post-session image generation for this campaign.\n\n"
            "**Current image settings**\n"
            "• `mode`: `off` or `auto`\n"
            "• `quality`: `auto`, `fast`, or `hq`\n"
            "• `max_scenes`: optional safety cap for auto-generated scenes\n"
            "• `include_dm_context`: whether DM-private context can inform automated images\n"
            "• `post_channel`: where automated images should be posted\n\n"
            "Creative style still belongs in `#context` or `#dm-planning`, not in `/settings`."
        )
    if topic == "ask":
        return (
            "**/ask**\n"
            "• `/ask dm`: rules, spells, monsters, lore, adjudication.\n"
            "• `/ask campaign`: campaign-specific facts, homebrew, NPCs, inventory, status.\n\n"
            "Both commands can target a channel or thread when you want the answer grounded in a specific campaign area.\n"
            "• `/ask campaign` uses campaign context by default.\n"
            "• `/ask dm` keeps context conservative by default, but you can override it with `use_context:on|off|auto`."
        )
    if topic == "channel":
        return (
            "**/channel**\n"
            "• `/channel summarize`: recap selected messages.\n"
            "• `/channel send`: move/copy important content into another channel or thread.\n"
            "• `/channel start`: create a thread or channel flow.\n"
            "• `/channel set_always_on`: decide whether AIDM listens without a mention in that target."
        )
    if topic == "memory":
        return (
            "**/memory**\n"
            "• `/memory list`: inspect memory assignments for this category, channel, or thread.\n"
            "• `/memory assign`: point a channel or thread at a memory.\n"
            "• `/memory delete`: remove a non-default memory.\n"
            "• `/memory reset`: clear a target memory and remove AIDM replies from that target."
        )
    if topic == "reference":
        return (
            "**/reference**\n"
            "Read selected messages, attachments, or a public URL and answer from them.\n"
            "Use this when you want grounded extraction or explanation rather than general campaign recall."
        )
    if topic == "feedback":
        return (
            "**/feedback**\n"
            "Use `/feedback` to capture what worked, what did not, and what should change next time. "
            "It is the lightweight place to leave operational notes after a session or test."
        )
    return (
        "**AIDM Help**\n"
        "Use `/help` with a topic for detail.\n\n"
        "**Topics**\n"
        "• `Invite`: scaffold a campaign category and get started\n"
        "• `Context`: public/session/DM guidance for transcript and summary runs\n"
        "• `Settings`: campaign-level image automation settings\n"
        "• `Ask`: rules or campaign questions\n"
        "• `Channel`: summarization and routing tools\n"
        "• `Memory`: inspect and assign memory behavior\n"
        "• `Reference`: answer from selected messages, files, or URLs\n"
        "• `Feedback`: leave structured follow-up notes\n\n"
        "The fastest next step for a new campaign is: run `/invite`, then use `/help topic:Context`."
    )


def _build_invite_onboarding_message(category: discord.CategoryChannel) -> str:
    context_mention = _get_category_channel_mention(category, "context")
    dm_planning_mention = _get_category_channel_mention(category, "dm-planning")
    worldbuilding_mention = _get_category_channel_mention(category, "worldbuilding")
    session_summary_mention = _get_category_channel_mention(category, "session-summary")
    session_voice_mention = _get_category_channel_mention(category, "session-voice")
    gameplay_mention = _get_category_channel_mention(category, "gameplay")
    return (
        f"**Campaign setup for {category.name} is ready.**\n"
        f"• Use {context_mention} for public evergreen facts and session notes.\n"
        f"• Use {dm_planning_mention} for DM-only material.\n"
        f"• Use {worldbuilding_mention} for locations, factions, lore, custom entities, and `/create other` workspaces.\n"
        f"• Live voice sessions should use {session_voice_mention}.\n"
        f"• Transcript and recap output will land in {session_summary_mention}.\n"
        f"• Session play/chat can happen in {gameplay_mention} and your other campaign channels.\n\n"
        "**Recommended first steps**\n"
        "• Run `/help topic:Context`\n"
        "• Add the party roster and naming/spelling clarifications with `/context add`\n"
        "• Use `Session Only` context for next-session notes, then replace or clear it manually when you are done with it\n"
        f"• Drop useful reference images into {context_mention} as the visual library grows\n"
        "• Use `/settings images` when you want automatic post-session image generation\n"
        "• Use `/generate image` for one-off manual image generation"
    )


def _scope_label(scope_value: str) -> str:
    return {
        "public": "Public Evergreen",
        "session": "Session Only",
        "dm": "DM Private",
    }.get(scope_value, scope_value.title())


def _preview_text(text: str, limit: int = 320) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _context_surface_label(category: discord.CategoryChannel | None, scope_value: str) -> str:
    if not category:
        return "#dm-planning" if scope_value == "dm" else "#context"
    if scope_value == "dm":
        return _get_category_channel_mention(category, "dm-planning")
    return _get_category_channel_mention(category, "context")


def _compiled_context_status(
    category: discord.CategoryChannel | None,
    scope_value: str,
    text: str | None,
    source_label: str,
    asset_count: int = 0,
) -> str:
    text = text.strip() if text else ""
    surface = _context_surface_label(category, scope_value)
    if not text:
        lines_out = [
            f"**{_scope_label(scope_value)}**",
            "• Runtime state: empty",
            f"• Source: {source_label}",
            f"• Discord surface: {surface}",
        ]
        if asset_count:
            lines_out.append(f"• Assets: {asset_count}")
        return "\n".join(lines_out)

    lines = len(text.splitlines())
    chars = len(text)
    preview = _preview_text(text)
    lines_out = [
        f"**{_scope_label(scope_value)}**",
        f"• Runtime state: {chars} chars across {lines} lines",
        f"• Source: {source_label}",
        f"• Discord surface: {surface}",
    ]
    if asset_count:
        lines_out.append(f"• Assets: {asset_count}")
    lines_out.append(f"• Preview: {preview}")
    return "\n".join(lines_out)


def _member_is_dm(interaction: discord.Interaction) -> bool:
    member_roles = getattr(interaction.user, "roles", [])
    return any(getattr(role, "name", None) == DM_ROLE_NAME for role in member_roles)


def _context_asset_from_raw(asset: dict) -> ContextAsset:
    return ContextAsset(
        filename=str(asset.get("filename", "")),
        url=str(asset.get("url", "")),
        proxy_url=asset.get("proxy_url"),
        content_type=asset.get("content_type"),
        source_message_id=asset.get("source_message_id"),
        source_channel_id=asset.get("source_channel_id"),
        is_image=bool(asset.get("is_image")),
        image_bytes=asset.get("image_bytes"),
    )


def _normalize_image_aspect_ratio(value: str | None) -> str | None:
    if not value or value == "auto":
        return None
    return value


def _parse_context_tags(tags: str | None) -> list[str]:
    if not tags:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tags.split(","):
        cleaned = raw.strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _attachment_is_image(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True
    filename = attachment.filename.lower()
    return any(filename.endswith(ext) for ext in IMAGE_EXTENSIONS)


def _extract_context_assets(messages: list[discord.Message]) -> list[dict]:
    assets: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for message in messages:
        for attachment in message.attachments:
            key = (attachment.url, message.id)
            if key in seen:
                continue
            seen.add(key)
            assets.append(
                {
                    "filename": attachment.filename,
                    "url": attachment.url,
                    "content_type": attachment.content_type,
                    "source_message_id": message.id,
                    "source_channel_id": message.channel.id,
                    "is_image": _attachment_is_image(attachment),
                }
            )
    return assets


async def _build_context_material_from_messages(messages: list[discord.Message]) -> list[str]:
    rendered: list[str] = []
    for message in messages:
        parts = [format_message_text(message)]
        for attachment in message.attachments:
            if _attachment_is_image(attachment):
                parts.append(f"[Image attachment preserved separately: {attachment.filename}]")
                continue
            try:
                extracted = await extract_attachment_text(attachment)
                parts.append(f"[Attachment: {attachment.filename}]\n{extracted}")
            except Exception as exc:
                logger.warning(
                    "Failed to extract non-image attachment %s from message %s while building context: %s",
                    attachment.filename,
                    message.id,
                    exc,
                )
                parts.append(f"[Attachment present but unreadable: {attachment.filename}. Reason: {exc}]")
        rendered.append("\n\n".join(parts))
    return rendered


async def _resolve_context_source_target(
    interaction: discord.Interaction,
    *,
    channel: str | None,
    thread: str | None,
) -> discord.abc.GuildChannel | discord.Thread | None:
    source_target = interaction.channel
    if channel:
        source_target = interaction.guild.get_channel(int(channel))
    if thread:
        source_target = await interaction.guild.fetch_channel(int(thread))
    return source_target


async def _collect_latest_session_summaries(category: discord.CategoryChannel | None) -> tuple[str | None, str | None]:
    if category is None:
        return None, None
    summary_channel = discord.utils.get(category.text_channels, name="session-summary")
    if summary_channel is None:
        return None, None

    objective_lines: list[str] = []
    narrative_lines: list[str] = []
    current_section: str | None = None

    messages = [message async for message in summary_channel.history(limit=80)]
    messages.reverse()
    for message in messages:
        content = (message.content or "").strip()
        if not content:
            continue
        if content == "**Objective Summary**":
            objective_lines = []
            current_section = "objective"
            continue
        if content == "**Narrative Summary**":
            narrative_lines = []
            current_section = "narrative"
            continue
        if content.startswith("**") and content.endswith("**"):
            current_section = None
            continue
        if current_section == "objective":
            objective_lines.append(content)
        elif current_section == "narrative":
            narrative_lines.append(content)

    objective = "\n".join(objective_lines).strip() or None
    narrative = "\n".join(narrative_lines).strip() or None
    return objective, narrative


async def _send_generated_image_message(
    destination: discord.abc.Messageable,
    *,
    title: str,
    subtitle_lines: list[str],
    image_bytes: bytes,
    mime_type: str,
    index: int = 1,
) -> None:
    extension = ".png" if mime_type == "image/png" else ".jpg"
    filename = f"generated_image_{index:02d}{extension}"
    file = discord.File(io.BytesIO(image_bytes), filename=filename)
    message = f"**{title}**"
    if subtitle_lines:
        message += "\n" + "\n".join(subtitle_lines)
    await destination.send(message, file=file)


async def _update_context_scope(
    interaction: discord.Interaction,
    *,
    scope_value: str,
    action_value: str,
    note: str | None,
    start: str | None,
    end: str | None,
    message_ids: str | None,
    last_n: int | None,
    channel: str | None,
    thread: str | None,
    tags: str | None,
) -> str:
    if scope_value == "dm" and not _member_is_dm(interaction):
        raise PermissionError(f"Only members with the `{DM_ROLE_NAME}` role can change DM-private summary context.")

    source_target = await _resolve_context_source_target(interaction, channel=channel, thread=thread)
    if source_target is None and action_value != "clear":
        raise ValueError("Source channel or thread not found.")

    selected_messages = []
    parts: list[str] = []
    source_mode = "manual_note"
    parsed_tags = _parse_context_tags(tags)
    if action_value != "clear" and any(value is not None for value in (start, end, message_ids, last_n)):
        selected_messages, options_or_error = await select_messages(
            source_target,
            start,
            end,
            message_ids,
            last_n,
        )
        if isinstance(options_or_error, str):
            raise ValueError(options_or_error)
        material = await _build_context_material_from_messages(selected_messages)
        parts.append("\n\n".join(material))
        source_mode = "selected_messages"

    if action_value != "clear" and note:
        parts.append(note.strip())
        source_mode = "mixed" if source_mode == "selected_messages" else "manual_note"

    if action_value != "clear" and not parts:
        raise ValueError("Provide message selectors and/or a manual note, or use `/context clear`.")

    destination_channel = None
    category = interaction.channel.category
    if category:
        if scope_value == "dm":
            destination_channel = discord.utils.get(category.text_channels, name="dm-planning")
        else:
            destination_channel = discord.utils.get(category.text_channels, name="context")
    if destination_channel is None:
        raise ValueError("Could not find the destination context channel for this category.")

    stored_text = "\n\n".join(part for part in parts if part).strip()
    source_label = _describe_context_source(source_target) if source_target else "manual note"
    source_message_ids = [message.id for message in selected_messages]
    assets = _extract_context_assets(selected_messages)
    messages = build_context_entry_messages(
        scope=scope_value,
        action=action_value,
        text=stored_text,
        source_label=source_label,
        source_mode=source_mode if action_value != "clear" else "clear",
        actor_name=getattr(interaction.user, "mention", interaction.user.display_name),
        actor_id=getattr(interaction.user, "id", None),
        source_channel_id=getattr(source_target, "id", None),
        source_message_ids=source_message_ids,
        tags=parsed_tags,
        assets=assets,
    )
    for message in messages:
        await destination_channel.send(message)

    logger.info(
        "Published %s context entry to #%s using %s",
        scope_value,
        destination_channel.name,
        action_value,
    )
    if scope_value == "dm":
        return (
            "Updated `dm` summary context. "
            f"Published to {destination_channel.mention}. "
            "DM context is only included when DM context is explicitly enabled for a run."
        )
    session_note = ""
    if scope_value == "session":
        session_note = " Session context stays active until you replace it or clear it; it does not expire automatically."
    return f"Updated `{scope_value}` summary context. Published to {destination_channel.mention}.{session_note}"


def _describe_context_source(source_target: discord.abc.GuildChannel | discord.Thread | None) -> str:
    if source_target is None:
        return "manual note"
    if isinstance(source_target, discord.Thread):
        return f"{source_target.mention} in {source_target.parent.mention}" if source_target.parent else source_target.mention
    if hasattr(source_target, "mention"):
        return source_target.mention
    return getattr(source_target, "name", "manual note")


def _default_npc_card_inventory_text() -> str:
    descriptions = {
        "Summary Card": "High-level identity, role, faction, CR, status, and last seen location.",
        "Profile Card": "Name, aliases, race/type, age, appearance, and distinctive features.",
        "Personality & Hooks": "Traits, ideals, flaws, bonds, secrets, and party hooks.",
        "Stat Block": "Core combat statistics, actions, and creature abilities.",
        "Relationships": "Party relationships, NPC connections, and faction standing.",
    }
    return "\n".join(f"- {title}: {descriptions[title]}" for title in NPC_DEFAULT_CARD_TITLES)


def _default_npc_cascade_rules_text() -> str:
    return "\n".join(
        [
            "- Faction or allegiance change -> Summary Card, Profile Card, Relationships",
            "- Race or creature type change -> Profile Card, Stat Block",
            "- Role or status change -> Summary Card, Relationships, Personality & Hooks",
            "- Adding abilities, spells, or items -> Stat Block, Summary Card",
            "- Party relationship changes -> Relationships, Personality & Hooks",
        ]
    )


async def _ensure_workspace_thread(
    interaction: discord.Interaction,
    *,
    display_name: str,
    thread_prefix: str,
    memory_prefix: str,
    target_channel_name: str,
    reuse_channel_memory: bool = False,
) -> tuple[discord.TextChannel, discord.Thread, bool]:
    category = get_interaction_category(interaction)
    if category is None:
        raise ValueError("Run this command inside a campaign category.")

    sheets_channel = discord.utils.get(category.text_channels, name=target_channel_name)
    if sheets_channel is None:
        sheets_channel = await interaction.guild.create_text_channel(name=target_channel_name, category=category)

    await asyncio.to_thread(
        ensure_channel_for_category,
        category.id,
        sheets_channel.id,
        sheets_channel.name,
        False,
        False,
    )

    thread_name = f"{thread_prefix} - {display_name}"
    workspace_thread, created_thread = await find_or_create_player_thread(sheets_channel, thread_name)

    context = await asyncio.to_thread(
        get_or_create_campaign_context,
        interaction.guild.id,
        interaction.guild.name,
        category.id,
        category.name,
        DM_ROLE_NAME,
    )
    await asyncio.to_thread(ensure_thread_for_channel, sheets_channel.id, workspace_thread.id, workspace_thread.name, True)

    if reuse_channel_memory:
        channel_memory_name = target_channel_name
        channel_memory_id = await asyncio.to_thread(ensure_memory, context.campaign_id, channel_memory_name)
        await asyncio.to_thread(assign_memory_to_channel, sheets_channel.id, channel_memory_id)
    else:
        memory_name = f"{memory_prefix}-{slugify_player_key(display_name)}"
        memory_id = await asyncio.to_thread(ensure_memory, context.campaign_id, memory_name)
        await asyncio.to_thread(assign_memory_to_thread, workspace_thread.id, memory_id)
        await asyncio.to_thread(set_thread_always_on, workspace_thread.id, True)
    return sheets_channel, workspace_thread, created_thread


async def _seed_workspace_thread(
    *,
    get_assistant_response,
    thread: discord.Thread,
    category_id: int | None,
    note: str | None,
    system_prompt: str,
) -> None:
    memory_id = await get_assigned_memory(thread.parent.id if thread.parent else thread.id, category_id, thread.id)
    if not memory_id:
        return
    user_text = (note or "").strip() or "The workspace has just been created. Acknowledge briefly and invite the user to keep adding notes or ask for edits."
    response = await get_assistant_response(
        user_text,
        thread.parent.id if thread.parent else thread.id,
        category_id,
        thread.id,
        memory_id,
        system_prompt=system_prompt,
    )
    if response:
        await send_response_in_chunks(thread, response)

def setup_commands(tree, get_assistant_response):
    register_command_modules(tree, get_assistant_response, globals())
