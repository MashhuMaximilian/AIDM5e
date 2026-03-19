# bot_commands.py

import asyncio
import io
import logging

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
    build_thread_data_snapshot,
    fetch_memory_details,
    get_campaign_image_settings,
    update_campaign_image_settings,
)
from data_store.memory_management import *
from prompts.summary_prompts import build_feedback_prompt

from .helper_functions import *
from .shared_functions import *
from .shared_functions import apply_always_on, send_response_in_chunks

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
            "• `/context list`: inspect the current runtime view of each scope\n"
            "• `/context summary`: legacy alias for `/context add`\n\n"
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
            "Both commands can target a channel or thread when you want the answer grounded in a specific campaign area."
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
    session_summary_mention = _get_category_channel_mention(category, "session-summary")
    session_voice_mention = _get_category_channel_mention(category, "session-voice")
    gameplay_mention = _get_category_channel_mention(category, "gameplay")
    return (
        f"**Campaign setup for {category.name} is ready.**\n"
        f"• Use {context_mention} for public evergreen facts and session notes.\n"
        f"• Use {dm_planning_mention} for DM-only material.\n"
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


def setup_commands(tree, get_assistant_response):
    ask_group = app_commands.Group(name="ask", description="Rules and lore commands.")
    channel_group = app_commands.Group(name="channel", description="Channel and thread commands.")
    memory_group = app_commands.Group(name="memory", description="Memory management commands.")
    context_group = app_commands.Group(name="context", description="Context helpers for summaries and transcripts.")
    settings_group = app_commands.Group(name="settings", description="Campaign settings commands.")
    generate_group = app_commands.Group(name="generate", description="Image and media generation commands.")

    @tree.command(name="help", description="Show command help and campaign onboarding guidance.")
    @app_commands.describe(topic="Optional topic to explain in more detail.")
    @app_commands.choices(
        topic=[app_commands.Choice(name=label, value=value) for value, label in HELP_TOPICS]
    )
    async def help_command(
        interaction: discord.Interaction,
        topic: app_commands.Choice[str] | None = None,
    ):
        help_topic = topic.value if topic else "overview"
        await send_interaction_message(interaction, _build_help_text(help_topic), ephemeral=True)


    @ask_group.command(name="campaign", description="Campaign info lookup. Defaults to #telldm if no target is set.")
    @app_commands.describe(
        query="What you want to know.",
        channel="Optional target channel. Defaults to #telldm in this category.",
        thread="Optional target thread. Overrides the channel target when set."
    )
    @app_commands.choices(
        query_type=[
            app_commands.Choice(name="Check Status", value="checkstatus"),
            app_commands.Choice(name="Homebrew", value="homebrew"),
            app_commands.Choice(name="NPC", value="npc"),
            app_commands.Choice(name="Inventory", value="inventory"),
            app_commands.Choice(name="Roll Check", value="rollcheck")
        ]
    )
   
    async def tellme(interaction: discord.Interaction, query_type: app_commands.Choice[str], query: str, channel: str = None, thread: str = None):
        await process_query_command(interaction, query_type, query, backup_channel_name="telldm", channel=channel, thread=thread)

    # Autocomplete for channels
    @tellme.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        # Call the existing channel autocomplete function
        choices = await channel_autocomplete(interaction, current)
        return choices[:25]  # Limit to 25 suggestions
    ## Autocomplete for threads in tellme
    @tellme.autocomplete('thread')
    async def tellme_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)


    # Main logic for the askdm command (same for tellme command)
    @ask_group.command(name="dm", description="Rules and lore lookup. Defaults to #telldm if no target is set.")
    @app_commands.describe(
        query="Your rules, lore, or adjudication question.",
        channel="Optional target channel. Defaults to #telldm in this category.",
        thread="Optional target thread. Overrides the channel target when set."
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
        ]
    )
    async def askdm(interaction: discord.Interaction, query_type: app_commands.Choice[str], query: str, channel: str = None, thread: str = None):
        await process_query_command(interaction, query_type, query, backup_channel_name="telldm", channel=channel, thread=thread)

    # Autocomplete for channels
    @askdm.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        choices = await channel_autocomplete(interaction, current)
        return choices[:25]  # Limit to 25 suggestions
    # Autocomplete for threads
    @askdm.autocomplete('thread')
    async def askdm_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)



    @channel_group.command(name="summarize", description="Summarize selected messages. Defaults to this channel.")
    @app_commands.describe(
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to summarize.",
        query="Additional requests or context for the recap.",
        last_n="Summarize the last 'n' messages (optional).",
        channel="Optional target channel and memory for the answer. Defaults to this channel.",
        thread="Optional target thread and memory for the answer."
    )
    async def summarize(interaction: discord.Interaction, start: str = None, end: str = None, message_ids: str = None, query: str = None, last_n: int = None, channel: str = None, thread: str = None):
        await interaction.response.defer()  # Defer the response while processing

        # Fetch the channel and thread if specified
        channel_id = int(channel) if channel else interaction.channel.id
        thread_id = int(thread) if thread else None
        category_id = get_category_id(interaction)

        
        # Fetch the assigned memory for the provided channel and thread
        assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id=thread_id)

        # Fetch conversation history based on provided parameters, including readable attachment content
        conversation_history, options_or_error = await fetch_reference_material(interaction.channel, start, end, message_ids, last_n)

        # Check if the response is an error message
        if isinstance(options_or_error, str):
            await interaction.followup.send(options_or_error)  # Send error message
            return

        options = options_or_error  # Assign the options for summarization

        # Summarize the conversation, passing assigned_memory to the summarization function
        response = await summarize_conversation(interaction, conversation_history, options, query, channel_id, thread_id, assigned_memory)

        # Send the summarized response in chunks
        if response:  # Ensure response is not empty
            await send_response(interaction, response, channel_id=channel_id, thread_id=thread_id)
        else:
            await interaction.followup.send("No content to summarize.")  # Optional: handle empty response

            # Autocomplete functions for channel and thread parameters
    @summarize.autocomplete('channel')  # Note that the parameter name is 'channel', not 'channel_id'
    async def target_channel_autocomplete(interaction: discord.Interaction, current: str):
                return await channel_autocomplete(interaction, current)

    @summarize.autocomplete('thread')  # Note that the parameter name is 'thread', not 'thread_id'
    async def send_thread_autocomplete(interaction: discord.Interaction, current: str):
                return await thread_autocomplete(interaction, current)

    @tree.command(name="reference", description="Read messages, files, or a URL and answer from them.")
    @app_commands.describe(
        query="What you want AIDM to extract, explain, or answer from the references.",
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to read.",
        last_n="Read the last 'n' messages (optional).",
        url="Optional public URL to read as additional context.",
        channel="Optional target channel and memory for the answer. Defaults to this channel.",
        thread="Optional target thread and memory for the answer."
    )
    async def reference(
        interaction: discord.Interaction,
        query: str,
        start: str = None,
        end: str = None,
        message_ids: str = None,
        last_n: int = None,
        url: str = None,
        channel: str = None,
        thread: str = None,
    ):
        await interaction.response.defer()

        channel_id = int(channel) if channel else interaction.channel.id
        thread_id = int(thread) if thread else None
        category_id = get_category_id(interaction)
        assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id=thread_id)
        if not assigned_memory:
            await interaction.followup.send("No memory found for the specified parameters.")
            return

        reference_chunks: list[str] = []
        if any(value is not None for value in (start, end, message_ids, last_n)):
            reference_material, options_or_error = await fetch_reference_material(
                interaction.channel,
                start,
                end,
                message_ids,
                last_n,
            )
            if isinstance(options_or_error, str):
                await interaction.followup.send(options_or_error)
                return
            reference_chunks.extend(reference_material)

        has_message_refs = any(value is not None for value in (start, end, message_ids, last_n))

        if not reference_chunks and not url:
            await interaction.followup.send("You must provide message selectors and/or a public URL.")
            return

        if url and not has_message_refs:
            try:
                response = await answer_from_public_url(
                    query=query,
                    url=url,
                    channel_id=channel_id,
                    assigned_memory=assigned_memory,
                    thread_id=thread_id,
                )
            except Exception as exc:
                await interaction.followup.send(f"Could not read the URL: {exc}")
                return
        else:
            if url:
                try:
                    reference_chunks.append(f"[Public URL: {url}]\n{await extract_public_url_text(url)}")
                except Exception as exc:
                    reference_chunks.append(
                        f"[Public URL could not be fetched directly: {url}. Reason: {exc}. "
                        "Use the other provided material and note that the URL may require a different retrieval path.]"
                    )

            response = await answer_from_references(
                query=query,
                reference_material=reference_chunks,
                channel_id=channel_id,
                assigned_memory=assigned_memory,
                thread_id=thread_id,
                url=url,
            )
        await send_response(
            interaction,
            response,
            channel_id=channel_id,
            thread_id=thread_id,
            backup_channel_name="telldm",
        )

    @reference.autocomplete('channel')
    async def reference_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @reference.autocomplete('thread')
    async def reference_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)


    @tree.command(name="feedback", description="Send feedback to #feedback and generate a recap there.")
    async def feedback(interaction: discord.Interaction, suggestions: str):
        await interaction.response.defer()  # Defer the response while processing the feedback

        # Step 1: Check if 'feedback' channel exists in the same category
        feedback_channel = discord.utils.get(interaction.channel.category.channels, name="feedback")

        # If the channel doesn't exist, create it
        if feedback_channel is None:
            guild = interaction.guild
            feedback_channel = await guild.create_text_channel(name="feedback", category=interaction.channel.category)
            await interaction.followup.send(f"The #feedback channel was not found, so I created it in the same category.")

        # Step 2: Send the feedback message to #feedback
        feedback_message = await feedback_channel.send(f"Feedback from {interaction.user.name}: {suggestions}")
        await interaction.followup.send(f"Your feedback has been sent to {feedback_channel.mention}.")

        # Step 3: Fetch all messages from the #feedback channel
        messages = []
        async for message in feedback_channel.history(limit=300):
            messages.append(f"{message.author.name}: {message.content}")

        if not messages:
            await interaction.followup.send(f"No messages found in {feedback_channel.mention}.")
            return

        # Step 4: Get the last message for focus in summarization
        last_message = messages[0]  # The most recent message is at the start of the list

        # Create a conversation history from all the messages
        conversation_history = "\n".join(reversed(messages))  # Reversed so that it reads from oldest to newest

        # Step 5: Get the assigned memory for the feedback channel
        category_id = get_category_id(interaction)
        assigned_memory = await get_assigned_memory(feedback_channel.id, category_id, thread_id=None)

        # Step 6: Send the conversation to the assistant for summarization, focusing on the last message
        prompt = build_feedback_prompt(conversation_history, last_message)

        # Update the assistant response call with the correct memory
        response = await get_assistant_response(prompt, feedback_channel.id, thread_id=None, assigned_memory=assigned_memory)


        await send_response(interaction, response, channel_id=None, thread_id=None, backup_channel_name="feedback")

        # Step 7: Confirm that the feedback was processed
        await interaction.followup.send(f"Feedback has been processed and a recap has been posted in {feedback_channel.mention}.")

    @channel_group.command(name="send", description="Copy selected messages to another channel or thread.")
    @app_commands.describe(
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to send (comma-separated if multiple).",
        last_n="Send the last 'n' messages (optional).",
        channel="Target channel in this category. Defaults to the current channel.",
        thread="Optional target thread inside the chosen channel."
    )
    async def send(
        interaction: discord.Interaction, 
        start: str = None, 
        end: str = None, 
        message_ids: str = None, 
        last_n: int = None, 
        channel: str = None, 
        thread: str = None
    ):
        await send_command_ack(interaction, "Sending messages...")

        # Fetch the channel and thread if specified
        channel_id = int(channel) if channel else interaction.channel.id
        thread_id = int(thread) if thread else None
        category_id = get_category_id(interaction)

        # Fetch conversation history based on the provided parameters
        conversation_history, options_or_error = await fetch_conversation_history(interaction.channel, start, end, message_ids, last_n)

        # Handle errors if conversation history is empty or invalid
        if isinstance(options_or_error, str):
            await interaction.followup.send(options_or_error)  # Send error message
            return

        # Assign the fetched options (for message selection)
        options = options_or_error

        # Fetch the target channel object
        target_channel_obj = interaction.guild.get_channel(channel_id)

        if not target_channel_obj:
            await interaction.followup.send("Target channel not found.")
            return

        # Check if the target channel is in the same category
        if target_channel_obj.category_id != interaction.channel.category_id:
            await interaction.followup.send(f"Cannot send messages to {target_channel_obj.name}. Must be in the same category.")
            return

        # If a thread is specified, fetch the thread
        target = target_channel_obj
        if thread:
            target = await interaction.guild.fetch_channel(thread_id)  # Fetch the thread object

        # Send all messages in the conversation history to the target (either thread or channel)
        for message in conversation_history:
            await send_response_in_chunks(target, message)

        assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id=thread_id)
        if assigned_memory:
            imported_content = "\n\n".join(conversation_history)
            acknowledgment_prompt = (
                "A user transferred the following Discord content into this channel or thread. "
                "Acknowledge briefly what was added and mention the most important fact or takeaway "
                "AIDM should now keep in mind for this memory. Keep the answer to at most 3 short bullets.\n\n"
                f"Transferred content:\n{imported_content}"
            )
            acknowledgment = await get_assistant_response(
                acknowledgment_prompt,
                channel_id,
                category_id,
                thread_id,
                assigned_memory=assigned_memory,
                send_message=False,
            )
            if acknowledgment:
                await send_response_in_chunks(target, acknowledgment)

        # Notify the user about the success after all messages are sent
        await interaction.followup.send(f"Messages sent successfully to {'thread' if thread else 'channel'} <#{target.id}>.")

    # Autocomplete for the target_channel field
    @send.autocomplete('channel')
    async def target_channel_autocomplete(interaction: discord.Interaction, current: str):
        # Use the existing channel autocomplete function
        choices = await channel_autocomplete(interaction, current)
        return choices[:25]  # Limit to 25 suggestions
    # Autocomplete for the thread field
    @send.autocomplete('thread')
    async def send_thread_autocomplete(interaction: discord.Interaction, current: str):
        # Use the thread autocomplete function
        return await thread_autocomplete(interaction, current)

    @channel_group.command(name="start", description="Create a channel/thread in this category and assign its memory.")
    @app_commands.describe(
        channel="Choose an existing channel or 'NEW CHANNEL' to create a new one.",
        channel_name="Name for the new channel (only if 'NEW CHANNEL' is selected).",
        thread_name="Name for the new thread (only if you choose 'CREATE A NEW THREAD').",
        memory="Choose an existing memory or create a new one.",
        memory_name="Provide a name for the new memory (only if 'CREATE NEW MEMORY' is selected).",
        always_on="Set the assistant always on or off."
    )
    @app_commands.choices(always_on=[
        app_commands.Choice(name="On", value="on"),
        app_commands.Choice(name="Off", value="off")
    ])
    async def startnew_command(
        interaction: discord.Interaction,
        channel: str,
        always_on: app_commands.Choice[str],
        memory: str,
        memory_name: str = None,
        channel_name: str = None,
        thread_name: str = None,
        thread: str = None
    ):
        # Validate parameters
        if channel == "NEW CHANNEL" and not channel_name:
            await send_interaction_message(interaction, "Error: You must provide a name for the new channel.")
            return
        if thread == "NEW THREAD" and not thread_name:
            await send_interaction_message(interaction, "Error: You must provide a name for the new thread.")
            return
        if memory == "CREATE NEW MEMORY" and not memory_name:
            await send_interaction_message(interaction, "Error: You must provide a name for the new memory.")
            return

        await send_command_ack(interaction, "Creating channel or thread...")

        # Retrieve guild and category
        guild = interaction.guild
        category = interaction.channel.category

        # Create or get the target channel
        target_channel = await handle_channel_creation(channel, channel_name, guild, category, interaction)
        if target_channel is None:
            return

        logging.info(f"Target channel ID: {target_channel.id}, Name: {target_channel.name}")

        # Handle thread creation if "NEW THREAD" is selected
        thread_obj = None
        if thread == "NEW THREAD":
            thread_obj, error = await handle_thread_creation(interaction, target_channel, thread_name, category.id, memory_name)
            if error:
                await send_interaction_message(interaction, error)
                return
        elif thread:  # Fetch existing thread if provided
            thread_obj = await interaction.guild.fetch_channel(int(thread))

        # Assign memory to the channel
        target_channel, _ = await handle_memory_assignment(
            interaction,
            memory,
            str(target_channel.id),
            None,  # No thread involved here
            memory_name,
            always_on
        )

        # Assign memory to the thread if applicable
        if thread_obj:
            _, target_thread = await handle_memory_assignment(
                interaction,
                memory,
                str(target_channel.id),
                str(thread_obj.id),
                memory_name,
                always_on
            )

        # Prepare follow-up messages based on the scenario
        always_on_status = "ON" if always_on.value.lower() == "on" else "OFF"
        followup_messages = []

        # Channel follow-up
        followup_messages.append(
            f"Created channel '<#{target_channel.id}>' with assigned memory: '{memory_name or memory}' "
            f"and Always_on set to: [{always_on_status}]."
        )

        # Thread follow-up
        if thread_obj:
            followup_messages.append(
                f"Created thread '<#{thread_obj.id}>' in channel '<#{target_channel.id}>' with assigned memory: "
                f"'{memory_name or memory}' and Always_on set to: [{always_on_status}]."
            )

        # Send the combined follow-up messages
        await send_interaction_message(interaction, "\n".join(followup_messages))

    @startnew_command.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        # Call the existing channel autocomplete function
        choices = await channel_autocomplete(interaction, current)

        # Add the option to create a new channel
        choices.append(discord.app_commands.Choice(name="CREATE A NEW CHANNEL", value="NEW CHANNEL"))

        return choices[:50]  # Limit to 50 suggestions

    @startnew_command.autocomplete('thread')
    async def thread_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        # Call the existing thread autocomplete function
        choices = await thread_autocomplete(interaction, current)

        # Add the option to create a new thread
        choices.append(discord.app_commands.Choice(name="CREATE A NEW THREAD", value="NEW THREAD"))

        return choices[:50]  # Limit to 50 suggestions

    @startnew_command.autocomplete('memory')
    async def memory_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await memory_autocomplete(interaction, current)


            

    @memory_group.command(name="assign", description="Assign an existing or new memory to a channel or thread.")
    @app_commands.describe(
        channel="Channel to update.",
        memory="Existing memory name, or choose CREATE NEW MEMORY.",
        thread="Optional thread to override the channel memory.",
        memory_name="Required only when creating a new memory.",
        always_on="Optionally toggle the assistant on for all messages there."
    )
    @app_commands.choices(always_on=[
        app_commands.Choice(name="On", value="on"),
        app_commands.Choice(name="Off", value="off")
    ])
    async def assign_memory_command(
        interaction: discord.Interaction,
        channel: str,
        memory: str,
        thread: str = None,
        memory_name: str = None,
        always_on: app_commands.Choice[str] = None  # Optional
    ):
        await send_command_ack(interaction, "Assigning memory...")

        # Handle memory assignment
        target_channel, target_thread = await handle_memory_assignment(
            interaction, memory, channel, thread, memory_name, always_on
        )

        # Handle response based on the results
        if target_thread:
            await send_interaction_message(
                interaction,
                f"Memory '{memory}' assigned successfully to thread {target_thread.mention} in channel {target_channel.mention}."
            )
        elif target_channel:
            await send_interaction_message(
                interaction,
                f"Memory '{memory}' assigned successfully to channel {target_channel.mention}."
                
            )
        else:
            await send_interaction_message(interaction, f"Memory '{memory}' assigned, but the specified channel or thread was not found.")

    @assign_memory_command.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @assign_memory_command.autocomplete('memory')
    async def memory_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await memory_autocomplete(interaction, current)

    @assign_memory_command.autocomplete('thread')
    async def thread_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)
    


    @channel_group.command(name="set_always_on", description="Toggle whether AIDM listens without needing a mention.")
    @app_commands.describe(
        channel="Channel to update.",
        thread="Optional thread to update instead of the whole channel.",
        always_on="Choose whether AIDM should listen to every message there."
    )
    @app_commands.choices(always_on=[
        app_commands.Choice(name="On", value="on"),
        app_commands.Choice(name="Off", value="off")
    ])
    async def set_always_on_command(
        interaction: discord.Interaction,
        channel: str,
        thread: str = None,
        always_on: app_commands.Choice[str] = None  # Optional; defaults to "off" if not specified
    ):
        await send_command_ack(interaction, "Updating always-on setting...")

        # Explicitly parse always_on as True (on) or False (off)
        always_on_value = always_on and always_on.value == "on"

        # Fetch channel and thread objects
        target_channel = interaction.guild.get_channel(int(channel)) if channel.isdigit() else None
        target_thread = await interaction.guild.fetch_channel(int(thread)) if thread else None

        if target_thread:
            await set_always_on(target_thread, always_on_value)
            await send_interaction_message(
                interaction,
                f"Assistant 'always on' set to {'on' if always_on_value else 'off'} for thread {target_thread.mention}."
            )
        elif target_channel:
            await set_always_on(target_channel, always_on_value)
            await send_interaction_message(
                interaction,
                f"Assistant 'always on' set to {'on' if always_on_value else 'off'} for channel {target_channel.mention}."
            )
        else:
            await send_interaction_message(interaction, "Error: Invalid channel or thread specified.")

        # Log the action
        logging.info(f"{'Thread' if target_thread else 'Channel'} {target_thread.id if target_thread else target_channel.id} 'always on' set to: {always_on_value}")

    @set_always_on_command.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @set_always_on_command.autocomplete('thread')
    async def thread_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)
    

    @memory_group.command(name="delete", description="Delete a non-default memory from this campaign.")
    async def delete_memory_command(interaction: discord.Interaction, memory: str):
        await send_command_ack(interaction, "Deleting memory...")

        result = delete_memory(memory, interaction.channel.category.id)
        if "deleted successfully" in result.lower():
            await set_default_memory(str(interaction.channel.category.id))
            result = (
                f"{result}\n"
                "Any channels or threads that used this memory no longer have a direct assignment. "
                "They may now resolve to their channel or campaign default memory. Use `/memory assign` "
                "to set a replacement explicitly, or delete/rework the affected thread or channel if needed."
            )
        await send_interaction_message(interaction, result)

    # Add autocomplete functionality for the memory argument
    @delete_memory_command.autocomplete('memory')
    async def memory_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await memory_autocomplete(interaction, current)


    @tree.command(name="invite", description="Initialize the default AIDM channel layout for this category.")
    async def invite_command(interaction: discord.Interaction):
        """Initialize threads and channels for the category where the command is invoked."""
        category = interaction.channel.category  # Get the category of the current channel
        
        if not category:
            await interaction.response.send_message("This command must be used in a category channel.")
            return
        
        # Acknowledge the interaction immediately
        await send_command_ack(interaction, "Initializing campaign...")

        try:
            invite_result = await initialize_threads(category)
        except ValueError as exc:
            await interaction.followup.send(str(exc))
            return

        created = ", ".join(invite_result["created"]) if invite_result["created"] else "none"
        reused = ", ".join(invite_result["reused"]) if invite_result["reused"] else "none"
        created_voice = ", ".join(invite_result["created_voice"]) if invite_result["created_voice"] else "none"
        reused_voice = ", ".join(invite_result["reused_voice"]) if invite_result["reused_voice"] else "none"
        await interaction.followup.send(
            f"Campaign initialized for **{category.name}**.\n"
            f"Created channels: {created}\n"
            f"Reused channels: {reused}\n"
            f"Created voice channels: {created_voice}\n"
            f"Reused voice channels: {reused_voice}"
        )
        if hasattr(interaction.channel, "send"):
            await send_response_in_chunks(interaction.channel, _build_invite_onboarding_message(category))

    @settings_group.command(name="images", description="Configure automatic post-session image generation for this campaign.")
    @app_commands.describe(
        mode="Whether images are generated automatically after summaries.",
        quality="Default quality policy for automatic session images.",
        max_scenes="Optional cap for how many scenes can be generated automatically. Use 0 to clear the cap.",
        include_dm_context="Whether automatic images can consume DM-private context.",
        post_channel="Optional post target. Defaults to #session-summary when unset.",
    )
    @app_commands.choices(mode=IMAGE_MODE_CHOICES, quality=IMAGE_QUALITY_CHOICES)
    async def settings_images(
        interaction: discord.Interaction,
        mode: app_commands.Choice[str] | None = None,
        quality: app_commands.Choice[str] | None = None,
        max_scenes: int | None = None,
        include_dm_context: bool | None = None,
        post_channel: str | None = None,
    ):
        if not _member_is_dm(interaction):
            await send_interaction_message(
                interaction,
                f"Only members with the `{DM_ROLE_NAME}` role can update campaign image settings.",
                ephemeral=True,
            )
            return

        category = interaction.channel.category
        if category is None:
            await send_interaction_message(interaction, "This command must be used inside a campaign category.", ephemeral=True)
            return

        current = await asyncio.to_thread(get_campaign_image_settings, category.id)
        new_max_scenes = current.session_image_max_scenes
        if max_scenes is not None:
            new_max_scenes = None if max_scenes <= 0 else max_scenes

        new_post_channel_id = current.session_image_post_channel_id
        if post_channel is not None:
            resolved_channel = interaction.guild.get_channel(int(post_channel))
            if not isinstance(resolved_channel, discord.TextChannel) or resolved_channel.category_id != category.id:
                await send_interaction_message(
                    interaction,
                    "The post channel must be a text channel inside this campaign category.",
                    ephemeral=True,
                )
                return
            new_post_channel_id = int(post_channel)

        updated = await asyncio.to_thread(
            update_campaign_image_settings,
            category.id,
            session_image_mode=mode.value if mode else current.session_image_mode,
            session_image_quality=quality.value if quality else current.session_image_quality,
            session_image_max_scenes=new_max_scenes,
            session_image_include_dm_context=include_dm_context if include_dm_context is not None else current.session_image_include_dm_context,
            session_image_post_channel_id=new_post_channel_id,
        )

        post_target = interaction.guild.get_channel(updated.session_image_post_channel_id) if updated.session_image_post_channel_id else discord.utils.get(category.text_channels, name="session-summary")
        post_label = post_target.mention if isinstance(post_target, discord.TextChannel) else "#session-summary"
        max_scenes_label = updated.session_image_max_scenes if updated.session_image_max_scenes is not None else "no cap"
        await send_interaction_message(
            interaction,
            (
                f"**Image settings for {category.mention}**\n"
                f"• mode: `{updated.session_image_mode}`\n"
                f"• quality: `{updated.session_image_quality}`\n"
                f"• max_scenes: `{max_scenes_label}`\n"
                f"• include_dm_context: `{updated.session_image_include_dm_context}`\n"
                f"• post_channel: {post_label}"
            ),
            ephemeral=True,
        )

    @settings_images.autocomplete("post_channel")
    async def settings_images_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @context_group.command(name="add", description="Add or replace public, session, or DM context for future transcript/summary runs.")
    @app_commands.describe(
        scope="Which context bucket to update.",
        action="Whether to replace or append to that bucket.",
        note="Optional manual text to store as context.",
        tags="Optional comma-separated tags such as roster, npc, location, scene, style.",
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to include.",
        last_n="Use the last 'n' messages from the source target.",
        channel="Optional source channel. Defaults to this channel.",
        thread="Optional source thread. Overrides the source channel when set.",
    )
    @app_commands.choices(
        scope=CONTEXT_SCOPE_CHOICES,
        action=CONTEXT_WRITE_ACTION_CHOICES,
    )
    async def context_add(
        interaction: discord.Interaction,
        scope: app_commands.Choice[str],
        action: app_commands.Choice[str],
        note: str = None,
        tags: str = None,
        start: str = None,
        end: str = None,
        message_ids: str = None,
        last_n: int = None,
        channel: str = None,
        thread: str = None,
    ):
        await send_command_ack(interaction, "Updating context...")

        try:
            response_text = await _update_context_scope(
                interaction,
                scope_value=scope.value,
                action_value=action.value,
                note=note,
                tags=tags,
                start=start,
                end=end,
                message_ids=message_ids,
                last_n=last_n,
                channel=channel,
                thread=thread,
            )
            await send_interaction_message(interaction, response_text, ephemeral=True)
        except PermissionError as exc:
            await send_interaction_message(interaction, str(exc), ephemeral=True)
        except Exception as exc:
            logger.exception("Error updating context: %s", exc)
            await send_interaction_message(interaction, f"Could not update context: {exc}", ephemeral=True)

    @context_add.autocomplete('channel')
    async def context_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @context_add.autocomplete('thread')
    async def context_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)

    @context_group.command(name="clear", description="Clear one public, session, or DM context scope.")
    @app_commands.describe(scope="Which context bucket to clear.")
    @app_commands.choices(scope=CONTEXT_SCOPE_CHOICES)
    async def context_clear(
        interaction: discord.Interaction,
        scope: app_commands.Choice[str],
    ):
        await send_command_ack(interaction, "Clearing context...")
        try:
            response_text = await _update_context_scope(
                interaction,
                scope_value=scope.value,
                action_value="clear",
                note=None,
                tags=None,
                start=None,
                end=None,
                message_ids=None,
                last_n=None,
                channel=None,
                thread=None,
            )
            await send_interaction_message(interaction, response_text, ephemeral=True)
        except PermissionError as exc:
            await send_interaction_message(interaction, str(exc), ephemeral=True)
        except Exception as exc:
            logger.exception("Error clearing context: %s", exc)
            await send_interaction_message(interaction, f"Could not clear context: {exc}", ephemeral=True)

    @context_group.command(name="list", description="Show the current runtime state of public, session, and DM context.")
    async def context_list(interaction: discord.Interaction):
        category = interaction.channel.category
        packet = await compile_context_packet_from_category(
            category,
            include_dm_context=_member_is_dm(interaction),
        )
        blocks = [
            f"**Context status for {category.mention if category else interaction.guild.name}**",
            "",
            _compiled_context_status(category, "public", packet.public_text, packet.public_source, len(packet.public_assets)),
            "",
            _compiled_context_status(category, "session", packet.session_text, packet.session_source, len(packet.session_assets)),
        ]
        if _member_is_dm(interaction):
            blocks.extend(
                [
                    "",
                    _compiled_context_status(category, "dm", packet.dm_text, packet.dm_source, len(packet.dm_assets)),
                ]
            )
        else:
            blocks.extend(
                [
                    "",
                    "**DM Private**\n"
                    f"• Runtime state: hidden\n"
                    f"• Discord surface: {_context_surface_label(category, 'dm')}\n"
                    f"• Edit access requires the `{DM_ROLE_NAME}` role",
                ]
            )
        blocks.extend(
            [
                "",
                "This reflects the effective compiled context used by the runtime. Discord-managed context entries are the source of truth. `Session Only` stays active until you replace it or clear it.",
            ]
        )
        await send_interaction_message(interaction, "\n".join(blocks), ephemeral=True)

    @context_group.command(name="summary", description="Legacy alias for `/context add`.")
    @app_commands.describe(
        scope="Which context bucket to update.",
        action="Whether to replace or append to that bucket.",
        note="Optional manual text to store as context.",
        tags="Optional comma-separated tags such as roster, npc, location, scene, style.",
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to include.",
        last_n="Use the last 'n' messages from the source target.",
        channel="Optional source channel. Defaults to this channel.",
        thread="Optional source thread. Overrides the source channel when set.",
    )
    @app_commands.choices(
        scope=CONTEXT_SCOPE_CHOICES,
        action=CONTEXT_WRITE_ACTION_CHOICES,
    )
    async def context_summary(
        interaction: discord.Interaction,
        scope: app_commands.Choice[str],
        action: app_commands.Choice[str],
        note: str = None,
        tags: str = None,
        start: str = None,
        end: str = None,
        message_ids: str = None,
        last_n: int = None,
        channel: str = None,
        thread: str = None,
    ):
        await send_command_ack(interaction, "Updating context...")
        try:
            response_text = await _update_context_scope(
                interaction,
                scope_value=scope.value,
                action_value=action.value,
                note=note,
                tags=tags,
                start=start,
                end=end,
                message_ids=message_ids,
                last_n=last_n,
                channel=channel,
                thread=thread,
            )
            await send_interaction_message(interaction, response_text, ephemeral=True)
        except PermissionError as exc:
            await send_interaction_message(interaction, str(exc), ephemeral=True)
        except Exception as exc:
            logger.exception("Error updating legacy summary context: %s", exc)
            await send_interaction_message(interaction, f"Could not update context: {exc}", ephemeral=True)

    @context_summary.autocomplete('channel')
    async def context_summary_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @context_summary.autocomplete('thread')
    async def context_summary_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)

    @generate_group.command(name="image", description="Generate images from the latest summary, selected messages, or a custom prompt.")
    @app_commands.describe(
        source_mode="Where the image instructions should come from.",
        prompt="Required for custom prompt mode. Optional extra source text for message-based modes.",
        directives="Optional extra instructions layered on top of the source material.",
        quality="Image generation quality policy.",
        aspect_ratio="Optional override. Leave on Auto to let the scene decide.",
        include_dm_context="Whether DM-private context can be included for this generation run.",
        message_ids="Comma-separated message IDs for message-based generation.",
        last_n="Use the last N messages from the chosen source target.",
        channel="Optional source channel for message-based generation.",
        thread="Optional source thread for message-based generation.",
    )
    @app_commands.choices(
        source_mode=IMAGE_SOURCE_MODE_CHOICES,
        quality=IMAGE_QUALITY_CHOICES,
        aspect_ratio=IMAGE_ASPECT_RATIO_CHOICES,
    )
    async def generate_image(
        interaction: discord.Interaction,
        source_mode: app_commands.Choice[str],
        prompt: str = None,
        directives: str = None,
        quality: app_commands.Choice[str] | None = None,
        aspect_ratio: app_commands.Choice[str] | None = None,
        include_dm_context: bool | None = None,
        message_ids: str = None,
        last_n: int | None = None,
        channel: str = None,
        thread: str = None,
    ):
        await send_command_ack(interaction, "Generating images...")

        category = getattr(interaction.channel, "category", None)
        if category is None and isinstance(interaction.channel, discord.Thread):
            category = getattr(interaction.channel.parent, "category", None)
        if category is None:
            await send_interaction_message(interaction, "This command must be used inside a campaign category.", ephemeral=True)
            return

        settings = await asyncio.to_thread(get_campaign_image_settings, category.id)
        selected_quality = quality.value if quality else settings.session_image_quality
        allow_dm_context = include_dm_context if include_dm_context is not None else settings.session_image_include_dm_context
        aspect_ratio_override = _normalize_image_aspect_ratio(aspect_ratio.value if aspect_ratio else None)
        context_packet = await compile_context_packet_from_category(category, include_dm_context=allow_dm_context)

        target_channel = interaction.channel
        source_value = source_mode.value
        if source_value == "latest_summary":
            objective_summary, narrative_summary = await _collect_latest_session_summaries(category)
            if not objective_summary and not narrative_summary:
                await send_interaction_message(interaction, "Could not find a recent objective or narrative summary in #session-summary.", ephemeral=True)
                return

            candidates = await scene_pipeline.extract_scene_candidates(
                objective_summary=objective_summary or "",
                narrative_summary=narrative_summary or "",
                context_packet=context_packet,
                max_scenes_cap=settings.session_image_max_scenes,
            )
            selected_scenes, rationale = await scene_pipeline.select_final_scenes(
                candidates,
                context_packet=context_packet,
                max_scenes_cap=settings.session_image_max_scenes,
            )
            if rationale:
                await send_response_in_chunks(target_channel, f"**Image scene selection**\n{rationale}")
            for index, scene in enumerate(selected_scenes, start=1):
                request = scene_pipeline.prepare_scene_image_request(
                    scene,
                    context_packet=context_packet,
                    quality_mode=selected_quality,
                    directives=directives,
                    aspect_ratio_override=aspect_ratio_override,
                )
                images = gemini_client.generate_image(
                    request.prompt,
                    model_name=request.model_name,
                    aspect_ratio=request.aspect_ratio,
                    reference_images=request.reference_assets,
                )
                if not images:
                    await target_channel.send(f"Skipping `{scene.title}` because Gemini returned no image.")
                    continue
                await _send_generated_image_message(
                    target_channel,
                    title=scene.title,
                    subtitle_lines=[
                        f"• Focus: {scene.subject_focus or 'mixed'}",
                        f"• Aspect ratio: `{request.aspect_ratio}`",
                        f"• Model: `{request.model_name}`",
                    ],
                    image_bytes=images[0]["image_bytes"],
                    mime_type=images[0]["mime_type"],
                    index=index,
                )
            await send_interaction_message(interaction, "Generated image set in this channel.", ephemeral=True)
            return

        selected_messages: list[discord.Message] = []
        raw_assets: list[dict] = []
        source_parts: list[str] = []
        if source_value in {"message_ids", "last_n"}:
            source_target = await _resolve_context_source_target(interaction, channel=channel, thread=thread)
            if source_target is None:
                await send_interaction_message(interaction, "Could not resolve the source channel or thread.", ephemeral=True)
                return
            selected_messages, options_or_error = await select_messages(
                source_target,
                None,
                None,
                message_ids if source_value == "message_ids" else None,
                last_n if source_value == "last_n" else None,
            )
            if isinstance(options_or_error, str):
                await send_interaction_message(interaction, options_or_error, ephemeral=True)
                return
            if not selected_messages:
                await send_interaction_message(interaction, "No source messages were selected.", ephemeral=True)
                return
            source_material = await _build_context_material_from_messages(selected_messages)
            source_parts.append("\n\n".join(source_material))
            raw_assets = _extract_context_assets(selected_messages)

        if source_value == "custom_prompt":
            if not prompt:
                await send_interaction_message(interaction, "Custom prompt mode requires `prompt`.", ephemeral=True)
                return
            source_parts.append(prompt.strip())
        elif prompt:
            source_parts.append(prompt.strip())

        if not source_parts:
            await send_interaction_message(interaction, "Provide source messages or a prompt for image generation.", ephemeral=True)
            return

        brief = await scene_pipeline.build_direct_image_brief(
            source_material="\n\n".join(part for part in source_parts if part).strip(),
            directives=directives,
            context_packet=context_packet,
        )
        selected_asset_objects = [_context_asset_from_raw(asset) for asset in raw_assets if asset.get("is_image")]
        request = scene_pipeline.prepare_direct_image_request(
            brief,
            context_packet=context_packet,
            quality_mode=selected_quality,
            directives=directives,
            aspect_ratio_override=aspect_ratio_override,
        )
        combined_reference_assets: list = []
        seen_refs: set[tuple[str, int | None]] = set()
        for asset in [*request.reference_assets, *selected_asset_objects]:
            key = (asset.url, asset.source_message_id)
            if key in seen_refs:
                continue
            seen_refs.add(key)
            combined_reference_assets.append(asset)

        images = gemini_client.generate_image(
            request.prompt,
            model_name=request.model_name,
            aspect_ratio=request.aspect_ratio,
            reference_images=combined_reference_assets,
        )
        if not images:
            await send_interaction_message(interaction, "Gemini returned no image for this request.", ephemeral=True)
            return

        await _send_generated_image_message(
            target_channel,
            title=brief.title,
            subtitle_lines=[
                f"• Focus: {brief.subject_focus or 'mixed'}",
                f"• Aspect ratio: `{request.aspect_ratio}`",
                f"• Model: `{request.model_name}`",
            ],
            image_bytes=images[0]["image_bytes"],
            mime_type=images[0]["mime_type"],
            index=1,
        )
        await send_interaction_message(interaction, "Generated image in this channel.", ephemeral=True)

    @generate_image.autocomplete("channel")
    async def generate_image_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @generate_image.autocomplete("thread")
    async def generate_image_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)


    @memory_group.command(name="list", description="Show one target, or list the whole category when no target is given.")
    @app_commands.describe(
        channel="Optional channel to inspect. Leave blank to list the whole category.",
        thread="Optional thread to inspect."
    )
    async def listmemory(interaction: discord.Interaction, channel: str = None, thread: str = None):
        try:
            category_id = get_category_id(interaction)
            if not channel and not thread:
                snapshot = await asyncio.to_thread(build_thread_data_snapshot)
                category_data = snapshot.get(str(category_id))
                if not category_data:
                    await send_interaction_message(interaction, "No memory data found for this category.")
                    return

                lines = [
                    f"**Memory map for {interaction.channel.category.mention}**",
                    f"• Default memory: `{category_data.get('default_memory') or 'None'}`",
                    "",
                ]
                grouped_channels: dict[str, list[tuple[str, dict]]] = {}
                for channel_discord_id, channel_data in category_data["channels"].items():
                    memory_name = channel_data.get("memory_name") or "None"
                    grouped_channels.setdefault(memory_name, []).append((channel_discord_id, channel_data))

                for memory_name in sorted(grouped_channels, key=str.lower):
                    lines.append(f"**{memory_name}**")
                    channels = sorted(
                        grouped_channels[memory_name],
                        key=lambda item: item[1].get("name", "").lower(),
                    )
                    for channel_discord_id, channel_data in channels:
                        channel_ref = interaction.guild.get_channel(int(channel_discord_id))
                        channel_label = channel_ref.mention if channel_ref else f"<#{channel_discord_id}>"
                        always_on_label = "✅ ON" if channel_data.get("always_on") else "❌ OFF"
                        lines.append(f"• {channel_label} ({always_on_label})")

                        threads = sorted(
                            channel_data.get("threads", {}).items(),
                            key=lambda item: item[1].get("name", "").lower(),
                        )
                        for thread_discord_id, thread_data in threads:
                            thread_ref = interaction.guild.get_channel(int(thread_discord_id))
                            thread_label = thread_ref.mention if thread_ref else f"<#{thread_discord_id}>"
                            thread_memory_name = thread_data.get("memory_name") or memory_name
                            thread_always_on = "✅ ON" if thread_data.get("always_on") else "❌ OFF"
                            relation = "thread override" if thread_memory_name != memory_name else "thread inherits"
                            lines.append(
                                f"  • {relation}: {thread_label} -> `{thread_memory_name}` ({thread_always_on})"
                            )
                    lines.append("")

                assigned_memory_names = {
                    memory_name
                    for memory_name in grouped_channels
                    if memory_name and memory_name != "None"
                }
                for channel_data in category_data["channels"].values():
                    for thread_data in channel_data.get("threads", {}).values():
                        thread_memory_name = thread_data.get("memory_name")
                        if thread_memory_name:
                            assigned_memory_names.add(thread_memory_name)

                unassigned_memories = sorted(
                    memory_name
                    for memory_name in category_data.get("memory_threads", {}).keys()
                    if memory_name not in assigned_memory_names
                )
                if unassigned_memories:
                    lines.append("**Unassigned memories**")
                    for memory_name in unassigned_memories:
                        default_marker = " (default)" if memory_name == category_data.get("default_memory") else ""
                        lines.append(f"• `{memory_name}`{default_marker}")
                    lines.append("")

                response = "\n".join(lines)
                await send_interaction_message(interaction, response[:2000])
                for chunk_start in range(2000, len(response), 2000):
                    await interaction.followup.send(response[chunk_start:chunk_start + 2000])
                return

            channel_id = int(channel) if channel else interaction.channel.id
            thread_id = int(thread) if thread else None

            target_channel = interaction.guild.get_channel(channel_id)
            target_thread = await interaction.guild.fetch_channel(thread_id) if thread_id else None
            
            if not target_channel:
                await send_interaction_message(interaction, "Channel not found.")
                return

            response_data = await asyncio.to_thread(fetch_memory_details, int(category_id), int(channel_id), int(thread_id) if thread_id else None)
            if not response_data:
                await send_interaction_message(interaction, "No memory data found for that target.")
                return
            
            # Format the response
            response = (
                f"**Memory details for {target_thread.mention if target_thread else target_channel.mention}**\n"
                f"• Memory ID: `{response_data['memory_id']}`\n"
                f"• Memory Name: `{response_data['memory_name']}`\n"
                f"• Always On: `{'✅ ON' if response_data['always_on'] else '❌ OFF'}`"
            )

            if not thread_id:
                snapshot = await asyncio.to_thread(build_thread_data_snapshot)
                category_data = snapshot.get(str(category_id), {})
                channel_data = category_data.get("channels", {}).get(str(channel_id), {})
                threads = sorted(
                    channel_data.get("threads", {}).items(),
                    key=lambda item: item[1].get("name", "").lower(),
                )
                if threads:
                    thread_lines = ["", "**Threads in this channel**"]
                    for thread_discord_id, thread_data in threads:
                        thread_ref = interaction.guild.get_channel(int(thread_discord_id))
                        thread_label = thread_ref.mention if thread_ref else f"<#{thread_discord_id}>"
                        thread_memory_name = thread_data.get("memory_name") or response_data["memory_name"] or "None"
                        relation = "override" if thread_memory_name != response_data["memory_name"] else "inherits"
                        thread_lines.append(f"• {thread_label} -> `{thread_memory_name}` ({relation})")
                    response += "\n" + "\n".join(thread_lines)
            
            await send_interaction_message(interaction, response[:2000])
            for chunk_start in range(2000, len(response), 2000):
                await interaction.followup.send(response[chunk_start:chunk_start + 2000])
            
        except ValueError:
            await send_interaction_message(interaction, "Error: Invalid channel or thread ID format.")
        except discord.NotFound:
            await send_interaction_message(interaction, "Error: Channel or thread not found.")
        except Exception as e:
            logging.error(f"Error in listmemory command: {str(e)}")
            await send_interaction_message(interaction, f"An error occurred: {str(e)}")

    @listmemory.autocomplete('channel')
    async def listmemory_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @listmemory.autocomplete('thread')
    async def listmemory_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)

    
    @memory_group.command(name="reset", description="Clear a target memory and delete AIDM replies from there.")
    @app_commands.describe(
        channel="Target channel. Defaults to the current channel.",
        thread="Optional target thread.",
        starting_with_message_id="Delete AIDM replies starting with this message ID (inclusive)."
    )
    async def reset_memory_command(interaction: discord.Interaction, channel: str = None, thread: str = None, starting_with_message_id: str = None):
        await send_command_ack(interaction, "Resetting memory...")

        try:
            channel_id = int(channel) if channel else interaction.channel.id
            thread_id = int(thread) if thread else None
            category_id = get_category_id(interaction)

            target = interaction.guild.get_channel(channel_id)
            if thread_id:
                target = await interaction.guild.fetch_channel(thread_id)

            assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id=thread_id)
            if not assigned_memory:
                await interaction.followup.send("No memory assigned to this channel/thread.")
                return

            if starting_with_message_id:
                try:
                    await target.fetch_message(int(starting_with_message_id))
                except discord.NotFound:
                    logging.warning(f"Message ID {starting_with_message_id} not found in this channel.")
                    await interaction.followup.send("Invalid message ID — message not found.")
                    return

            await reset_memory_history(assigned_memory)

            # === DELETE DISCORD MESSAGES ===
            deleted_discord_msgs = 0

            async for message in target.history(limit=500):
                if message.author.id == interaction.client.user.id:
                    if not starting_with_message_id or int(message.id) >= int(starting_with_message_id):
                        try:
                            await message.delete()
                            deleted_discord_msgs += 1
                            await asyncio.sleep(0.35)  # avoid rate limiting Discord (429s)
                        except (discord.Forbidden, discord.HTTPException) as e:
                            logging.warning(f"Could not delete message {message.id}: {e}")

            await interaction.followup.send(
                f"🧹 **Reset complete!**\n"
                "• Stored memory rows deleted: `0` (chat transcript storage is disabled)\n"
                f"• Discord messages deleted: `{deleted_discord_msgs}`"
            )

        except Exception as e:
            logging.error(f"Error during memory reset: {e}")
            try:
                await interaction.followup.send(f"❌ Unexpected error: {e}")
            except discord.NotFound:
                logging.error("Couldn't send followup message – maybe the interaction expired.")

    @reset_memory_command.autocomplete('channel')
    async def reset_memory_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @reset_memory_command.autocomplete('thread')
    async def reset_memory_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)

    @tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        original = error.original if isinstance(error, app_commands.CommandInvokeError) else error
        logger.exception("Application command error: %s", original)

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
            message = f"Could not complete `{command_name}` because of an internal error."

        try:
            await send_interaction_message(interaction, message, ephemeral=True)
        except Exception:
            logger.exception("Failed to send app command error message.")

    tree.add_command(ask_group)
    tree.add_command(channel_group)
    tree.add_command(context_group)
    tree.add_command(memory_group)
    tree.add_command(settings_group)
    tree.add_command(generate_group)
