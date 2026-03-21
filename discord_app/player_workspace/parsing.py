from __future__ import annotations

import re
from collections import OrderedDict

from .schema import CharacterDraft, CharacterSections, IdentityBlock, ReferenceLink, ResourcePool


HEADING_RE = re.compile(r"^\s{0,3}(#{2,3})\s+(.*\S)\s*$")
BLOCKQUOTE_RE = re.compile(r"^\s*>\s+(.*\S)\s*$")
FIELD_RE = re.compile(r"^\s*(NAME|LEVEL|XP|RACE|CLASS|SUBCLASS|PLAYER|BACKGROUND|ALIGNMENT|DEITY)\s*\.{0,}\s*:?\s*(.*\S)\s*$", re.IGNORECASE)
PROFILE_FIELD_PAIR_RE = re.compile(
    r"(NAME|LEVEL|XP|RACE|CLASS|SUBCLASS|PLAYER|BACKGROUND|ALIGNMENT|DEITY)\s*\.{2,}:?\s*(.*?)"
    r"(?=(?:\s{2,}(?:NAME|LEVEL|XP|RACE|CLASS|SUBCLASS|PLAYER|BACKGROUND|ALIGNMENT|DEITY)\s*\.{2,}:?)|$)",
    re.IGNORECASE,
)


def _slugify_heading(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    if "character profile" in normalized or normalized == "profile card":
        return "profile"
    if normalized in {"sheet card", "sheet"}:
        return "sheet"
    if "core status" in normalized or "resources pools" in normalized:
        return "core_status"
    if "ability scores" in normalized or normalized == "abilities":
        return "abilities"
    if "skills senses" in normalized or normalized == "skills":
        return "skills"
    if "actions in combat" in normalized or "actions magic" in normalized or "combat essentials" in normalized:
        return "actions"
    if "class features" in normalized or "features traits" in normalized or "features magic" in normalized or normalized == "rules card":
        return "rules"
    if "inventory attunement" in normalized or normalized == "items card":
        return "items"
    if "encumbrance" in normalized:
        return "encumbrance"
    if "currency" in normalized:
        return "currency"
    if "reference links" in normalized or normalized == "links":
        return "reference_links"
    if "needs review" in normalized or "missing" in normalized:
        return "missing_info"
    return normalized.replace(" ", "_")


def _extract_sections(raw_markdown: str) -> OrderedDict[str, list[str]]:
    sections: OrderedDict[str, list[str]] = OrderedDict()
    current_key: str | None = None
    current_lines: list[str] = []
    in_code_fence = False

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key is None:
            current_lines = []
            return
        body = "\n".join(current_lines).strip()
        if body:
            sections.setdefault(current_key, []).append(body)
        current_lines = []

    for line in raw_markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            current_lines.append(line.rstrip())
            continue

        heading_match = HEADING_RE.match(line)
        if heading_match and not in_code_fence:
            flush()
            current_key = _slugify_heading(heading_match.group(2))
            current_lines.append(line.rstrip())
            continue

        if current_key is None:
            current_key = "preamble"
        current_lines.append(line.rstrip())

    flush()
    return sections


def _join_sections(sections: OrderedDict[str, list[str]], *keys: str) -> str:
    parts: list[str] = []
    for key in keys:
        for value in sections.get(key, []):
            value = value.strip()
            if value:
                parts.append(value)
    return "\n\n".join(parts).strip()


def _extract_code_blocks(raw_markdown: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_code_fence = False

    for line in raw_markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code_fence:
                current = [line.rstrip()]
                in_code_fence = True
            else:
                current.append(line.rstrip())
                blocks.append("\n".join(current).strip())
                current = []
                in_code_fence = False
            continue

        if in_code_fence:
            current.append(line.rstrip())

    return blocks


def _classify_code_blocks(raw_markdown: str) -> dict[str, list[str]]:
    classified: dict[str, list[str]] = {}
    for block in _extract_code_blocks(raw_markdown):
        key = _classify_code_block(block)
        if not key:
            continue
        classified.setdefault(key, [])
        if block not in classified[key]:
            classified[key].append(block)
    return classified


def _classify_code_block(block: str) -> str | None:
    lines = [line.strip() for line in block.splitlines()[1:-1] if line.strip()]
    if not lines:
        return None

    first = lines[0].lower()
    if "character level, race, & class" in first:
        return "profile_table"
    if first.startswith("core status"):
        return "core_status"
    if first.startswith("ability scores & saving throws"):
        return "abilities"
    if first.startswith("skills & senses"):
        return "skills"
    if "encumbrance" in first:
        return "encumbrance"
    if "currency" in first:
        return "currency"
    return None


def _extract_profile_fields(raw_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in raw_text.splitlines():
        for match in PROFILE_FIELD_PAIR_RE.finditer(line):
            fields[match.group(1).upper()] = match.group(2).strip()
    return fields


def _extract_field(raw_text: str, field_name: str) -> str | None:
    paired_fields = _extract_profile_fields(raw_text)
    if field_name.upper() in paired_fields:
        value = paired_fields[field_name.upper()].strip()
        return value or None

    for line in raw_text.splitlines():
        match = FIELD_RE.match(line)
        if match and match.group(1).upper() == field_name.upper():
            value = match.group(2).strip()
            return value or None
    return None


def _extract_build_line(raw_text: str) -> str | None:
    level = _extract_field(raw_text, "LEVEL")
    race = _extract_field(raw_text, "RACE")
    klass = _extract_field(raw_text, "CLASS")
    subclass = _extract_field(raw_text, "SUBCLASS")

    parts: list[str] = []
    if level:
        parts.append(f"Level {level}")
    if race:
        parts.append(race)
    if klass:
        parts.append(f"{klass} ({subclass})" if subclass else klass)
    elif subclass:
        parts.append(f"({subclass})")
    return " ".join(parts).strip() or None


def _extract_concept(sections: OrderedDict[str, list[str]], raw_text: str) -> str | None:
    profile_text = _join_sections(sections, "profile") or raw_text
    for line in profile_text.splitlines():
        match = BLOCKQUOTE_RE.match(line)
        if match:
            concept = match.group(1).strip()
            return concept.strip('"').strip("'") or None

    paragraphs = [part.strip() for part in re.split(r"\n{2,}", profile_text) if part.strip()]
    if len(paragraphs) >= 2:
        candidate = paragraphs[1]
        if not candidate.startswith("```"):
            return candidate.splitlines()[0].strip() or None
    return None


def _strip_non_profile_code_blocks(profile_text: str) -> str:
    cleaned = profile_text
    for block in _extract_code_blocks(profile_text):
        if _classify_code_block(block) not in {None, "profile_table"}:
            cleaned = cleaned.replace(block, "").strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _strip_classified_code_blocks(section_text: str, *, strip_types: set[str]) -> str:
    cleaned = section_text
    for block in _extract_code_blocks(section_text):
        key = _classify_code_block(block)
        if key in strip_types:
            cleaned = cleaned.replace(block, "").strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_missing_info(sections: OrderedDict[str, list[str]]) -> list[str]:
    missing_text = _join_sections(sections, "missing_info")
    if not missing_text:
        return []
    missing: list[str] = []
    for line in missing_text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^\s*(?:[-*•]|o|\d+\.)\s*", "", cleaned)
        if cleaned.lower().startswith("needs review:"):
            cleaned = cleaned.split(":", 1)[1].strip()
        if cleaned:
            missing.append(cleaned)
    return missing


def _extract_reference_links(reference_text: str) -> list[ReferenceLink]:
    links: list[ReferenceLink] = []
    for line in reference_text.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*•]|\d+\.)\s*", "", line.strip())
        if not cleaned or ":" not in cleaned:
            continue
        label, value = cleaned.split(":", 1)
        url_match = re.search(r"https?://\S+", value)
        if not url_match:
            continue
        links.append(ReferenceLink(label=label.strip("* ").strip(), url=url_match.group(0).strip(), source_type="reference"))
    return links


RESOURCE_ROW_RE = re.compile(r"([A-Z][A-Z /&'.+-]+?)\s*\.{2,}\s*(.+)$")


def _extract_resource_pools(core_status_text: str) -> list[ResourcePool]:
    pools: list[ResourcePool] = []
    for line in core_status_text.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith(("```", "-", "CORE STATUS", "RESOURCES & POOLS")):
            continue
        match = RESOURCE_ROW_RE.match(cleaned)
        if not match:
            continue
        name = match.group(1).strip()
        value = match.group(2).strip()
        pools.append(ResourcePool(name=name, value=value))
    return pools


def parse_player_workspace_draft(raw_markdown: str, *, mode: str = "import") -> CharacterDraft:
    sections = _extract_sections(raw_markdown or "")
    code_blocks = _classify_code_blocks(raw_markdown or "")

    profile_text = _strip_non_profile_code_blocks(_join_sections(sections, "profile"))
    core_status_text = "\n\n".join(code_blocks.get("core_status", [])).strip()
    abilities_text = "\n\n".join(code_blocks.get("abilities", [])).strip()
    skills_text = "\n\n".join(code_blocks.get("skills", [])).strip()
    actions_text = _strip_classified_code_blocks(
        _join_sections(sections, "actions"),
        strip_types={"core_status", "abilities", "skills", "encumbrance", "currency", "profile_table"},
    )
    rules_text = _strip_classified_code_blocks(
        _join_sections(sections, "rules"),
        strip_types={"core_status", "abilities", "skills", "encumbrance", "currency", "profile_table"},
    )
    reference_text = _join_sections(sections, "reference_links")
    items_text = _strip_classified_code_blocks(
        _join_sections(sections, "items"),
        strip_types={"encumbrance", "currency"},
    )
    encumbrance_text = "\n\n".join(code_blocks.get("encumbrance", [])).strip()
    currency_text = "\n\n".join(code_blocks.get("currency", [])).strip()
    missing_info = _extract_missing_info(sections)

    identity = IdentityBlock()
    identity.character_name = _extract_field(raw_markdown, "NAME") if _extract_field(raw_markdown, "NAME") else None
    identity.player_name = _extract_field(raw_markdown, "PLAYER")
    identity.level = _extract_field(raw_markdown, "LEVEL")
    identity.race = _extract_field(raw_markdown, "RACE")
    identity.class_name = _extract_field(raw_markdown, "CLASS")
    identity.subclass = _extract_field(raw_markdown, "SUBCLASS")
    identity.background = _extract_field(raw_markdown, "BACKGROUND")
    identity.alignment = _extract_field(raw_markdown, "ALIGNMENT")
    identity.deity = _extract_field(raw_markdown, "DEITY")
    identity.xp = _extract_field(raw_markdown, "XP")
    identity.build_line = _extract_build_line(raw_markdown)

    profile_heading_match = re.search(r"^#{2,3}\s+.+?—\s*(.+?)\s*$", profile_text, re.MULTILINE)
    if profile_heading_match:
        identity.character_name = profile_heading_match.group(1).strip()
    identity.character_name = identity.character_name or None

    return CharacterDraft(
        mode=mode,
        raw_markdown=raw_markdown.strip(),
        identity=identity,
        concept=_extract_concept(sections, raw_markdown),
        sections=CharacterSections(
            profile=profile_text,
            core_status=core_status_text,
            abilities=abilities_text,
            skills=skills_text,
            actions=actions_text,
            rules=rules_text,
            reference_links=reference_text,
            items=items_text,
            encumbrance=encumbrance_text,
            currency=currency_text,
            missing_info=_join_sections(sections, "missing_info"),
        ),
        missing_info=missing_info,
        resource_pools=_extract_resource_pools(core_status_text),
        attacks=[],
        reference_links=_extract_reference_links(reference_text),
        section_map={key: "\n\n".join(values).strip() for key, values in sections.items()},
    )
