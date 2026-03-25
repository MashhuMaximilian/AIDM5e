from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


CreateMode = Literal["idea", "import"]
WorkspaceMode = CreateMode


@dataclass(slots=True)
class SourceBundle:
    note: str | None = None
    source_text: str | None = None
    file_paths: list[str] = field(default_factory=list)
    source_label: str | None = None


@dataclass(slots=True)
class PlayerWorkspaceRequest:
    mode: CreateMode
    character_name: str | None = None
    player_name: str | None = None
    source: SourceBundle = field(default_factory=SourceBundle)
    thread_name: str | None = None


@dataclass(slots=True)
class WorkspaceSlots:
    character_card_message_id: int | None = None
    profile_card_message_id: int | None = None
    skills_actions_card_message_id: int | None = None
    rules_card_message_id: int | None = None
    links_card_message_id: int | None = None
    items_card_message_id: int | None = None


@dataclass(slots=True)
class PlayerWorkspaceCardBundle:
    character_card: str
    profile_card: str
    skills_actions_card: str
    rules_card: str
    links_card: str
    items_card: str
    welcome_text: str


@dataclass(slots=True)
class PlayerWorkspaceBundle:
    request: PlayerWorkspaceRequest
    cards: PlayerWorkspaceCardBundle
    draft: Any | None = None
    validation: Any | None = None
    slots: WorkspaceSlots = field(default_factory=WorkspaceSlots)
