from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from tempfile import NamedTemporaryFile

import discord

from content_retrieval import extract_text_from_local_file, select_messages
from data_store.db_repository import ensure_channel_for_category

from .rendering import build_player_character_card
from .schema import PlayerWorkspaceBundle, WorkspaceSlots


logger = logging.getLogger(__name__)

PLAYER_SOURCE_ATTACHMENT_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".txt",
    ".md",
    ".docx",
}

WORKSPACE_SLOT_ORDER: tuple[tuple[str, str], ...] = (
    ("Character Card", "character_card"),
    ("Profile Card", "profile_card"),
    ("Rules Card", "rules_card"),
    ("Items Card", "items_card"),
)

LEGACY_PATTERNS = (
    "**Character Card**",
    "**Profile Card**",
    "**Sheet Card**",
    "**Skills Card**",
    "**Rules Card**",
    "**Items Card**",
    "## Character Workspace",
    "## Core Status & Resources",
    "## Ability Scores & Saving Throws",
    "## Skills & Senses",
    "## 👤 CHARACTER PROFILE",
    "## ⚔️ CLASS FEATURES & MAGIC",
    "## 🎒 INVENTORY & ATTUNEMENT",
)


def slugify_player_key(value: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", (value or "draft").lower()).strip("-")
    return normalized or "draft"


def split_discord_body(body: str, max_len: int = 1800) -> list[str]:
    text = body.strip()
    if not text:
        return [""]
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    in_code_fence = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        prospective = current_len + len(line) + 1
        if current and prospective > max_len:
            if in_code_fence:
                current.append("```")
            chunks.append("\n".join(current).strip())
            current = ["```"] if in_code_fence else []
            current_len = 4 if in_code_fence else 0

        current.append(line)
        current_len += len(line) + 1
        if line.strip().startswith("```"):
            in_code_fence = not in_code_fence

    if current:
        if in_code_fence:
            current.append("```")
        chunks.append("\n".join(current).strip())

    return [chunk for chunk in chunks if chunk]


def _trim_embed_body(body: str, *, limit: int = 4000) -> str:
    cleaned = (body or "").strip() or "Needs review."
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 18].rstrip() + "\n\n[Truncated]"

def _summary_embed(body: str) -> discord.Embed:
    return discord.Embed(
        title="Character Summary",
        description=_trim_embed_body(body),
        color=discord.Color.orange(),
    )


def _detail_embed(title: str, body: str) -> discord.Embed:
    cleaned = (body or "Needs review.").strip()
    return discord.Embed(title=title, description=_trim_embed_body(cleaned), color=discord.Color.dark_grey())


def build_slot_payload(title: str, body: str) -> tuple[str, discord.Embed | None]:
    if title == "Character Card":
        return f"**{title}**", _summary_embed(body)
    return f"**{title}**", _detail_embed(title, body)


class CardEditModal(discord.ui.Modal):
    def __init__(self, *, title: str, initial_body: str) -> None:
        super().__init__(title=f"Edit {title}")
        self.card_title = title
        self.content_input = discord.ui.TextInput(
            label="Card Content",
            style=discord.TextStyle.paragraph,
            default=(initial_body or "Needs review.")[:4000],
            max_length=4000,
            required=True,
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        embed = _detail_embed(self.card_title, str(self.content_input.value))
        await interaction.response.edit_message(content=f"**{self.card_title}**", embed=embed, view=CardDetailView(self.card_title))


class CardDetailView(discord.ui.View):
    def __init__(self, card_title: str) -> None:
        super().__init__(timeout=None)
        self.card_title = card_title

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.secondary, custom_id="aidm:player-card-edit")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        initial_body = interaction.message.embeds[0].description if interaction.message.embeds else ""
        await interaction.response.send_modal(CardEditModal(title=self.card_title, initial_body=initial_body))


def build_summary_view(detail_links: dict[str, str] | None) -> discord.ui.View | None:
    if not detail_links:
        return None
    view = discord.ui.View(timeout=None)
    ordered = [
        ("Profile", detail_links.get("profile")),
        ("Rules", detail_links.get("rules")),
        ("Items", detail_links.get("items")),
    ]
    for label, url in ordered:
        if not url:
            continue
        view.add_item(discord.ui.Button(label=label, url=url, style=discord.ButtonStyle.link))
    return view if view.children else None


def slot_payloads(bundle: PlayerWorkspaceBundle) -> tuple[tuple[str, str, discord.Embed | None], ...]:
    return tuple(
        (title, *build_slot_payload(title, getattr(bundle.cards, attr_name) or "Needs review."))
        for title, attr_name in WORKSPACE_SLOT_ORDER
    )


async def ensure_character_sheets_channel(
    interaction: discord.Interaction,
    category: discord.CategoryChannel,
) -> discord.TextChannel:
    channel = discord.utils.get(category.text_channels, name="character-sheets")
    if channel is None:
        channel = await interaction.guild.create_text_channel(name="character-sheets", category=category)

    await asyncio.to_thread(
        ensure_channel_for_category,
        category.id,
        channel.id,
        channel.name,
        False,
        False,
    )
    return channel


async def iter_archived_threads(channel: discord.TextChannel) -> list[discord.Thread]:
    archived: list[discord.Thread] = []
    async for thread in channel.archived_threads(limit=100):
        archived.append(thread)
    try:
        async for thread in channel.archived_threads(limit=100, private=True):
            archived.append(thread)
    except TypeError:
        pass
    except discord.HTTPException:
        logger.warning("Could not fetch private archived threads for channel %s", channel.id)
    return archived


async def find_or_create_player_thread(
    channel: discord.TextChannel,
    thread_name: str,
) -> tuple[discord.Thread, bool]:
    for thread in channel.threads:
        if thread.name == thread_name:
            return thread, False

    for thread in await iter_archived_threads(channel):
        if thread.name == thread_name:
            try:
                await thread.edit(archived=False, locked=False)
            except discord.HTTPException:
                try:
                    await thread.edit(archived=False)
                except discord.HTTPException:
                    logger.warning("Could not unarchive thread %s; reusing archived state.", thread.id)
            return thread, False

    thread = await channel.create_thread(name=thread_name)
    return thread, True


async def stage_attachment_to_temp_path(attachment: discord.Attachment) -> str:
    suffix = Path(attachment.filename).suffix or ".bin"
    with NamedTemporaryFile(prefix="aidm-player-", suffix=suffix, delete=False) as handle:
        handle.write(await attachment.read())
        return handle.name


def _read_temp_source_text(temp_path: str) -> str | None:
    try:
        return extract_text_from_local_file(temp_path)
    except Exception as exc:
        logger.info("Could not extract local source text from %s: %s", temp_path, exc)
        return None


async def collect_player_source_material(
    interaction: discord.Interaction,
    *,
    note: str | None,
    attachment: discord.Attachment | None,
    start: str | None,
    end: str | None,
    message_ids: str | None,
    last_n: int | None,
    channel: str | None,
    thread: str | None,
    resolve_source_target: Callable[[discord.Interaction, str | None, str | None], Awaitable[tuple[discord.abc.Messageable, str]]],
    build_context_material_from_messages: Callable[[list[discord.Message]], Awaitable[tuple[str, str]]],
    describe_context_source: Callable[..., str],
) -> tuple[str, list[str], str, list[str]]:
    source_parts: list[str] = []
    file_paths: list[str] = []
    temp_paths: list[str] = []
    source_label = "notes"

    if note and note.strip():
        source_parts.append(note.strip())

    if attachment is not None:
        suffix = Path(attachment.filename).suffix.lower()
        if suffix in PLAYER_SOURCE_ATTACHMENT_EXTENSIONS:
            temp_path = await stage_attachment_to_temp_path(attachment)
            temp_paths.append(temp_path)
            file_paths.append(temp_path)
            source_label = f"slash attachment: {attachment.filename}"
            extracted = await asyncio.to_thread(_read_temp_source_text, temp_path)
            if extracted:
                source_parts.append(extracted.strip())
        else:
            raise ValueError(f"Unsupported player import attachment type: {attachment.filename}")

    if any(value is not None for value in (start, end, message_ids, last_n)):
        source_target, source_descriptor = await resolve_source_target(interaction, channel, thread)
        selected_messages, options_or_error = await select_messages(source_target, start, end, message_ids, last_n)
        if selected_messages is None:
            raise ValueError(options_or_error)
        rendered_text, attachments_text = await build_context_material_from_messages(selected_messages)
        if rendered_text:
            source_parts.append(rendered_text.strip())
        if attachments_text:
            source_parts.append(attachments_text.strip())
        source_label = describe_context_source(source_descriptor, start, end, message_ids, last_n)
        for message in selected_messages:
            for message_attachment in getattr(message, "attachments", []):
                suffix = Path(message_attachment.filename).suffix.lower()
                if suffix not in PLAYER_SOURCE_ATTACHMENT_EXTENSIONS:
                    continue
                temp_path = await stage_attachment_to_temp_path(message_attachment)
                temp_paths.append(temp_path)
                file_paths.append(temp_path)
                extracted = await asyncio.to_thread(_read_temp_source_text, temp_path)
                if extracted:
                    source_parts.append(extracted.strip())

    source_text = "\n\n".join(part for part in source_parts if part).strip()
    return source_text, file_paths, source_label, temp_paths


def _bot_id_for_thread(thread: discord.Thread) -> int | None:
    bot_user = thread.guild.me or thread.guild.get_member(thread._state.user.id)
    return bot_user.id if bot_user else None


async def _pinned_workspace_slot_groups(thread: discord.Thread) -> dict[str, list[discord.Message]]:
    bot_id = _bot_id_for_thread(thread)
    groups: dict[str, list[discord.Message]] = {title: [] for title, _ in WORKSPACE_SLOT_ORDER}
    pinned = await thread.pins()
    for message in pinned:
        if bot_id is not None and message.author.id != bot_id:
            continue
        content = message.content or ""
        for title, _ in WORKSPACE_SLOT_ORDER:
            if content.startswith(f"**{title}**"):
                groups[title].append(message)
                break
    for title in groups:
        groups[title].sort(key=lambda msg: msg.id)
    return groups


async def _cleanup_workspace_messages(thread: discord.Thread, keep_ids: set[int]) -> None:
    bot_id = _bot_id_for_thread(thread)
    async for message in thread.history(limit=None):
        if message.id in keep_ids:
            continue
        if bot_id is not None and message.author.id != bot_id:
            continue
        content = (message.content or "").strip()
        if not content:
            continue
        if any(pattern in content for pattern in LEGACY_PATTERNS):
            try:
                await message.delete()
            except discord.HTTPException:
                logger.warning("Failed to delete legacy workspace message %s in thread %s", message.id, thread.id)


async def sync_workspace_slots(thread: discord.Thread, bundle: PlayerWorkspaceBundle) -> WorkspaceSlots:
    payloads = slot_payloads(bundle)
    grouped = await _pinned_workspace_slot_groups(thread)
    has_valid_existing = (
        all(len(grouped[title]) == 1 for title, _ in WORKSPACE_SLOT_ORDER)
        and sum(len(messages) for messages in grouped.values()) == len(WORKSPACE_SLOT_ORDER)
    )

    if has_valid_existing:
        existing = {title: grouped[title][0] for title, _ in WORKSPACE_SLOT_ORDER}
        keep_ids = {message.id for message in existing.values()}
    else:
        await _cleanup_workspace_messages(thread, keep_ids=set())
        existing = {}
        keep_ids = set()

    resolved_ids: dict[str, int | None] = {}
    resolved_messages: dict[str, discord.Message] = {}

    for title, content, embed in payloads:
        message = existing.get(title)
        view = None if title == "Character Card" else CardDetailView(title)
        if message is None:
            message = await thread.send(content=content, embed=embed, view=view)
            try:
                await message.pin(reason="AIDM character workspace slot")
            except discord.HTTPException:
                logger.warning("Failed to pin workspace slot %s in thread %s", title, thread.id)
        else:
            current_description = message.embeds[0].description if message.embeds else ""
            target_description = embed.description if embed else ""
            current_title = message.embeds[0].title if message.embeds else ""
            target_title = embed.title if embed else ""
            if (
                (message.content or "") != content
                or current_description != target_description
                or current_title != target_title
                or bool(message.embeds) != bool(embed)
            ):
                message = await message.edit(content=content, embed=embed, view=view)
        keep_ids.add(message.id)
        resolved_ids[title] = message.id
        resolved_messages[title] = message

    character_message = resolved_messages.get("Character Card")
    if character_message is not None:
        detail_links = {
            "profile": resolved_messages["Profile Card"].jump_url if resolved_messages.get("Profile Card") else "",
            "rules": resolved_messages["Rules Card"].jump_url if resolved_messages.get("Rules Card") else "",
            "items": resolved_messages["Items Card"].jump_url if resolved_messages.get("Items Card") else "",
        }
        final_character_body = build_player_character_card(
            bundle.request,
            bundle.draft,
            bundle.validation,
            detail_links=detail_links,
        )
        final_content, final_embed = build_slot_payload("Character Card", final_character_body)
        final_view = build_summary_view(detail_links)
        current_description = character_message.embeds[0].description if character_message.embeds else ""
        current_title = character_message.embeds[0].title if character_message.embeds else ""
        if (
            (character_message.content or "") != final_content
            or current_description != final_embed.description
            or current_title != final_embed.title
        ):
            character_message = await character_message.edit(content=final_content, embed=final_embed, view=final_view)
            resolved_ids["Character Card"] = character_message.id
            resolved_messages["Character Card"] = character_message
        else:
            await character_message.edit(view=final_view)

    await _cleanup_workspace_messages(thread, keep_ids)

    return WorkspaceSlots(
        character_card_message_id=resolved_ids.get("Character Card"),
        profile_card_message_id=resolved_ids.get("Profile Card"),
        rules_card_message_id=resolved_ids.get("Rules Card"),
        items_card_message_id=resolved_ids.get("Items Card"),
    )
