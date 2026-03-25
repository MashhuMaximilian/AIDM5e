from __future__ import annotations

import re

from .prompting import build_thread_welcome_text
from .schema import PlayerWorkspaceCardBundle, PlayerWorkspaceRequest


SECTION_HEADING_RE = re.compile(r"^\s*###\s+(.*\S)\s*$", re.MULTILINE)
CODE_BLOCK_RE = re.compile(r"```(?:\w+)?\n.*?```", re.DOTALL)

TRUNCATION_SUFFIX = "\n\n[Truncated]"
CARD_LIMIT = 3900

SLOT_ORDER = (
    "character_card",
    "profile_card",
    "skills_actions_card",
    "rules_card",
    "items_card",
    "links_card",
)


def _normalize_heading(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _slot_for_heading(title: str) -> str | None:
    normalized = _normalize_heading(title)

    if "character summary" in normalized or normalized == "summary card":
        return "character_card"
    if "character profile" in normalized or normalized == "profile card":
        return "profile_card"
    if (
        "actions in combat" in normalized
        or "actions magic" in normalized
        or "stats skills" in normalized
        or "skills actions" in normalized
        or "ability scores" in normalized
        or "skills senses" in normalized
    ):
        return "skills_actions_card"
    if (
        normalized == "rules card"
        or "rules features" in normalized
        or "class features" in normalized
        or "features magic" in normalized
        or normalized.startswith("rules ")
    ):
        return "rules_card"
    if (
        normalized == "items card"
        or "inventory" in normalized
        or "attune" in normalized
        or "currency" in normalized
        or "encumbrance" in normalized
    ):
        return "items_card"
    if "reference links" in normalized or normalized == "links card":
        return "links_card"
    return None


def _iter_sections(markdown: str) -> list[tuple[str, str]]:
    text = (markdown or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    matches = list(SECTION_HEADING_RE.finditer(text))
    if not matches:
        return []

    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        heading = match.group(1).strip()
        sections.append((heading, section_text))
    return sections


def _extract_profile_stats_sections(profile_text: str) -> tuple[str, str]:
    if not profile_text.strip():
        return profile_text, ""

    moved_blocks: list[str] = []
    cleaned = profile_text
    for match in CODE_BLOCK_RE.finditer(profile_text):
        block = match.group(0)
        upper = block.upper()
        if "ABILITY SCORES & SAVING THROWS" in upper or "SKILLS & SENSES" in upper:
            moved_blocks.append(block.strip())
            cleaned = cleaned.replace(block, "").strip()

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    stats_text = "\n\n".join(block for block in moved_blocks if block).strip()
    return cleaned, stats_text


def _truncate_card(text: str, *, limit: int = CARD_LIMIT) -> str:
    cleaned = (text or "").strip() or "Needs review."
    if len(cleaned) <= limit:
        return cleaned

    lines = cleaned.splitlines()
    kept: list[str] = []
    truncated = False

    for line in lines:
        candidate_lines = kept + [line]
        candidate_text = "\n".join(candidate_lines).rstrip()
        closing = "\n```" if candidate_text.count("```") % 2 else ""
        if len(candidate_text + closing + TRUNCATION_SUFFIX) > limit:
            truncated = True
            break
        kept.append(line)

    if not truncated:
        return cleaned[:limit].rstrip()

    while kept:
        result = "\n".join(kept).rstrip()
        if result.count("```") % 2:
            result_with_closing = result + "\n```"
        else:
            result_with_closing = result
        if len(result_with_closing + TRUNCATION_SUFFIX) <= limit:
            return result_with_closing + TRUNCATION_SUFFIX
        kept.pop()

    return "[Truncated]"


def split_markdown_into_cards(
    markdown: str,
    request: PlayerWorkspaceRequest,
) -> PlayerWorkspaceCardBundle:
    sections_by_slot: dict[str, list[str]] = {slot: [] for slot in SLOT_ORDER}

    for heading, section_text in _iter_sections(markdown):
        slot = _slot_for_heading(heading)
        if slot is None:
            continue
        sections_by_slot[slot].append(section_text.strip())

    if sections_by_slot["profile_card"]:
        profile_text = "\n\n".join(sections_by_slot["profile_card"]).strip()
        cleaned_profile, stats_text = _extract_profile_stats_sections(profile_text)
        sections_by_slot["profile_card"] = [cleaned_profile] if cleaned_profile else []
        if stats_text:
            sections_by_slot["skills_actions_card"].insert(0, stats_text)

    cards: dict[str, str] = {}
    for slot in SLOT_ORDER:
        joined = "\n\n".join(part for part in sections_by_slot[slot] if part and part.strip()).strip()
        cards[slot] = _truncate_card(joined or "Needs review.")

    return PlayerWorkspaceCardBundle(
        character_card=cards["character_card"],
        profile_card=cards["profile_card"],
        skills_actions_card=cards["skills_actions_card"],
        rules_card=cards["rules_card"],
        items_card=cards["items_card"],
        links_card=cards["links_card"],
        welcome_text=build_thread_welcome_text(request),
    )
