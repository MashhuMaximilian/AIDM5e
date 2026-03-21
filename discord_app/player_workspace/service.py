from __future__ import annotations

import logging
import re

from ai_services.gemini_client import gemini_client

from .parsing import parse_player_workspace_draft
from .rendering import render_player_workspace_cards
from .schema import (
    CharacterDraft,
    CharacterSections,
    IdentityBlock,
    PlayerWorkspaceBundle,
    PlayerWorkspaceRequest,
    ReferenceLink,
    ResourcePool,
)
from .strategies import IdeaStrategy, ImportStrategy
from .validator import validate_draft


logger = logging.getLogger(__name__)
CRITICAL_IMPORT_SECTIONS = ("core_status", "abilities", "skills", "actions")
OPTIONAL_IMPORT_REPAIR_SECTIONS = ("reference_links",)

MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def _extract_spell_names(rules_text: str) -> list[str]:
    section_match = re.search(
        r"\*\*✨ Spellbook / Known Spells\*\*(.*?)(?=\n\s*\*\*|\n###|\Z)",
        rules_text or "",
        re.DOTALL,
    )
    if not section_match:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for raw in section_match.group(1).splitlines():
        line = raw.strip().lstrip("*- ").strip()
        if not line or ":" not in line:
            continue
        _, value = line.split(":", 1)
        for part in value.split(","):
            cleaned = re.sub(r"[*_`]", "", part).strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            names.append(cleaned)
    return names


def _extract_item_names(items_text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for raw in (items_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        numbered = re.match(r"^\d+\.\s+(.+)$", line)
        bullet = re.match(r"^\*\s+\*\*([^:*]+)\*\*", line)
        if numbered:
            candidate = re.sub(r"`", "", numbered.group(1)).strip()
            candidate = re.sub(r"\s*\(.*?\)\s*$", "", candidate).strip()
        elif bullet:
            candidate = bullet.group(1).strip()
        else:
            continue
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(candidate)
    return names


def _reference_link_categories(reference_text: str) -> dict[str, set[str]]:
    categories = {
        "Race / Class / Subclass": set(),
        "Feats": set(),
        "Spells": set(),
        "Items": set(),
        "Other": set(),
    }
    current_category = "Other"
    for raw in (reference_text or "").splitlines():
        line = raw.strip()
        if not line or "Reference Links" in line:
            continue
        if line.startswith("**") and line.endswith("**"):
            heading = line.strip("* ").strip().lower()
            if "race" in heading or "class" in heading or "subclass" in heading:
                current_category = "Race / Class / Subclass"
            elif "feat" in heading:
                current_category = "Feats"
            elif "spell" in heading:
                current_category = "Spells"
            elif "item" in heading:
                current_category = "Items"
            else:
                current_category = "Other"
            continue
        match = MARKDOWN_LINK_RE.search(line)
        if match:
            categories[current_category].add(match.group(1).strip().lower())
    return categories


def _links_are_sparse(draft: CharacterDraft) -> bool:
    categories = _reference_link_categories(draft.sections.reference_links)
    spell_names = _extract_spell_names(draft.sections.rules)
    item_names = _extract_item_names(draft.sections.items)
    if spell_names and len(categories["Spells"]) < len(spell_names):
        return True
    if item_names and len(categories["Items"]) < len(item_names):
        return True
    return not any(categories.values())


def _pick(primary: str | None, fallback: str | None) -> str | None:
    return primary if (primary or "").strip() else fallback


def _merge_identity(base: IdentityBlock, patch: IdentityBlock) -> IdentityBlock:
    return IdentityBlock(
        character_name=_pick(patch.character_name, base.character_name),
        player_name=_pick(patch.player_name, base.player_name),
        level=_pick(patch.level, base.level),
        race=_pick(patch.race, base.race),
        class_name=_pick(patch.class_name, base.class_name),
        subclass=_pick(patch.subclass, base.subclass),
        background=_pick(patch.background, base.background),
        alignment=_pick(patch.alignment, base.alignment),
        deity=_pick(patch.deity, base.deity),
        xp=_pick(patch.xp, base.xp),
        build_line=_pick(patch.build_line, base.build_line),
    )


def _merge_sections(base: CharacterSections, patch: CharacterSections) -> CharacterSections:
    return CharacterSections(
        summary=_pick(patch.summary, base.summary) or "",
        profile=_pick(patch.profile, base.profile) or "",
        core_status=_pick(patch.core_status, base.core_status) or "",
        abilities=_pick(patch.abilities, base.abilities) or "",
        skills=_pick(patch.skills, base.skills) or "",
        actions=_pick(patch.actions, base.actions) or "",
        rules=_pick(patch.rules, base.rules) or "",
        reference_links=_pick(patch.reference_links, base.reference_links) or "",
        items=_pick(patch.items, base.items) or "",
        encumbrance=_pick(patch.encumbrance, base.encumbrance) or "",
        currency=_pick(patch.currency, base.currency) or "",
        missing_info=_pick(patch.missing_info, base.missing_info) or "",
    )


def _merge_links(base: list[ReferenceLink], patch: list[ReferenceLink]) -> list[ReferenceLink]:
    merged: list[ReferenceLink] = []
    seen: set[tuple[str, str]] = set()
    for item in [*base, *patch]:
        key = (item.label.strip().lower(), item.url.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _merge_resources(base: list[ResourcePool], patch: list[ResourcePool]) -> list[ResourcePool]:
    merged: dict[str, ResourcePool] = {item.name.strip().lower(): item for item in base if item.name.strip()}
    for item in patch:
        key = item.name.strip().lower()
        if key:
            merged[key] = item
    return list(merged.values())


def _merge_drafts(base: CharacterDraft, patch: CharacterDraft) -> CharacterDraft:
    return CharacterDraft(
        mode=base.mode,
        raw_markdown="\n\n".join(part for part in [base.raw_markdown.strip(), patch.raw_markdown.strip()] if part),
        identity=_merge_identity(base.identity, patch.identity),
        concept=_pick(patch.concept, base.concept),
        sections=_merge_sections(base.sections, patch.sections),
        missing_info=list(dict.fromkeys([*base.missing_info, *patch.missing_info])),
        resource_pools=_merge_resources(base.resource_pools, patch.resource_pools),
        attacks=patch.attacks or base.attacks,
        reference_links=_merge_links(base.reference_links, patch.reference_links),
        section_map={**base.section_map, **{key: value for key, value in patch.section_map.items() if (value or "").strip()}},
    )


class CreatePlayerService:
    def __init__(self, *, gemini=gemini_client) -> None:
        self.gemini = gemini
        self._strategies = {
            "idea": IdeaStrategy(),
            "import": ImportStrategy(),
        }

    async def create(self, request: PlayerWorkspaceRequest) -> PlayerWorkspaceBundle:
        strategy = self._strategies[request.mode]
        raw_markdown = await strategy.generate(request, self.gemini)
        draft = parse_player_workspace_draft(raw_markdown, mode=request.mode)
        validation = validate_draft(draft)
        logger.info(
            "Player workspace validation after primary %s pass: missing_sections=%s missing_fields=%s",
            request.mode,
            validation.missing_sections,
            validation.missing_fields,
        )
        if request.mode == "import":
            missing_critical = [section for section in CRITICAL_IMPORT_SECTIONS if section in validation.missing_sections]
            missing_optional = [
                section
                for section in OPTIONAL_IMPORT_REPAIR_SECTIONS
                if not getattr(draft.sections, section, "").strip()
            ]
            repair_sections = list(dict.fromkeys([*missing_critical, *missing_optional]))
            if repair_sections and hasattr(strategy, "repair"):
                logger.info("Player import missing critical sections %s; running one repair pass", ", ".join(missing_critical))
                repair_markdown = await strategy.repair(
                    request,
                    self.gemini,
                    missing_sections=repair_sections,
                    current_markdown=raw_markdown,
                )
                if (repair_markdown or "").strip():
                    repaired = parse_player_workspace_draft(repair_markdown, mode=request.mode)
                    draft = _merge_drafts(draft, repaired)
                    validation = validate_draft(draft)
                    logger.info(
                        "Player workspace validation after repair pass: missing_sections=%s missing_fields=%s",
                        validation.missing_sections,
                        validation.missing_fields,
                    )
            if _links_are_sparse(draft) and hasattr(strategy, "backfill_reference_links"):
                logger.info("Player import reference links are sparse; running dedicated links backfill pass")
                links_markdown = await strategy.backfill_reference_links(
                    request,
                    self.gemini,
                    current_markdown=draft.raw_markdown,
                )
                if (links_markdown or "").strip():
                    linked = parse_player_workspace_draft(links_markdown, mode=request.mode)
                    draft = _merge_drafts(draft, linked)
        cards = render_player_workspace_cards(request, draft, validation)
        return PlayerWorkspaceBundle(
            request=request,
            draft=draft,
            validation=validation,
            cards=cards,
        )
