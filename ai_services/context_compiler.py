import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import discord

from voice.context_support import build_context_block, read_context_text


ENTRY_BEGIN = "[AIDM_CONTEXT_ENTRY]"
ENTRY_END = "[/AIDM_CONTEXT_ENTRY]"
MAX_CONTEXT_MESSAGE_LENGTH = 1800
CONTEXT_HISTORY_LIMIT = 500


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


def build_context_entry_messages(
    *,
    scope: str,
    action: str,
    text: str | None,
    source_label: str,
    source_mode: str,
    actor_name: str,
    actor_id: int | None,
) -> list[str]:
    entry_id = uuid.uuid4().hex[:12]
    cleaned_text = (text or "").strip()
    kind = "control" if action == "clear" else "text"

    # Keep plenty of room for the visible header + machine-readable metadata.
    parts = [cleaned_text[i:i + 1100] for i in range(0, len(cleaned_text), 1100)] or [""]
    part_count = len(parts)
    messages: list[str] = []

    for index, part in enumerate(parts, start=1):
        metadata = {
            "entry_id": entry_id,
            "scope": scope,
            "action": action,
            "kind": kind,
            "part_index": index,
            "part_count": part_count,
            "source_label": source_label,
            "source_mode": source_mode,
            "actor_name": actor_name,
            "actor_id": actor_id,
        }
        metadata_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        title = {
            "public": "Public Evergreen",
            "session": "Session Only",
            "dm": "DM Private",
        }.get(scope, scope.title())
        header_lines = [
            f"**{title} context entry**",
            f"• Action: `{action}`",
            f"• By: {actor_name}",
            f"• Source: {source_label}",
        ]
        if part_count > 1:
            header_lines.append(f"• Part: {index}/{part_count}")

        message = (
            "\n".join(header_lines)
            + "\n\n"
            + ENTRY_BEGIN
            + "\n"
            + metadata_json
            + "\n"
            + ENTRY_END
        )
        if part:
            message += "\n\n" + part

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
    body = content[end + len(ENTRY_END):].strip()
    try:
        metadata = json.loads(metadata_block)
    except json.JSONDecodeError:
        return None

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
                created_at=bucket["created_at"],
            )
        )

    entries.sort(key=lambda item: item.created_at, reverse=True)
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
    fallback_to_local_files: bool = True,
) -> CompiledContextPacket:
    packet = CompiledContextPacket()
    if category is None:
        if fallback_to_local_files:
            packet.public_text = read_context_text("public") or None
            packet.session_text = read_context_text("session") or None
            packet.dm_text = (read_context_text("dm") or None) if include_dm_context else None
            packet.public_source = "local_fallback" if packet.public_text else "empty"
            packet.session_source = "local_fallback" if packet.session_text else "empty"
            packet.dm_source = "local_fallback" if packet.dm_text else "empty"
            packet.text_block = build_context_block(packet.public_text, packet.session_text, packet.dm_text)
        return packet

    context_channel = discord.utils.get(category.text_channels, name="context")
    dm_planning_channel = discord.utils.get(category.text_channels, name="dm-planning")

    context_entries = await _load_channel_entries(context_channel)
    dm_entries = await _load_channel_entries(dm_planning_channel) if include_dm_context else []

    packet.public_entries = _resolve_scope(context_entries, "public")
    packet.session_entries = _resolve_scope(context_entries, "session")
    packet.dm_entries = _resolve_scope(dm_entries, "dm")

    packet.public_text = _entries_to_text(packet.public_entries)
    packet.session_text = _entries_to_text(packet.session_entries)
    packet.dm_text = _entries_to_text(packet.dm_entries) if include_dm_context else None

    packet.public_source = "discord" if packet.public_entries else "empty"
    packet.session_source = "discord" if packet.session_entries else "empty"
    packet.dm_source = "discord" if packet.dm_entries else "empty"

    if fallback_to_local_files:
        if not packet.public_text:
            packet.public_text = read_context_text("public") or None
            if packet.public_text:
                packet.public_source = "local_fallback"
        if not packet.session_text:
            packet.session_text = read_context_text("session") or None
            if packet.session_text:
                packet.session_source = "local_fallback"
        if include_dm_context and not packet.dm_text:
            packet.dm_text = read_context_text("dm") or None
            if packet.dm_text:
                packet.dm_source = "local_fallback"

    packet.text_block = build_context_block(
        public_text=packet.public_text,
        session_text=packet.session_text,
        dm_text=packet.dm_text,
    )
    return packet
