from __future__ import annotations

import re

from .schema import CharacterDraft, PlayerWorkspaceCardBundle, PlayerWorkspaceRequest, ReferenceLink, ValidationResult


HEADING_RE = re.compile(r"^\s{0,3}(#{2,3})\s+(.*\S)\s*$")
URL_RE = re.compile(r"https?://\S+")
CODE_BLOCK_RE = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)
LABEL_VALUE_RE = re.compile(r"^\s*([A-Z][A-Z /&'.+-]+?)\s*\.{0,}\s*:?\s*(.+?)\s*$")
ABILITY_ROW_RE = re.compile(
    r"^\|\s*(\[[^\]]+\])?\s*(STR|DEX|CON|INT|WIS|CHA)\s*\|\s*([^\|]+?)\s*\|\s*([^\|]+?)\s*\|\s*([^\|]+?)\s*\|",
    re.IGNORECASE,
)
SKILL_ENTRY_RE = re.compile(r"\[(?P<marker>[^\]]+)\]\s*(?P<name>[A-Za-z/' ]+?)\s*\.{1,}\s*(?P<value>[+-]?\d+)")
PASSIVE_RE = re.compile(r"PASSIVE\s+([A-Z ]+)\s*:\s*([^\|\n]+)", re.IGNORECASE)
RESOURCE_LINE_RE = re.compile(
    r"^\s*[*-]\s+\*\*(?P<name>[^:*]+):\*\*.*?(?P<tail>(?P<count>\d+)\s*/\s*(?P<reset>Short Rest|Long Rest|Day|Dawn|Sunset))",
    re.IGNORECASE,
)
RESOURCE_CHARGE_RE = re.compile(
    r"^\s*[*-]\s+\*\*(?P<name>[^:*]+):\*\*.*?(?P<tail>(?P<count>\d+)\s+Charges?.*)",
    re.IGNORECASE,
)

CORE_STAT_LABELS = ("AC", "HP", "SPEED", "INIT", "PB")
ABILITY_ORDER = ("STR", "DEX", "CON", "INT", "WIS", "CHA")
SKILL_ORDER = (
    "Acrobatics",
    "Animal Hand",
    "Arcana",
    "Athletics",
    "Deception",
    "History",
    "Insight",
    "Intimidation",
    "Investigation",
    "Medicine",
    "Nature",
    "Perception",
    "Performance",
    "Persuasion",
    "Religion",
    "Sleight Hand",
    "Stealth",
    "Survival",
)


def tidy_markdown_for_discord(text: str) -> str:
    if not text:
        return ""

    cleaned_lines: list[str] = []
    in_code_fence = False

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            if cleaned_lines and cleaned_lines[-1] and cleaned_lines[-1].strip() and cleaned_lines[-1].strip() != "```":
                pass
            cleaned_lines.append(line)
            continue

        if not in_code_fence and HEADING_RE.match(line):
            while cleaned_lines and not cleaned_lines[-1].strip():
                cleaned_lines.pop()
            if cleaned_lines:
                cleaned_lines.append("")
            cleaned_lines.append(line)
            cleaned_lines.append("")
            continue

        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _coalesce(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip()).strip()


def _code_body(text: str) -> str:
    match = CODE_BLOCK_RE.search(text or "")
    return match.group(1).strip("\n") if match else (text or "").strip()


def _strip_first_code_block(text: str) -> str:
    return CODE_BLOCK_RE.sub("", text or "", count=1).strip()


def _dotted_label(label: str, width: int = 11) -> str:
    label = label.strip().upper()
    dots = "." * max(1, width - len(label))
    return f"{label} {dots}"


def _compact_resource_value(value: str) -> str:
    compact = (value or "").strip()
    replacements = (
        ("Short Rest", "SR"),
        ("Long Rest", "LR"),
        ("Regained at Dawn", "@ Dawn"),
        ("regained at Dawn", "@ Dawn"),
        ("Regained at Sunset", "@ Sunset"),
        ("regains at Sunset", "@ Sunset"),
        ("regained at Sunset", "@ Sunset"),
    )
    for source, target in replacements:
        compact = compact.replace(source, target)
    compact = re.sub(r"\s*/\s*", "/", compact)
    compact = re.sub(r"\s{2,}", " ", compact)
    return compact.strip()


def _format_core_row(label: str, value: str, width: int = 22) -> str:
    return f"{_dotted_label(label):<13} {value}".ljust(width)


def _parse_core_status_rows(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    left_rows: list[tuple[str, str]] = []
    right_rows: list[tuple[str, str]] = []
    body = _code_body(text)
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("CORE STATUS", "RESOURCES & POOLS", "-", "[")):
            continue
        segments = re.split(r"\s{2,}", stripped)
        for segment in segments:
            cleaned = segment.strip()
            if not cleaned:
                continue
            if "." in cleaned:
                bits = [bit for bit in re.split(r"\.{2,}", cleaned) if bit.strip()]
                if len(bits) >= 2:
                    label, value = bits[0].strip(), bits[1].strip()
                else:
                    continue
            else:
                match = LABEL_VALUE_RE.match(cleaned)
                if not match:
                    continue
                label, value = match.group(1).strip(), match.group(2).strip()
            upper_label = label.upper()
            target = left_rows if upper_label in CORE_STAT_LABELS else right_rows
            target.append((upper_label, value))
    dedup = {}
    for label, value in left_rows:
        dedup[label] = value
    left_rows = [(label, dedup[label]) for label in CORE_STAT_LABELS if label in dedup]
    dedup = {}
    for label, value in right_rows:
        dedup[label] = value
    right_rows = list(dedup.items())
    return left_rows, right_rows


def _render_core_status_table(text: str, *, build_line: str | None = None) -> str:
    left_rows, right_rows = _parse_core_status_rows(text)
    if not left_rows and not right_rows:
        return text.strip()
    lines = [
        "```",
    ]
    if (build_line or "").strip():
        lines.extend([
            f"BUILD......: {build_line.strip()}",
            "",
        ])
    lines.extend([
        "CORE STATUS",
        "----------------------",
    ])
    for l_label, l_value in left_rows:
        lines.append(_format_core_row(l_label, _compact_resource_value(l_value), width=22))
    lines.extend([
        "----------------------",
        "RESOURCES & POOLS",
    ])
    for r_label, r_value in right_rows:
        compact_label = (r_label or "RESOURCE")[:18]
        lines.append(f"{compact_label:.<24} {_compact_resource_value(r_value)}")
    lines.append("------------------------")
    lines.append("```")
    return "\n".join(lines)


def _compact_profile_value(value: str | None, *, limit: int = 18) -> str:
    compact = (value or "Unknown").strip()
    compact = compact.replace("Background", "BG")
    compact = re.sub(r"\s{2,}", " ", compact)
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _render_profile_identity_table(draft: CharacterDraft) -> str:
    identity = draft.identity
    lines = [
        "```",
        "[ CHARACTER LEVEL, RACE, & CLASS ]",
        "----------------------------------------",
        f"LEVEL.....: {identity.level or 'Unknown'}",
        f"RACE......: {identity.race or 'Unknown'}",
        f"CLASS.....: {identity.class_name or 'Unknown'}",
        f"SUBCLASS..: {identity.subclass or 'Unknown'}",
        f"XP........: {identity.xp or 'Unknown'}",
        f"PLAYER....: {identity.player_name or 'Unknown'}",
        f"BACKGROUND: {identity.background or 'Unknown'}",
        f"ALIGNMENT.: {identity.alignment or 'Unknown'}",
        f"DEITY.....: {identity.deity or 'Unknown'}",
        "----------------------------------------",
        "```",
    ]
    return "\n".join(lines)


def _normalize_marker(marker: str | None) -> str:
    cleaned = (marker or "").strip()
    if "●" in cleaned or "•" in cleaned:
        return "[●]"
    if "◎" in cleaned or "◉" in cleaned:
        return "[◎]"
    return "[ ]"


def _render_abilities_table(text: str) -> str:
    rows: dict[str, tuple[str, str, str]] = {}
    for line in _code_body(text).splitlines():
        match = ABILITY_ROW_RE.search(line)
        if not match:
            continue
        ability = match.group(2).upper()
        rows[ability] = (
            _normalize_marker(match.group(1)),
            match.group(3).strip(),
            match.group(4).strip(),
            match.group(5).strip(),
        )
    if not rows:
        return text.strip()
    lines = [
        "```",
        "ABILITY SCORES & SAVING THROWS",
        "+---------+-------+-----+------+",
        "| ABILITY | SCORE | MOD | SAVE |",
        "+---------+-------+-----+------+",
    ]
    for ability in ABILITY_ORDER:
        marker, score, mod, save = rows.get(ability, ("[ ]", "Unknown", "Unknown", "Unknown"))
        lines.append(f"| {marker} {ability:<3} | {score:>5} | {mod:>3} | {save:>4} |")
    lines.extend([
        "+---------+-------+-----+------+",
        "● -> Proficient",
        "```",
    ])
    return "\n".join(lines)


def _normalize_skill_name(name: str) -> str:
    normalized = re.sub(r"[^a-z]+", " ", name.lower()).strip()
    mapping = {
        "animal hand": "Animal Hand",
        "sleight hand": "Sleight Hand",
    }
    for skill in SKILL_ORDER:
        if normalized == re.sub(r"[^a-z]+", " ", skill.lower()).strip():
            return skill
    return mapping.get(normalized, name.strip())


def _render_skills_table(text: str) -> str:
    body = _code_body(text)
    entries: dict[str, tuple[str, str]] = {}
    passives: dict[str, str] = {}
    for line in body.splitlines():
        for match in SKILL_ENTRY_RE.finditer(line):
            entries[_normalize_skill_name(match.group("name"))] = (
                _normalize_marker(match.group("marker")),
                match.group("value").strip(),
            )
        for match in PASSIVE_RE.finditer(line):
            passives[match.group(1).strip().upper()] = match.group(2).strip()
    if not entries:
        return text.strip()
    lines = [
        "```",
        "SKILLS & SENSES",
        "-------------------------",
    ]
    for name in SKILL_ORDER:
        marker, value = entries.get(name, ("[ ]", "Unknown"))
        lines.append(f"{marker} {name:<14} .... {value}")
    lines.append("--------------------------")
    passive_perception = passives.get("PERCEPTION", "Unknown")
    passive_insight = passives.get("INSIGHT", "Unknown")
    lines.append(f"PASSIVE PERCEPTION: {passive_perception}")
    lines.append(f"PASSIVE INSIGHT: {passive_insight}")
    lines.append("----------------------------")
    lines.append("Legend:")
    lines.append("[ ] None")
    lines.append("[●] Proficient")
    lines.append("[◎] Expertise")
    lines.append("```")
    return "\n".join(lines)


def _render_magic_excerpt(rules_text: str) -> str:
    lines = []
    capture = False
    for raw_line in (rules_text or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith(("**✨ Spellbook / Known Spells**", "**✨ Magic**", "### ⚔️ ACTIONS & MAGIC")):
            capture = True
        elif capture and stripped.startswith(("## ", "### ", "**")) and not stripped.startswith(("**✨ Spellbook / Known Spells**", "**✨ Magic**")):
            break
        if capture and stripped:
            lines.append(raw_line.rstrip())
    return "\n".join(lines).strip()


def _build_resource_tracking(rules_text: str) -> str:
    if "🔋 Resource Tracking" in (rules_text or ""):
        return ""
    rows: list[str] = []
    seen: set[str] = set()
    for raw_line in (rules_text or "").splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith(("*", "-")):
            continue
        match = RESOURCE_LINE_RE.search(stripped) or RESOURCE_CHARGE_RE.search(stripped)
        if not match:
            continue
        name = match.group("name").strip()
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        count = int(match.group("count"))
        tail = re.sub(r"[`*.]+", "", match.group("tail")).strip()
        if 1 <= count <= 20:
            tracker = " ".join("○" for _ in range(count))
            if tail:
                rows.append(f"**{name}:** {tracker} `{tail}`")
            else:
                rows.append(f"**{name}:** {tracker}")
        else:
            rows.append(f"**{name}:** `{tail}`" if tail else f"**{name}:**")
    if not rows:
        return ""
    return "\n".join(["**🔋 Resource Tracking**", *rows]).strip()


def _normalize_actions_section(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"(?<!\n)([*-]\s+\*\*)", r"\n\1", cleaned)
    cleaned = re.sub(r"(?<!\n)(>\s+\*\*Multiattack:)", r"\n\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_resource_tracking(text: str) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    out: list[str] = []
    in_tracking = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("**🔋 Resource Tracking**"):
            in_tracking = True
            out.append(line)
            continue
        if in_tracking and stripped.startswith(("## ", "### ", "**")) and not stripped.startswith("**🔋 Resource Tracking**"):
            in_tracking = False
        if in_tracking:
            line = line.replace("`[ ]`", "`○`").replace("[ ]", "○")
        out.append(line)
    return "\n".join(out)


def _normalize_reference_links(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    if not URL_RE.search(cleaned):
        return ""
    output: list[str] = ["**🔗 Reference Links**"]
    markdown_links = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", cleaned)
    if markdown_links:
        for label, url in markdown_links:
            output.append(f"* [{label}]({url})")
        return "\n".join(output)
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        output.append(stripped)
    return "\n".join(output)


def _render_single_column_block(title: str, rows: list[str], width: int = 51) -> str:
    bar = "-" * width
    lines = ["```", title, bar, *rows, bar, "```"]
    return "\n".join(lines)


def _render_encumbrance_block(text: str) -> str:
    body = _code_body(text)
    weight = "Unknown"
    push = "Unknown"
    carry = "Unknown"
    match = re.search(r"WEIGHT CARRIED:\s*([^\n]+)", body, re.IGNORECASE)
    if match:
        weight = match.group(1).strip()
    match = re.search(r"PUSH/DRAG/LIFT:\s*([^\n]+)", body, re.IGNORECASE)
    if match:
        push = match.group(1).strip()
    match = re.search(r"CARRY CAPACITY:\s*([^\n]+)", body, re.IGNORECASE)
    if match:
        carry = match.group(1).strip()
    return _render_single_column_block(
        "[🎒 ENCUMBRANCE — LIFTING AND CARRYING ]",
        [
            f"WEIGHT CARRIED: {weight}",
            f"PUSH/DRAG/LIFT: {push}",
            f"CARRY CAPACITY: {carry}",
        ],
        width=51,
    )


def _render_currency_block(text: str) -> str:
    body = _code_body(text)
    values = {"COPPER": "0", "SILVER": "0", "GOLD": "0", "PLATINUM": "0", "ELECTRUM": "0"}
    for label in values:
        match = re.search(rf"{label}\.*:\s*([^\n]+)", body, re.IGNORECASE)
        if match:
            values[label] = match.group(1).strip()
    rows = [
        f"COPPER............: {values['COPPER']}",
        f"SILVER............: {values['SILVER']}",
        f"GOLD..............: {values['GOLD']}",
        f"PLATINUM..........: {values['PLATINUM']}",
        f"ELECTRUM..........: {values['ELECTRUM']}",
    ]
    return _render_single_column_block("[💰 CURRENCY ]", rows, width=32)


def _ensure_feats_section(rules_text: str) -> str:
    cleaned = (rules_text or "").strip()
    if not cleaned or "Feats" in cleaned:
        return cleaned
    detected: list[str] = []
    for feat in ("Magic Initiate", "War Caster", "Fey Touched", "Tough"):
        if re.search(rf"\b{re.escape(feat)}\b", cleaned, re.IGNORECASE):
            detected.append(feat)
    if not detected:
        return cleaned
    feats_block = "\n".join(["**📜 Feats**", *[f"* **{name}**" for name in detected]])
    return _coalesce(cleaned, feats_block)


def _normalize_resource_tracking_block(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    out: list[str] = []
    for raw_line in cleaned.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("**🔋 Resource Tracking**"):
            out.append("**🔋 Resource Tracking**")
            continue
        stripped = stripped.lstrip("* ").strip()
        stripped = stripped.replace("`[ ]`", "`○`").replace("[ ]", "○")
        out.append(stripped)
    return "\n".join(out)


def _strip_duplicate_profile_heading(text: str, character_name: str) -> str:
    lines: list[str] = []
    target = character_name.strip().lower()
    for raw_line in (text or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("### 👤 CHARACTER PROFILE"):
            continue
        if stripped.upper().startswith("👤 CHARACTER PROFILE"):
            continue
        if stripped.upper() == "PROFILE CARD":
            continue
        if stripped.upper() == "MESSAGE":
            continue
        if stripped.lower() == target:
            continue
        lines.append(raw_line)
    return "\n".join(lines).strip()


def _parse_skill_entries(text: str) -> tuple[list[tuple[str, int]], dict[str, str]]:
    entries: list[tuple[str, int]] = []
    passives: dict[str, str] = {}
    body = _code_body(text)
    for line in body.splitlines():
        for match in SKILL_ENTRY_RE.finditer(line):
            name = _normalize_skill_name(match.group("name"))
            try:
                value = int(match.group("value"))
            except ValueError:
                continue
            entries.append((name, value))
        for match in PASSIVE_RE.finditer(line):
            passives[match.group(1).strip().upper()] = match.group(2).strip()
    dedup: dict[str, int] = {}
    for name, value in entries:
        dedup[name] = value
    ordered = list(dedup.items())
    return ordered, passives


def _render_skill_highlights(skills_text: str) -> str:
    entries, passives = _parse_skill_entries(skills_text)
    if not entries and not passives:
        return ""
    ranked = sorted(entries, key=lambda item: (-item[1], item[0]))[:6]
    pieces = [f"`{name} {value:+d}`" for name, value in ranked]
    if "PERCEPTION" in passives:
        pieces.append(f"`Passive Perception {passives['PERCEPTION']}`")
    if "INSIGHT" in passives:
        pieces.append(f"`Passive Insight {passives['INSIGHT']}`")
    return " • ".join(pieces)


def _render_actions_excerpt(actions_text: str, *, limit: int = 5) -> str:
    cleaned = _normalize_actions_section(actions_text)
    if not cleaned:
        return ""
    kept: list[str] = []
    bullet_count = 0
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("### ", "## ")):
            continue
        if stripped.startswith("> "):
            kept.append(line.rstrip())
            continue
        if stripped.startswith(("* ", "- ")):
            kept.append(line.rstrip())
            bullet_count += 1
            if bullet_count >= limit:
                break
    return "\n".join(kept).strip()


def _render_reference_link_list(links: list[ReferenceLink]) -> str:
    if not links:
        return ""
    parts = [f"[{link.label}]({link.url})" for link in links if (link.label or "").strip() and (link.url or "").strip()]
    return " • ".join(parts)


def _render_detail_links(detail_links: dict[str, str] | None) -> str:
    if not detail_links:
        return ""
    ordered = [
        ("Profile", detail_links.get("profile")),
        ("Rules", detail_links.get("rules")),
        ("Items", detail_links.get("items")),
    ]
    parts = [f"[{label}]({url})" for label, url in ordered if url]
    if not parts:
        return ""
    return " • ".join(parts)


def build_player_character_card(
    request: PlayerWorkspaceRequest,
    draft: CharacterDraft,
    validation: ValidationResult,
    *,
    detail_links: dict[str, str] | None = None,
) -> str:
    name = draft.identity.character_name or request.character_name or "Unnamed Character"
    concept = draft.concept or "Needs review."
    build_line = draft.identity.build_line or "Needs review."
    core_status = draft.sections.core_status.strip()
    abilities = draft.sections.abilities.strip()
    skills = draft.sections.skills.strip()
    actions = draft.sections.actions.strip()
    magic_excerpt = _render_magic_excerpt(draft.sections.rules)
    combat_excerpt = _render_actions_excerpt(actions)
    resource_tracking = _normalize_resource_tracking_block(_build_resource_tracking(draft.sections.rules))

    parts = [
        f"**{name.upper()}**",
        f"> {concept}",
    ]
    if core_status:
        parts.extend(["## Core Status & Resources", _render_core_status_table(core_status, build_line=build_line)])
    if abilities:
        parts.extend(["## Ability Scores & Saving Throws", _render_abilities_table(abilities)])
    if skills:
        parts.extend(["## Skills & Senses", _render_skills_table(skills)])
    if combat_excerpt:
        parts.extend(["## Actions in Combat", combat_excerpt])
    if magic_excerpt:
        parts.extend(["## Spells & Magic", tidy_markdown_for_discord(magic_excerpt)])
    if resource_tracking:
        parts.extend(["## Resource Tracking", tidy_markdown_for_discord(resource_tracking)])
    if validation.missing_sections or validation.missing_fields:
        parts.append("## Needs Review")
        for section in validation.missing_sections:
            parts.append(f"• Missing section: {section}")
        for field in validation.missing_fields:
            parts.append(f"• Missing field: {field}")
    return tidy_markdown_for_discord("\n".join(parts))


def render_player_workspace_cards(
    request: PlayerWorkspaceRequest,
    draft: CharacterDraft,
    validation: ValidationResult,
) -> PlayerWorkspaceCardBundle:
    character_card = build_player_character_card(request, draft, validation)
    character_name = draft.identity.character_name or request.character_name or "Unnamed Character"
    cleaned_profile = _strip_duplicate_profile_heading(_strip_first_code_block(draft.sections.profile), character_name)
    profile_body = _coalesce(
        f"### 👤 CHARACTER PROFILE — {character_name}",
        cleaned_profile,
        _render_profile_identity_table(draft),
    )
    profile_card = tidy_markdown_for_discord(profile_body)
    resource_tracking = _build_resource_tracking(draft.sections.rules)
    rules_body = _coalesce(_ensure_feats_section(draft.sections.rules), resource_tracking, _normalize_reference_links(draft.sections.reference_links))
    rules_card = tidy_markdown_for_discord(_normalize_resource_tracking(rules_body))
    items_body = _coalesce(
        draft.sections.items,
        _render_encumbrance_block(draft.sections.encumbrance) if draft.sections.encumbrance.strip() else "",
        _render_currency_block(draft.sections.currency) if draft.sections.currency.strip() else "",
    )
    items_card = tidy_markdown_for_discord(items_body)
    welcome_text = build_thread_welcome_text(request)

    return PlayerWorkspaceCardBundle(
        character_card=character_card,
        profile_card=profile_card,
        rules_card=rules_card,
        items_card=items_card,
        welcome_text=welcome_text,
    )


def build_thread_welcome_text(request: PlayerWorkspaceRequest) -> str:
    display_name = request.character_name or "this character"
    if request.mode == "idea":
        return (
            f"**Character workspace ready for {display_name}.**\n"
            "Use this thread as the draft workspace.\n"
            "Add concept notes, references, and source material here as the build takes shape.\n"
            "Nothing here is campaign canon until someone explicitly publishes a summary."
        )

    return (
        f"**Character workspace ready for {display_name}.**\n"
        "Use this thread as the draft workspace.\n"
        "Post new notes and source material here as the sheet evolves.\n"
        "Nothing here is campaign canon until someone explicitly publishes a summary."
    )
