import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import discord

from config import DISCORD_BOT_TOKEN
from voice.context_support import build_context_block


logger = logging.getLogger(__name__)
ENTRY_BEGIN = "[AIDM_CONTEXT_ENTRY]"
ENTRY_END = "[/AIDM_CONTEXT_ENTRY]"
MAX_CONTEXT_MESSAGE_LENGTH = 1800
CONTEXT_HISTORY_LIMIT = 500


@dataclass
class ContextAsset:
    filename: str
    url: str
    proxy_url: str | None
    content_type: str | None
    source_message_id: int | None
    source_channel_id: int | None
    is_image: bool
    image_bytes: bytes | None = None


@dataclass
class ManagedContextEntry:
    entry_id: str
    scope: str
    action: str
    kind: str
    text: str
    source_label: str
    source_mode: str
    actor_name: str
    actor_id: int | None
    channel_id: int
    message_ids: list[int]
    source_channel_id: int | None
    source_message_ids: list[int]
    tags: list[str]
    assets: list[ContextAsset]
    created_at: datetime


@dataclass
class CompiledContextPacket:
    public_entries: list[ManagedContextEntry] = field(default_factory=list)
    session_entries: list[ManagedContextEntry] = field(default_factory=list)
    dm_entries: list[ManagedContextEntry] = field(default_factory=list)
    public_text: str | None = None
    session_text: str | None = None
    dm_text: str | None = None
    text_block: str | None = None
    public_source: str = "empty"
    session_source: str = "empty"
    dm_source: str = "empty"
    public_assets: list[ContextAsset] = field(default_factory=list)
    session_assets: list[ContextAsset] = field(default_factory=list)
    dm_assets: list[ContextAsset] = field(default_factory=list)


def build_context_entry_messages(
    *,
    scope: str,
    action: str,
    text: str | None,
    source_label: str,
    source_mode: str,
    actor_name: str,
    actor_id: int | None,
    source_channel_id: int | None = None,
    source_message_ids: list[int] | None = None,
    tags: list[str] | None = None,
    assets: list[dict] | None = None,
) -> list[str]:
    entry_id = uuid.uuid4().hex[:12]
    cleaned_text = (text or "").strip()
    normalized_tags = list(dict.fromkeys(tag.strip().lower() for tag in (tags or []) if tag and tag.strip()))
    normalized_assets = list(assets or [])
    image_count = sum(1 for asset in normalized_assets if asset.get("is_image"))
    if action == "clear":
        kind = "control"
    elif normalized_assets and cleaned_text:
        kind = "mixed"
    elif normalized_assets:
        kind = "image"
    else:
        kind = "text"

    base_metadata = {
        "entry_id": entry_id,
        "scope": scope,
        "action": action,
        "kind": kind,
        "source_label": source_label,
        "source_mode": source_mode,
        "actor_name": actor_name,
        "actor_id": actor_id,
        "source_channel_id": source_channel_id,
        "source_message_ids": source_message_ids or [],
        "tags": normalized_tags,
        "asset_count": len(normalized_assets),
        "image_count": image_count,
    }

    title = {
        "public": "Public Evergreen",
        "session": "Session Only",
        "dm": "DM Private",
    }.get(scope, scope.title())
    header_lines = [
        f"**{title}**",
        f"• Action: `{action}`",
        f"• By: {actor_name}",
        f"• Source: {source_label}",
    ]
    if normalized_tags:
        header_lines.append(f"• Tags: `{', '.join(normalized_tags)}`")
    if normalized_assets:
        asset_label = f"{len(normalized_assets)} ref" if len(normalized_assets) == 1 else f"{len(normalized_assets)} refs"
        image_label = f"{image_count} image" if image_count == 1 else f"{image_count} images"
        header_lines.append(f"• Assets: `{asset_label}`, `{image_label}`")

    def build_message(part_index: int, part_count: int, part: str) -> str:
        metadata = dict(base_metadata)
        metadata["part_index"] = part_index
        metadata["part_count"] = part_count
        metadata_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))

        visible_lines = list(header_lines)
        if part_count > 1:
            visible_lines.append(f"• Part: {part_index}/{part_count}")
        visible_sections = ["\n".join(visible_lines)]
        if action == "clear":
            visible_sections.append("_This scope was cleared._")
        elif not part and normalized_assets:
            visible_sections.append("_Image references captured for this entry._")
        if part:
            visible_sections.append(part)

        visible_sections.append(f"||{ENTRY_BEGIN}{metadata_json}{ENTRY_END}||")
        return "\n\n".join(section for section in visible_sections if section)

    def compute_available_text_len(part_count: int) -> int:
        sample_message = build_message(part_count, part_count, "")
        return MAX_CONTEXT_MESSAGE_LENGTH - len(sample_message) - 2

    part_count = 1
    while True:
        available_text_len = compute_available_text_len(part_count)
        if available_text_len < 0:
            raise ValueError("Context entry metadata is too large to fit in a Discord message.")

        parts = [
            cleaned_text[i:i + max(1, available_text_len)]
            for i in range(0, len(cleaned_text), max(1, available_text_len))
        ] or [""]
        next_part_count = len(parts)
        if next_part_count == part_count:
            break
        part_count = next_part_count

    messages: list[str] = []

    for index, part in enumerate(parts, start=1):
        message = build_message(index, part_count, part)
        if len(message) > MAX_CONTEXT_MESSAGE_LENGTH:
            raise ValueError("Context entry is too large for the current message chunking strategy.")
        messages.append(message)

    return messages


def parse_context_entry_fragment(message: discord.Message) -> dict | None:
    content = message.content or ""
    begin = content.find(ENTRY_BEGIN)
    end = content.find(ENTRY_END)
    if begin == -1 or end == -1 or end < begin:
        return None

    metadata_block = content[begin + len(ENTRY_BEGIN):end].strip()
    visible_content = (content[:begin] + content[end + len(ENTRY_END):]).replace("||", "").strip()
    try:
        metadata = json.loads(metadata_block)
    except json.JSONDecodeError:
        return None

    sections = [section.strip() for section in visible_content.split("\n\n") if section.strip()]
    body = "\n\n".join(sections[1:]).strip() if len(sections) > 1 else ""

    return {
        "metadata": metadata,
        "text": body,
        "message_id": message.id,
        "channel_id": message.channel.id,
        "created_at": message.created_at,
    }


def _reconstruct_entries(fragments: list[dict]) -> list[ManagedContextEntry]:
    grouped: dict[str, dict] = {}

    for fragment in fragments:
        metadata = fragment["metadata"]
        entry_id = str(metadata.get("entry_id") or "")
        if not entry_id:
            continue
        bucket = grouped.setdefault(
            entry_id,
            {
                "metadata": metadata,
                "parts": {},
                "message_ids": [],
                "channel_id": fragment["channel_id"],
                "created_at": fragment["created_at"],
            },
        )
        bucket["parts"][int(metadata.get("part_index", 1))] = fragment["text"]
        bucket["message_ids"].append(fragment["message_id"])
        if fragment["created_at"] > bucket["created_at"]:
            bucket["created_at"] = fragment["created_at"]

    entries: list[ManagedContextEntry] = []
    for entry_id, bucket in grouped.items():
        metadata = bucket["metadata"]
        part_count = int(metadata.get("part_count", 1))
        ordered_parts = [bucket["parts"].get(index, "") for index in range(1, part_count + 1)]
        entries.append(
            ManagedContextEntry(
                entry_id=entry_id,
                scope=str(metadata.get("scope", "")),
                action=str(metadata.get("action", "")),
                kind=str(metadata.get("kind", "text")),
                text="\n".join(part for part in ordered_parts if part).strip(),
                source_label=str(metadata.get("source_label", "manual note")),
                source_mode=str(metadata.get("source_mode", "manual_note")),
                actor_name=str(metadata.get("actor_name", "Unknown")),
                actor_id=metadata.get("actor_id"),
                channel_id=int(bucket["channel_id"]),
                message_ids=sorted(bucket["message_ids"]),
                source_channel_id=metadata.get("source_channel_id"),
                source_message_ids=[int(value) for value in metadata.get("source_message_ids", []) if str(value).isdigit()],
                tags=[str(tag) for tag in metadata.get("tags", []) if str(tag).strip()],
                assets=[
                    ContextAsset(
                        filename=str(asset.get("filename", "")),
                        url=str(asset.get("url", "")),
                        proxy_url=asset.get("proxy_url"),
                        content_type=asset.get("content_type"),
                        source_message_id=asset.get("source_message_id"),
                        source_channel_id=asset.get("source_channel_id"),
                        is_image=bool(asset.get("is_image")),
                        image_bytes=asset.get("image_bytes"),
                    )
                    for asset in metadata.get("assets", [])
                    if asset.get("url")
                ],
                created_at=bucket["created_at"],
            )
        )

    entries.sort(key=lambda item: item.created_at, reverse=True)
    return entries


def _attachment_is_image(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True
    filename = attachment.filename.lower()
    return filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"))


async def _hydrate_entry_assets(
    guild: discord.Guild,
    entries: list[ManagedContextEntry],
) -> list[ManagedContextEntry]:
    if not entries:
        return entries

    channel_cache: dict[int, discord.abc.GuildChannel | discord.Thread | None] = {}
    message_cache: dict[tuple[int, int], discord.Message | None] = {}

    async def resolve_channel(channel_id: int | None):
        if not channel_id:
            return None
        if channel_id in channel_cache:
            return channel_cache[channel_id]
        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await guild.fetch_channel(channel_id)
            except Exception as exc:
                logger.warning("Could not fetch context source channel %s: %s", channel_id, exc)
                channel = None
        channel_cache[channel_id] = channel
        return channel

    for entry in entries:
        if entry.assets or not entry.source_message_ids or not entry.source_channel_id:
            continue
        source_channel = await resolve_channel(entry.source_channel_id)
        if source_channel is None:
            continue

        resolved_assets: list[ContextAsset] = []
        seen: set[tuple[str, int | None]] = set()
        for message_id in entry.source_message_ids:
            cache_key = (entry.source_channel_id, message_id)
            if cache_key in message_cache:
                message = message_cache[cache_key]
            else:
                try:
                    message = await source_channel.fetch_message(message_id)
                except Exception as exc:
                    logger.warning(
                        "Could not fetch context source message %s in channel %s: %s",
                        message_id,
                        entry.source_channel_id,
                        exc,
                    )
                    message = None
                message_cache[cache_key] = message
            if message is None:
                continue
            for attachment in message.attachments:
                key = (attachment.url, message.id)
                if key in seen:
                    continue
                seen.add(key)
                image_bytes = None
                if _attachment_is_image(attachment):
                    try:
                        image_bytes = await attachment.read(use_cached=True)
                    except Exception as exc:
                        logger.warning(
                            "Could not prefetch context image %s from message %s: %s",
                            attachment.filename,
                            message.id,
                            exc,
                        )
                resolved_assets.append(
                    ContextAsset(
                        filename=attachment.filename,
                        url=attachment.url,
                        proxy_url=attachment.proxy_url,
                        content_type=attachment.content_type,
                        source_message_id=message.id,
                        source_channel_id=message.channel.id,
                        is_image=_attachment_is_image(attachment),
                        image_bytes=image_bytes,
                    )
                )
        entry.assets = resolved_assets

    return entries


def _resolve_scope(entries: list[ManagedContextEntry], scope: str) -> list[ManagedContextEntry]:
    active: list[ManagedContextEntry] = []
    for entry in entries:
        if entry.scope != scope:
            continue
        if entry.action == "clear":
            break
        active.append(entry)
        if entry.action == "replace":
            break
    active.reverse()
    return active


def _entries_to_text(entries: list[ManagedContextEntry]) -> str | None:
    text = "\n\n".join(entry.text for entry in entries if entry.text).strip()
    return text or None


def _entries_to_assets(entries: list[ManagedContextEntry]) -> list[ContextAsset]:
    assets: list[ContextAsset] = []
    seen: set[tuple[str, int | None]] = set()
    for entry in entries:
        for asset in entry.assets:
            key = (asset.url, asset.source_message_id)
            if key in seen:
                continue
            seen.add(key)
            assets.append(asset)
    return assets


async def _load_channel_entries(channel: discord.TextChannel | None) -> list[ManagedContextEntry]:
    if channel is None:
        return []

    fragments: list[dict] = []
    async for message in channel.history(limit=CONTEXT_HISTORY_LIMIT):
        fragment = parse_context_entry_fragment(message)
        if fragment:
            fragments.append(fragment)
    return _reconstruct_entries(fragments)


async def compile_context_packet_from_category(
    category: discord.CategoryChannel | None,
    *,
    include_dm_context: bool = False,
) -> CompiledContextPacket:
    packet = CompiledContextPacket()
    if category is None:
        return packet

    context_channel = discord.utils.get(category.text_channels, name="context")
    dm_planning_channel = discord.utils.get(category.text_channels, name="dm-planning")

    context_entries = await _load_channel_entries(context_channel)
    dm_entries = await _load_channel_entries(dm_planning_channel) if include_dm_context else []

    packet.public_entries = await _hydrate_entry_assets(category.guild, _resolve_scope(context_entries, "public"))
    packet.session_entries = await _hydrate_entry_assets(category.guild, _resolve_scope(context_entries, "session"))
    packet.dm_entries = await _hydrate_entry_assets(category.guild, _resolve_scope(dm_entries, "dm"))

    packet.public_text = _entries_to_text(packet.public_entries)
    packet.session_text = _entries_to_text(packet.session_entries)
    packet.dm_text = _entries_to_text(packet.dm_entries) if include_dm_context else None
    packet.public_assets = _entries_to_assets(packet.public_entries)
    packet.session_assets = _entries_to_assets(packet.session_entries)
    packet.dm_assets = _entries_to_assets(packet.dm_entries) if include_dm_context else []

    packet.public_source = "discord" if packet.public_entries else "empty"
    packet.session_source = "discord" if packet.session_entries else "empty"
    packet.dm_source = "discord" if packet.dm_entries else "empty"

    packet.text_block = build_context_block(
        public_text=packet.public_text,
        session_text=packet.session_text,
        dm_text=packet.dm_text,
    )
    return packet


async def compile_context_packet_from_category_id(
    discord_category_id: int,
    *,
    include_dm_context: bool = False,
) -> CompiledContextPacket:
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN is required to load Discord-managed context.")

    intents = discord.Intents.none()
    intents.guilds = True
    temp_client = discord.Client(intents=intents)
    holder: dict[str, object] = {}

    @temp_client.event
    async def on_ready():
        try:
            category = temp_client.get_channel(discord_category_id)
            if category is None:
                category = await temp_client.fetch_channel(discord_category_id)
            if not isinstance(category, discord.CategoryChannel):
                raise ValueError(f"Channel {discord_category_id} is not a Discord category.")
            holder["packet"] = await compile_context_packet_from_category(
                category,
                include_dm_context=include_dm_context,
            )
        except Exception as exc:
            holder["error"] = exc
        finally:
            await temp_client.close()

    try:
        await temp_client.start(DISCORD_BOT_TOKEN)
    finally:
        if not temp_client.is_closed():
            await temp_client.close()
    if "error" in holder:
        raise holder["error"]  # type: ignore[misc]
    packet = holder.get("packet")
    if not isinstance(packet, CompiledContextPacket):
        raise RuntimeError("Could not compile Discord context packet.")
    return packet
