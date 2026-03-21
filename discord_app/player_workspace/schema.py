from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


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
class IdentityBlock:
    character_name: str | None = None
    player_name: str | None = None
    level: str | None = None
    race: str | None = None
    class_name: str | None = None
    subclass: str | None = None
    background: str | None = None
    alignment: str | None = None
    deity: str | None = None
    xp: str | None = None
    build_line: str | None = None


@dataclass(slots=True)
class CharacterSections:
    profile: str = ""
    core_status: str = ""
    abilities: str = ""
    skills: str = ""
    actions: str = ""
    rules: str = ""
    reference_links: str = ""
    items: str = ""
    encumbrance: str = ""
    currency: str = ""
    missing_info: str = ""


@dataclass(slots=True)
class ResourcePool:
    name: str
    value: str
    max_value: str | None = None
    reset: str | None = None
    notes: str | None = None


@dataclass(slots=True)
class Attack:
    name: str
    to_hit: str | None = None
    damage: str | None = None
    damage_type: str | None = None
    properties: str | None = None


@dataclass(slots=True)
class ReferenceLink:
    label: str
    url: str
    source_type: str | None = None


@dataclass(slots=True)
class CharacterDraft:
    mode: CreateMode
    raw_markdown: str
    identity: IdentityBlock = field(default_factory=IdentityBlock)
    concept: str | None = None
    sections: CharacterSections = field(default_factory=CharacterSections)
    missing_info: list[str] = field(default_factory=list)
    resource_pools: list[ResourcePool] = field(default_factory=list)
    attacks: list[Attack] = field(default_factory=list)
    reference_links: list[ReferenceLink] = field(default_factory=list)
    section_map: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ValidationIssue:
    message: str
    severity: Literal["error", "warning"] = "warning"
    section: str | None = None


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    renderable: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)


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
    draft: CharacterDraft
    validation: ValidationResult
    cards: PlayerWorkspaceCardBundle
    slots: WorkspaceSlots = field(default_factory=WorkspaceSlots)


# Backwards-compatible aliases while the command layer migrates.
PlayerWorkspaceDraft = CharacterDraft
