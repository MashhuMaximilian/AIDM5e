from __future__ import annotations

import re

from .schema import CharacterDraft, PlayerWorkspaceCardBundle, PlayerWorkspaceRequest, ReferenceLink, ResourcePool, ValidationResult


HEADING_RE = re.compile(r"^\s{0,3}(#{2,3})\s+(.*\S)\s*$")
CODE_BLOCK_RE = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)
ABILITY_ROW_RE = re.compile(
    r"^\|\s*(\[[^\]]+\])?\s*(STR|DEX|CON|INT|WIS|CHA)\s*\|\s*([^\|]+?)\s*\|\s*([^\|]+?)\s*\|\s*([^\|]+?)\s*\|",
    re.IGNORECASE,
)
SKILL_ENTRY_RE = re.compile(r"\[(?P<marker>[^\]]+)\]\s*(?P<name>[A-Za-z/' ]+?)\s*\.{1,}\s*(?P<value>[+-]?\d+)")
PASSIVE_RE = re.compile(r"PASSIVE\s+([A-Z ]+)\s*:\s*([^\|\n]+)", re.IGNORECASE)

CORE_LABELS = ("AC", "HP", "SPEED", "INIT", "PB")
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

    lines: list[str] = []
    in_code = False
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            lines.append(line)
            continue
        if not in_code and HEADING_RE.match(line):
            while lines and not lines[-1].strip():
                lines.pop()
            if lines:
                lines.append("")
            lines.append(line)
            lines.append("")
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _coalesce(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip()).strip()


def _code_body(text: str) -> str:
    match = CODE_BLOCK_RE.search(text or "")
    return match.group(1).strip("\n") if match else (text or "").strip()


def _strip_first_code_block(text: str) -> str:
    return CODE_BLOCK_RE.sub("", text or "", count=1).strip()


def _extract_named_section(text: str, heading: str) -> str:
    lines = (text or "").splitlines()
    out: list[str] = []
    in_section = False
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith(heading):
            in_section = True
            out.append(heading)
            continue
        if in_section and stripped.startswith("**") and not stripped.startswith(heading):
            break
        if in_section and stripped.startswith(("## ", "### ")):
            break
        if in_section and stripped:
            out.append(raw.rstrip())
    return "\n".join(out).strip()


def _extract_flexible_bold_section(text: str, section_names: tuple[str, ...]) -> str:
    lines = (text or "").splitlines()
    out: list[str] = []
    in_section = False
    normalized_targets = tuple(name.lower() for name in section_names)
    for raw in lines:
        stripped = raw.strip()
        normalized = stripped.strip("* ").strip().rstrip(":").lower()
        if any(target in normalized for target in normalized_targets):
            in_section = True
            out.append(raw.rstrip())
            continue
        if in_section and (
            stripped.startswith("**")
            or stripped.startswith("### ")
            or any(target in normalized for target in ("spell slots", "reference links", "character profile", "rules & features"))
        ):
            break
        if in_section and stripped:
            out.append(raw.rstrip())
    return "\n".join(out).strip()


def _strip_named_section(text: str, heading: str) -> str:
    lines = (text or "").splitlines()
    out: list[str] = []
    in_section = False
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith(heading):
            in_section = True
            continue
        if in_section and stripped.startswith("**") and not stripped.startswith(heading):
            in_section = False
        if in_section and stripped.startswith(("## ", "### ")):
            in_section = False
        if in_section:
            continue
        out.append(raw)
    return "\n".join(out).strip()


def _normalize_marker(marker: str | None) -> str:
    value = (marker or "").strip()
    if "◎" in value or "◉" in value:
        return "[◎]"
    if "●" in value or "•" in value:
        return "[●]"
    return "[ ]"


def _normalize_skill_name(name: str) -> str:
    normalized = re.sub(r"[^a-z]+", " ", name.lower()).strip()
    aliases = {"animal hand": "Animal Hand", "sleight hand": "Sleight Hand"}
    for skill in SKILL_ORDER:
        if normalized == re.sub(r"[^a-z]+", " ", skill.lower()).strip():
            return skill
    return aliases.get(normalized, name.strip())


def _render_profile_identity_table(draft: CharacterDraft, fallback_player_name: str | None = None) -> str:
    identity = draft.identity
    player_name = _normalize_player_name(identity.player_name, fallback_player_name) or "Unknown"
    return "\n".join(
        [
            "```",
            "[ CHARACTER LEVEL, RACE, & CLASS ]",
            "----------------------------------------",
            f"LEVEL.....: {identity.level or 'Unknown'}",
            f"RACE......: {identity.race or 'Unknown'}",
            f"CLASS.....: {identity.class_name or 'Unknown'}",
            f"SUBCLASS..: {identity.subclass or 'Unknown'}",
            f"XP........: {identity.xp or 'Unknown'}",
            f"PLAYER....: {player_name}",
            f"BACKGROUND: {identity.background or 'Unknown'}",
            f"ALIGNMENT.: {identity.alignment or 'Unknown'}",
            f"DEITY.....: {identity.deity or 'Unknown'}",
            "----------------------------------------",
            "```",
        ]
    )


def _parse_core_status_rows(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    left_rows: list[tuple[str, str]] = []
    right_rows: list[tuple[str, str]] = []
    for raw in _code_body(text).splitlines():
        line = raw.strip()
        if not line or line.startswith(("```", "-", "BUILD", "CORE STATUS", "RESOURCES & POOLS", "[")):
            continue
        if "." in line:
            parts = [part.strip() for part in re.split(r"\.{2,}", line) if part.strip()]
            if len(parts) >= 2:
                label, value = parts[0], parts[1]
            else:
                continue
        else:
            if ":" not in line:
                continue
            label, value = [part.strip() for part in line.split(":", 1)]
        if label.upper() in CORE_LABELS:
            left_rows.append((label.upper(), value))
        else:
            right_rows.append((label.upper(), value))
    dedup_left = {label: value for label, value in left_rows}
    dedup_right = {label: value for label, value in right_rows}
    return [(label, dedup_left[label]) for label in CORE_LABELS if label in dedup_left], list(dedup_right.items())


def _render_core_status_table(text: str, *, build_line: str | None = None) -> str:
    left_rows, _ = _parse_core_status_rows(text)
    if not left_rows:
        return ""
    lines = ["```"]
    if (build_line or "").strip():
        lines.extend([f"BUILD......: {build_line.strip()}", ""])
    lines.extend(["CORE STATUS", "----------------------"])
    for label, value in left_rows:
        lines.append(f"{label:<5}......... {value}")
    lines.append("```")
    return "\n".join(lines)


def _render_abilities_table(text: str) -> str:
    rows: dict[str, tuple[str, str, str, str]] = {}
    for line in _code_body(text).splitlines():
        match = ABILITY_ROW_RE.search(line)
        if not match:
            continue
        rows[match.group(2).upper()] = (
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
    lines.extend(["+---------+-------+-----+------+", "● -> Proficient", "```"])
    return "\n".join(lines)


def _render_skills_table(text: str) -> str:
    entries: dict[str, tuple[str, str]] = {}
    passives: dict[str, str] = {}
    for raw in _code_body(text).splitlines():
        for match in SKILL_ENTRY_RE.finditer(raw):
            entries[_normalize_skill_name(match.group("name"))] = (_normalize_marker(match.group("marker")), match.group("value").strip())
        for match in PASSIVE_RE.finditer(raw):
            passives[match.group(1).strip().upper()] = match.group(2).strip()
    if not entries:
        return text.strip()
    lines = ["```", "SKILLS & SENSES", "-------------------------"]
    for skill in SKILL_ORDER:
        marker, value = entries.get(skill, ("[ ]", "Unknown"))
        lines.append(f"{marker} {skill:<14} .... {value}")
    lines.extend(
        [
            "--------------------------",
            f"PASSIVE PERCEPTION: {passives.get('PERCEPTION', 'Unknown')}",
            f"PASSIVE INSIGHT: {passives.get('INSIGHT', 'Unknown')}",
            "----------------------------",
            "Legend:",
            "[ ] None",
            "[●] Proficient",
            "[◎] Expertise",
            "```",
        ]
    )
    return "\n".join(lines)


def _normalize_actions_section(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"(?<!\n)(>\s+\*\*Multiattack:)", r"\n\1", cleaned)
    cleaned = re.sub(r"(?<!\n)([*-]\s+\*\*)", r"\n\1", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _render_spellcasting_ability_excerpt(rules_text: str, actions_text: str) -> str:
    source = "\n".join(part for part in ((actions_text or "").strip(), (rules_text or "").strip()) if part)
    match = re.search(r"Spellcasting Ability:\s*([A-Za-z]+)\s*\(([^)]+)\)", source, re.IGNORECASE)
    return f"`Spellcasting Ability: {match.group(1).strip().title()} ({match.group(2).strip()})`" if match else ""


def _normalize_resource_tracking_block(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    out = ["**:battery: Resource Tracking**"]
    for raw in cleaned.splitlines():
        stripped = raw.strip()
        if not stripped or "resource tracking" in stripped.lower():
            continue
        stripped = stripped.lstrip("*- ").strip().replace("[ ]", "◯").replace("○", "◯")
        stripped = stripped.replace("** **", "").replace('""', "")
        match = re.match(r"^\*\*(.+?):\*\*\s*(.+)$", stripped)
        if match:
            name, value = match.group(1).strip(), match.group(2).strip()
        else:
            parts = stripped.split(":", 1)
            if len(parts) != 2:
                continue
            name, value = parts[0].strip("* "), parts[1].strip()
        name = re.sub(r"\*+", "", name).strip()
        value = re.sub(r"\s+", " ", value).strip().strip('"')
        value = value.replace("**", "").strip()
        value = re.sub(r"^\*+\s*", "", value)
        value = re.sub(r"\s*\*+$", "", value)
        note = ""
        if "◯" in value:
            tracker_match = re.search(r"◯(?:\s*◯)*", value)
            if tracker_match:
                tracker = tracker_match.group(0).strip()
                trailing = value[tracker_match.end():].strip()
                trailing = trailing.strip("`").strip()
                if trailing.startswith("(") and trailing.endswith(")"):
                    trailing = trailing[1:-1].strip()
                note = trailing
                value = tracker
            if note:
                value = f"{value} `{note}`"
        elif value:
            value = f"`{value.strip('`')}`"
        out.append(f"- **{name}:** {value}")
    return "\n".join(out) if len(out) > 1 else ""


def _build_resource_tracking_from_pools(core_status_text: str) -> str:
    _, right_rows = _parse_core_status_rows(core_status_text)
    if not right_rows:
        return ""
    lines = ["**:battery: Resource Tracking**"]
    for label, value in right_rows:
        cleaned = re.sub(r"\s+", " ", value).strip().replace("**", "")
        cleaned = cleaned.replace("○", "◯").replace("[ ]", "◯")
        if "◯" in cleaned:
            tracker_match = re.search(r"◯(?:\s*◯)*", cleaned)
            if tracker_match:
                tracker = tracker_match.group(0).strip()
                trailing = cleaned[tracker_match.end():].strip()
                trailing = trailing.strip("`").strip()
                if trailing.startswith("(") and trailing.endswith(")"):
                    trailing = trailing[1:-1].strip()
                lines.append(f"- **{label.title()}:** {tracker}{f' `{trailing}`' if trailing else ''}")
            else:
                lines.append(f"- **{label.title()}:** {cleaned}")
        else:
            lines.append(f"- **{label.title()}:** `{cleaned}`")
    return "\n".join(lines) if len(lines) > 1 else ""


def _build_resource_tracking_from_resource_pools(resource_pools: list[ResourcePool]) -> str:
    if not resource_pools:
        return ""
    lines = ["**:battery: Resource Tracking**"]
    for pool in resource_pools:
        name = (pool.name or "").strip()
        value = re.sub(r"\s+", " ", (pool.value or "").strip()).replace("○", "◯").replace("[ ]", "◯").replace("**", "")
        if not name or not value:
            continue
        normalized_name = name.title()
        if normalized_name.lower() == "hit dice":
            lines.append(f"- **Hit Dice:** `{value}`")
            continue
        if "◯" in value:
            tracker_match = re.search(r"◯(?:\s*◯)*", value)
            if tracker_match:
                tracker = tracker_match.group(0).strip()
                trailing = value[tracker_match.end():].strip()
                trailing = trailing.strip("`").strip()
                if trailing.startswith("(") and trailing.endswith(")"):
                    trailing = trailing[1:-1].strip()
                lines.append(f"- **{normalized_name}:** {tracker}{f' `{trailing}`' if trailing else ''}")
            else:
                lines.append(f"- **{normalized_name}:** {value}")
        else:
            lines.append(f"- **{normalized_name}:** `{value}`")
    return "\n".join(lines) if len(lines) > 1 else ""


def _normalize_player_name(value: str | None, fallback: str | None = None) -> str | None:
    candidate = (value or "").strip()
    if candidate and candidate.lower() not in {"unknown", "needs review."}:
        return candidate
    fallback_candidate = (fallback or "").strip()
    if fallback_candidate and fallback_candidate.lower() not in {"unknown", "needs review."}:
        return fallback_candidate
    return candidate or fallback_candidate or None


def _extract_summary_build(summary_text: str, fallback: str) -> str:
    match = re.search(r"BUILD\.{0,}:\**\s*(.+)", summary_text or "", re.IGNORECASE)
    if match:
        return re.sub(r"\*+", "", match.group(1)).strip()
    return re.sub(r"\*+", "", fallback).strip()


def _extract_summary_quote(summary_text: str, fallback: str | None) -> str:
    for raw in (summary_text or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith(">"):
            candidate = stripped.lstrip(">").strip()
            upper = candidate.upper()
            if (
                candidate
                and "BUILD" not in upper
                and "CORE STATUS" not in upper
                and "RACE / CLASS / SUBCLASS" not in upper
                and "CHARACTER LEVEL, RACE, & CLASS" not in upper
                and "SPELLCASTING ABILITY" not in upper
                and "REFERENCE LINKS" not in upper
            ):
                words = candidate.strip('"').strip("'").split()
                if len(words) > 20:
                    return " ".join(words[:20]).rstrip(".,;:") + "..."
                return candidate.strip('"').strip("'")
    fallback_text = (fallback or "").strip().strip('"').strip("'")
    words = fallback_text.split()
    if len(words) > 20:
        return " ".join(words[:20]).rstrip(".,;:") + "..."
    return fallback_text


def _extract_inline_spellcasting(summary_text: str) -> str:
    match = re.search(r"`?Spellcasting Ability:\s*([A-Za-z]+)\s*\(([^)]+)\)`?", summary_text or "", re.IGNORECASE)
    return f"`Spellcasting Ability: {match.group(1).strip().title()} ({match.group(2).strip()})`" if match else ""


def _extract_spellcasting_dc(spellcasting_text: str) -> str:
    match = re.search(r"\bDC\s*([+-]?\d+)\b", spellcasting_text or "", re.IGNORECASE)
    return match.group(1).strip() if match else "Unknown"


def _core_status_map(core_status_text: str) -> dict[str, str]:
    left_rows, _ = _parse_core_status_rows(core_status_text)
    return {label.upper(): value for label, value in left_rows}


def _format_speed_for_summary(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    cleaned = re.sub(r"(\d+)\s*ft\.?", r"\1ft", cleaned, flags=re.IGNORECASE)
    return cleaned or "Unknown"


def _format_hit_dice_value(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    if not cleaned:
        return "Unknown"
    slash_match = re.match(r"(\d+)\s*/\s*(\d+)\s*[\[(]?\s*(d\d+)\s*[\])]?$", cleaned, re.IGNORECASE)
    if slash_match:
        return f"{slash_match.group(1)} / {slash_match.group(2)} [{slash_match.group(3).lower()}]"
    compact = cleaned.replace(" ", "")
    dice_match = re.match(r"(\d+)d(\d+)$", compact, re.IGNORECASE)
    if dice_match:
        count = dice_match.group(1)
        return f"{count} / {count} [d{dice_match.group(2)}]"
    return cleaned


def _extract_hit_dice(resource_pools: list[ResourcePool], core_status_text: str) -> str:
    for pool in resource_pools:
        if (pool.name or "").strip().lower() == "hit dice":
            return _format_hit_dice_value(pool.value)
    _, right_rows = _parse_core_status_rows(core_status_text)
    for label, value in right_rows:
        if label.upper() == "HIT DICE":
            return _format_hit_dice_value(value)
    return "Unknown"


def _extract_hp_values(core_status_text: str) -> tuple[int | None, int | None]:
    hp_value = _core_status_map(core_status_text).get("HP", "")
    match = re.search(r"(\d+)\s*/\s*(\d+)", hp_value)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _render_hp_bar(current_hp: int | None, max_hp: int | None) -> str:
    if current_hp is None or max_hp is None or max_hp <= 0:
        return ""
    ratio = max(0.0, min(1.0, current_hp / max_hp))
    filled = round(ratio * 45)
    empty = 45 - filled
    return f"`{'█' * filled}{'░' * empty}`"


def _render_summary_combat_snapshot(
    core_status_text: str,
    resource_pools: list[ResourcePool],
    spellcasting_text: str,
) -> str:
    core = _core_status_map(core_status_text)
    ac = core.get("AC", "Unknown")
    pb = core.get("PB", "Unknown")
    speed = _format_speed_for_summary(core.get("SPEED", "Unknown"))
    dc = _extract_spellcasting_dc(spellcasting_text)
    hit_dice = _extract_hit_dice(resource_pools, core_status_text)
    current_hp, max_hp = _extract_hp_values(core_status_text)
    hp_bar = _render_hp_bar(current_hp, max_hp)

    parts = [
        f"🛡️ **AC: `{ac}`**  |  🎯 **DC: `{dc}`** | 💎 **PB: `{pb}`**  | 🏃 **SPD: `{speed}`**",
        "",
        f"🎲 **Hit Dice:** `{hit_dice}`",
    ]
    if current_hp is not None and max_hp is not None:
        parts.extend(
            [
                "",
                f"**### 💟 HP: [ {current_hp} / {max_hp} ]**",
            ]
        )
        if hp_bar:
            parts.append(hp_bar)
    return "\n".join(parts).strip()


def _build_resource_tracking(rules_text: str) -> str:
    return _normalize_resource_tracking_block(_extract_named_section(rules_text, "**🔋 Resource Tracking**"))


def _render_spell_slots_excerpt(rules_text: str) -> str:
    explicit = _extract_named_section(rules_text, "**✨ Spell Slots**")
    if explicit:
        lines = ["**:sparkles: Spell Slots**"]
        for raw in explicit.splitlines()[1:]:
            stripped = raw.strip()
            if stripped:
                stripped = stripped.lstrip("*- ").replace("[ ]", "◯").replace("○", "◯").replace("**", "")
                if ":" in stripped:
                    label, value = stripped.split(":", 1)
                    value = value.strip() or "Unknown"
                    if label.strip().lower() == "cantrips":
                        lines.append(f"**Cantrips:** *{value}*")
                    else:
                        lines.append(f"**{label.strip()}:** {value}")
        return "\n".join(lines)
    source = _extract_named_section(rules_text, "**✨ Spellbook / Known Spells**") or rules_text
    if not source:
        return ""
    counts: dict[int, int] = {}
    if re.search(r"\bCantrips?\b", source, re.IGNORECASE):
        counts[0] = -1
    for level in range(1, 10):
        match = re.search(rf"(?:Lvl|Level)\s*{level}\s*\((\d+)\s+Slots?\)", source, re.IGNORECASE)
        if match:
            counts[level] = int(match.group(1))
    if not counts:
        return ""
    lines = ["**:sparkles: Spell Slots**"]
    if 0 in counts:
        lines.append("**Cantrips:** *Unlimited*")
    for level in range(1, 10):
        if level in counts:
            lines.append(f"**Lvl {level}:** {' '.join('◯' for _ in range(counts[level]))}")
    return "\n".join(lines)


def _render_summary_resource_tracking(summary_text: str, rules_text: str) -> str:
    explicit = _normalize_resource_tracking_block(
        _extract_named_section(summary_text, "**🔋 Resource Tracking**")
        or _extract_flexible_bold_section(summary_text, ("resource tracking", "resources & pools"))
    )
    if explicit:
        return explicit
    explicit_rules = _build_resource_tracking(rules_text)
    if explicit_rules:
        return explicit_rules
    return ""


def _render_summary_spell_slots(summary_text: str, rules_text: str) -> str:
    explicit = _extract_named_section(summary_text, "**✨ Spell Slots**") or _extract_flexible_bold_section(
        summary_text,
        ("spell slots",),
    )
    if explicit:
        lines = ["**:sparkles: Spell Slots**"]
        for raw in explicit.splitlines()[1:]:
            stripped = raw.strip().lstrip("*- ").strip()
            if stripped:
                stripped = stripped.replace("**", "").replace("○", "◯").replace("[ ]", "◯")
                if ":" in stripped:
                    label, value = stripped.split(":", 1)
                    if label.strip().lower() == "cantrips":
                        stripped = f"**Cantrips:** *{value.strip()}*"
                    else:
                        stripped = f"**{label.strip()}:** {value.strip()}"
                lines.append(stripped)
        return "\n".join(lines)
    return _render_spell_slots_excerpt(rules_text)


def _render_reference_links_card(reference_text: str, links: list[ReferenceLink]) -> str:
    categories = {"Race / Class / Subclass": [], "Feats": [], "Spells": [], "Items": [], "Other": []}
    current_category = "Other"
    for line in (reference_text or "").splitlines():
        stripped = line.strip()
        if not stripped or "Reference Links" in stripped:
            continue
        if stripped.startswith("**") and stripped.endswith("**"):
            heading = stripped.strip("* ").strip().lower()
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
        match = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", stripped)
        if not match:
            continue
        label, url = match.group(1).strip(), match.group(2).strip()
        prefix = stripped.split("[", 1)[0].strip("* :-").lower()
        if any(token in prefix for token in ("race", "class", "subclass")):
            categories["Race / Class / Subclass"].append(f"* [{label}]({url})")
        elif "feat" in prefix:
            categories["Feats"].append(f"* [{label}]({url})")
        elif "spell" in prefix:
            categories["Spells"].append(f"* [{label}]({url})")
        elif "item" in prefix:
            categories["Items"].append(f"* [{label}]({url})")
        else:
            categories[current_category].append(f"* [{label}]({url})")
    if not any(categories.values()):
        for link in links:
            label, url = (link.label or "").strip(), (link.url or "").strip()
            if not label or not url:
                continue
            lowered = label.lower()
            if any(token in lowered for token in ("race", "class", "subclass")):
                categories["Race / Class / Subclass"].append(f"* [{label}]({url})")
            elif "feat" in lowered:
                categories["Feats"].append(f"* [{label}]({url})")
            elif "spell" in lowered:
                categories["Spells"].append(f"* [{label}]({url})")
            elif any(token in lowered for token in ("item", "ring", "cloak", "mantle", "rod", "circlet", "gloves", "tattoos")):
                categories["Items"].append(f"* [{label}]({url})")
            else:
                categories["Other"].append(f"* [{label}]({url})")
    parts: list[str] = []
    for title in ("Race / Class / Subclass", "Feats", "Spells", "Items", "Other"):
        if categories[title]:
            parts.append(f"**{title}**")
            parts.extend(categories[title])
    return "\n".join(parts).strip()


def _render_single_column_block(title: str, rows: list[str], width: int) -> str:
    bar = "-" * width
    return "\n".join(["```", title, bar, *rows, bar, "```"])


def _render_encumbrance_block(text: str) -> str:
    body = _code_body(text)
    def find(label: str, default: str = "Unknown") -> str:
        match = re.search(rf"{re.escape(label)}:\s*([^\n]+)", body, re.IGNORECASE)
        return match.group(1).strip() if match else default
    return _render_single_column_block(
        "[🎒 ENCUMBRANCE ]",
        [
            f"WEIGHT CARRIED: {find('WEIGHT CARRIED')}",
            f"CARRY CAPACITY: {find('CARRY CAPACITY')}",
            f"PUSH/DRAG/LIFT: {find('PUSH/DRAG/LIFT')}",
        ],
        33,
    )


def _render_currency_block(text: str) -> str:
    body = _code_body(text)
    def find(label: str, default: str = "0") -> str:
        match = re.search(rf"{label}\.*:\s*([^\n]+)", body, re.IGNORECASE)
        return match.group(1).strip() if match else default
    return _render_single_column_block(
        "[💰 CURRENCY ]",
        [
            f"COPPER............: {find('COPPER')}",
            f"SILVER............: {find('SILVER')}",
            f"GOLD..............: {find('GOLD')}",
            f"PLATINUM..........: {find('PLATINUM')}",
            f"ELECTRUM..........: {find('ELECTRUM')}",
        ],
        32,
    )


def _ensure_feats_section(rules_text: str) -> str:
    cleaned = (rules_text or "").strip()
    if not cleaned or "Feats" in cleaned:
        return cleaned
    found = [feat for feat in ("Magic Initiate", "War Caster", "Fey Touched", "Tough") if re.search(rf"\b{re.escape(feat)}\b", cleaned, re.IGNORECASE)]
    return _coalesce(cleaned, "\n".join(["**📜 Feats**", *[f"* **{feat}**" for feat in found]])) if found else cleaned


def _strip_duplicate_profile_heading(text: str, character_name: str) -> str:
    out: list[str] = []
    target = character_name.strip().lower()
    for raw in (text or "").splitlines():
        stripped = raw.strip()
        if stripped.upper().startswith("👤 CHARACTER PROFILE") or stripped.upper() in {"PROFILE CARD", "MESSAGE"} or stripped.lower() == target:
            continue
        out.append(raw)
    return "\n".join(out).strip()


def build_player_character_card(
    request: PlayerWorkspaceRequest,
    draft: CharacterDraft,
    validation: ValidationResult,
    *,
    detail_links: dict[str, str] | None = None,
) -> str:
    name = draft.identity.character_name or request.character_name or "Unnamed Character"
    draft.identity.player_name = _normalize_player_name(draft.identity.player_name, request.player_name)
    summary_text = draft.sections.summary
    concept = _extract_summary_quote(summary_text, draft.concept)
    build_line = _extract_summary_build(summary_text, draft.identity.build_line or "Needs review.")
    resource_tracking = _render_summary_resource_tracking(summary_text, draft.sections.rules)
    if not resource_tracking:
        resource_tracking = _build_resource_tracking_from_resource_pools(draft.resource_pools)
    if not resource_tracking:
        resource_tracking = _build_resource_tracking_from_pools(draft.sections.core_status)
    spell_slots = _render_summary_spell_slots(summary_text, draft.sections.rules)
    spellcasting = _extract_inline_spellcasting(summary_text) or _render_spellcasting_ability_excerpt(draft.sections.rules, draft.sections.actions)
    combat_snapshot = _render_summary_combat_snapshot(draft.sections.core_status, draft.resource_pools, spellcasting)
    parts = [f"**{name.upper()}**"]
    if concept:
        parts.append(f"> {concept}")
    parts.append(f"> **BUILD**: {build_line}")
    if spellcasting:
        spellcasting_line = re.sub(r"\*+", "", spellcasting.strip("`")).strip()
        if ":" in spellcasting_line:
            _, rhs = spellcasting_line.split(":", 1)
            spellcasting_value = rhs.strip()
        else:
            spellcasting_value = spellcasting_line
        parts.append(f"> **Spellcasting Ability**: {spellcasting_value}")
    if combat_snapshot:
        parts.append("")
        parts.append(combat_snapshot)
    if resource_tracking:
        parts.append(resource_tracking)
    if spell_slots:
        if resource_tracking:
            parts.append("")
        parts.append(spell_slots)
    return tidy_markdown_for_discord("\n".join(parts))


def render_player_workspace_cards(
    request: PlayerWorkspaceRequest,
    draft: CharacterDraft,
    validation: ValidationResult,
) -> PlayerWorkspaceCardBundle:
    character_name = draft.identity.character_name or request.character_name or "Unnamed Character"
    profile_body = _coalesce(
        f"### {character_name}",
        _strip_duplicate_profile_heading(_strip_first_code_block(draft.sections.profile), character_name),
        _render_profile_identity_table(draft, request.player_name),
        _render_core_status_table(draft.sections.core_status, build_line=draft.identity.build_line or request.character_name or "Needs review."),
    )
    skills_actions_body = _coalesce(
        "### Ability Scores & Saving Throws",
        _render_abilities_table(draft.sections.abilities),
        "### Skills & Senses",
        _render_skills_table(draft.sections.skills),
        "### Actions in Combat",
        _normalize_actions_section(draft.sections.actions),
    )
    rules_text = _ensure_feats_section(draft.sections.rules)
    rules_text = _strip_named_section(rules_text, "**🔋 Resource Tracking**")
    rules_text = _strip_named_section(rules_text, "**✨ Spell Slots**")
    rules_text = _strip_named_section(rules_text, "### 🔗 REFERENCE LINKS")
    items_body = _coalesce(
        draft.sections.items,
        _render_encumbrance_block(draft.sections.encumbrance),
        _render_currency_block(draft.sections.currency),
    )
    return PlayerWorkspaceCardBundle(
        character_card=build_player_character_card(request, draft, validation),
        profile_card=tidy_markdown_for_discord(profile_body),
        skills_actions_card=tidy_markdown_for_discord(skills_actions_body),
        rules_card=tidy_markdown_for_discord(rules_text),
        links_card=tidy_markdown_for_discord(_render_reference_links_card(draft.sections.reference_links, draft.reference_links)) or "Needs review.",
        items_card=tidy_markdown_for_discord(items_body),
        welcome_text=build_thread_welcome_text(request),
    )


def build_thread_welcome_text(request: PlayerWorkspaceRequest) -> str:
    display_name = request.character_name or "this character"
    if request.mode == "idea":
        return (
            f"**Character workspace ready for {display_name}.**\n"
            "Use this thread as the draft workspace.\n"
            "Add concept notes, references, and source material here as the build takes shape.\n"
            "Nothing here is campaign canon until someone explicitly publishes a summary."
            "**If not pinned already, I strongly advise you to pin all the relevant cards/messages for the best experience.**"
        )
    return (
        f"**Character workspace ready for {display_name}.**\n"
        "Use this thread as the draft workspace.\n"
        "Post new notes and source material here as the sheet evolves.\n"
        "Nothing here is campaign canon until someone explicitly publishes a summary."
        "**If not pinned already, I strongly advise you to pin all the relevant cards/messages for the best experience.**"

    )
