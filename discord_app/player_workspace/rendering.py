import re
from typing import Any

from .constants import CARD_TITLES, MAX_PLAYER_CARD_MESSAGE_LENGTH, MISSING_PLACEHOLDER, SKILL_LABELS, SKILL_TO_ABILITY
from .parsing import (
    _ability_score_map,
    _build_combat_section_from_source,
    _build_skills_card_from_source,
    _build_stats_section_from_source,
    _derive_hit_dice,
    _derive_proficiency_bonus,
    _derive_speed_from_build,
    _extract_ac_from_source,
    _extract_attacks_per_action,
    _extract_combat_lines,
    _extract_level_from_build,
    _extract_sheet_snapshot_values,
    _extract_source_snapshot_values,
    _parse_ability_scores,
    _parse_save_map,
    _parse_sense_map,
    _parse_skill_map,
    _proficiency_marker,
    _skills_card_is_sparse,
)
from .text import (
    _compact_name,
    _display_mode_label,
    _display_section_heading,
    _display_status_label,
    _ensure_blank_line_before_headings,
    _extract_actions_section,
    _extract_code_block_from_section,
    _extract_markdown_section,
    _format_metric_row,
    _format_single_line_code_block,
    _is_missing_placeholder,
    _looks_preformatted,
    _normalize_section_key,
    _render_player_card_message,
    _section_map,
    _split_field_blocks,
    _split_resource_label_and_value,
    _split_top_level_commas,
    _strip_markdown,
    _strip_markdown_preserve_lines,
    _tokenize_inline_values,
    _truncate_text_block,
    _wrap_tags,
    build_reference_link,
    split_player_card_body,
)


def _derive_passive_from_bonus(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(10 + int(str(value).replace("+", "")))
    except ValueError:
        return None


def _format_ability_grid(text: str) -> str | None:
    scores = _parse_ability_scores(text)
    if not scores:
        return None
    chunks = [scores[:3], scores[3:6]]
    lines: list[str] = []
    for chunk in chunks:
        if not chunk:
            continue
        pieces = [f"{abbr:<3} {score:>2} ({mod:>3})" for abbr, score, mod in chunk]
        lines.append("   ".join(pieces))
    return "```text\n" + "\n".join(lines) + "\n```" if lines else None


def _build_reference_search_section(names: list[str], *, title: str = "## 🔗 Reference Searches") -> str:
    linked_names: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in names:
        compact = _compact_name(name)
        if not compact:
            continue
        if compact.lower() in {
            "class features", "subclass features", "racial traits", "feats", "magic",
            "proficiencies", "inventory attunement", "attuned items", "notable gear",
            "companions", "currency", "encumbrance", "class features & magic",
        }:
            continue
        lowered = compact.lower()
        if lowered in seen:
            continue
        link = build_reference_link(compact)
        if not link:
            continue
        seen.add(lowered)
        linked_names.append((compact, link))
    if not linked_names:
        return ""
    lines = [title]
    for name, link in linked_names[:8]:
        lines.append(f"- **{name}:** {link}")
    return "\n".join(lines)


def _extract_snapshot_field(sheet_body: str, keys: tuple[str, ...]) -> str | None:
    sections = _section_map(sheet_body)
    for key in keys:
        value = sections.get(key)
        if value:
            return value
    return None


def _extract_ability_source_text(sheet_body: str) -> str:
    return (
        _extract_code_block_from_section(sheet_body or "", ("ability scores", "saving throws"))
        or _extract_snapshot_field(sheet_body or "", ("stats", "abilities"))
        or (sheet_body or "")
    )


def _extract_save_source_text(sheet_body: str, skills_body: str) -> str:
    return (
        _extract_code_block_from_section(sheet_body or "", ("ability scores", "saving throws"))
        or skills_body
        or sheet_body
        or ""
    )


def _extract_resource_pool_tokens(sheet_body: str) -> list[str]:
    sections = _section_map(normalize_sheet_body(sheet_body or ""))
    resource_tokens = _tokenize_inline_values(sections.get("resources", ""))
    keywords = ("ki", "lay on hands", "wild shape", "sorcery", "slots", "spell slot", "channel divinity", "rage", "superiority", "bardic", "inspiration", "charges", "points", "healing")
    selected = []
    for token in resource_tokens:
        lowered = token.lower()
        if any(keyword in lowered for keyword in keywords):
            selected.append(_strip_markdown(token))
    searchable = _strip_markdown_preserve_lines(sheet_body or "")
    fallback_patterns = (
        ("Ki Points", r"\bKi(?:\s+Points?)?\s*[:=]?\s*(\d+)\b"),
        ("Lay on Hands", r"\bLay\s+on\s+Hands\s*[:=]?\s*(\d+)\b"),
        ("Wild Shape", r"\bWild\s+Shape\s*[:=]?\s*(\d+)\b"),
        ("Channel Divinity", r"\bChannel\s+Divinity\s*[:=]?\s*(\d+)\b"),
        ("Sorcery Points", r"\bSorcery\s+Points?\s*[:=]?\s*(\d+)\b"),
    )
    selected_lower = {token.lower() for token in selected}
    for label, pattern in fallback_patterns:
        match = re.search(pattern, searchable, flags=re.IGNORECASE)
        if not match:
            continue
        token = f"{label} {match.group(1)}"
        if token.lower() not in selected_lower:
            selected.append(token)
            selected_lower.add(token.lower())
    return selected[:3]


def _build_core_status_resources_block(sheet_body: str, skills_body: str) -> str:
    snapshot = _extract_sheet_snapshot_values(sheet_body or "")
    senses = _parse_sense_map(skills_body or "")
    skills = _parse_skill_map(skills_body or "")
    resources = _extract_resource_pool_tokens(sheet_body or "")

    explicit_passive = senses.get("Passive Perception") or snapshot.get("passive")
    derived_passive = _derive_passive_from_bonus(skills.get("Perception"))
    try:
        passive_perception = str(max(value for value in [int(explicit_passive) if explicit_passive else -10000, int(derived_passive) if derived_passive else -10000] if value > -10000))
    except Exception:
        passive_perception = explicit_passive or derived_passive or "—"

    hp_value = "UNKNOWN"
    if snapshot.get("current_hp") and snapshot.get("max_hp"):
        hp_value = f"{snapshot['current_hp']} / {snapshot['max_hp']}"
    elif snapshot.get("max_hp"):
        hp_value = f"{snapshot['max_hp']} / {snapshot['max_hp']}"

    init_value = snapshot.get("initiative")
    if init_value and not str(init_value).startswith(("+", "-")) and str(init_value) != "UNKNOWN":
        init_value = f"+{init_value}"

    left_rows = [
        _format_metric_row("AC", snapshot.get("ac", "UNKNOWN")),
        _format_metric_row("HP", hp_value),
        _format_metric_row("Speed", f"{snapshot['speed']} ft" if snapshot.get("speed") else "UNKNOWN"),
        _format_metric_row("Init", init_value or "UNKNOWN"),
        _format_metric_row("PB", f"+{snapshot['pb']}" if snapshot.get("pb") else "UNKNOWN"),
    ]
    right_rows = [_format_metric_row("Hit Dice", snapshot.get("hit_dice", "UNKNOWN"))]
    for token in resources[:3]:
        label, value = _split_resource_label_and_value(token)
        right_rows.append(_format_metric_row(label, value or token))
    right_rows.append(_format_metric_row("P. Perception", passive_perception))
    row_count = max(len(left_rows), len(right_rows))
    while len(left_rows) < row_count:
        left_rows.append("")
    while len(right_rows) < row_count:
        right_rows.append("")
    lines = [
        "CORE STATUS                       RESOURCES & POOLS",
        "----------------------------      ------------------------------",
    ]
    for left, right in zip(left_rows, right_rows):
        lines.append(f"{left:<32}      {right}")
    lines.append("----------------------------      ------------------------------")
    return "```text\n" + "\n".join(lines) + "\n```"


def _format_ability_save_table(sheet_body: str, skills_body: str) -> str:
    ability_map = _ability_score_map(_extract_ability_source_text(sheet_body or ""))
    save_map = _parse_save_map(_extract_save_source_text(sheet_body or "", skills_body or ""))
    snapshot = _extract_sheet_snapshot_values(sheet_body or "")
    pb = snapshot.get("pb")
    lines = [
        "ABILITY SCORES & SAVING THROWS",
        "+---------+-------+-----+------+",
        "| ABILITY | SCORE | MOD | SAVE |",
        "+---------+-------+-----+------+",
    ]
    for abbr in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
        score, mod = ability_map.get(abbr, ("UNKNOWN", "UNKNOWN"))
        save = save_map.get(abbr) or mod
        marker = _proficiency_marker(bonus=save_map.get(abbr), ability_mod=mod, pb=pb)
        ability_label = f"[{marker if marker.strip() else ' '}] {abbr}"
        lines.append(f"| {ability_label:<7} | {score:>5} | {mod:>3} | {save:>4} |")
    lines.append("+---------+-------+-----+------+")
    lines.append("● -> Proficient    ◎ -> Expertise")
    return "```text\n" + "\n".join(lines) + "\n```"


def _format_skills_senses_table(sheet_body: str, skills_body: str) -> str:
    ability_map = _ability_score_map(_extract_ability_source_text(sheet_body or ""))
    skill_map = _parse_skill_map(skills_body or "")
    sense_map = _parse_sense_map(skills_body or "")
    snapshot = _extract_sheet_snapshot_values(sheet_body or "")
    pb = snapshot.get("pb")

    def row_for(skill_name: str) -> str:
        bonus = skill_map.get(skill_name, "UNKNOWN")
        ability = SKILL_TO_ABILITY.get(skill_name, "")
        ability_mod = ability_map.get(ability, ("", ""))[1] if ability else None
        marker = _proficiency_marker(bonus=bonus, ability_mod=ability_mod, pb=pb)
        label = skill_name.replace("Animal Handling", "Animal Hand").replace("Sleight of Hand", "Sleight/Hand")
        dots = "." * max(2, 16 - len(label))
        return f"[{marker if marker.strip() else ' '}] {label} {dots} {bonus:>3}"

    def prefer_max(explicit: str | None, derived: str | None) -> str | None:
        values = []
        for candidate in (explicit, derived):
            if not candidate:
                continue
            try:
                values.append(int(candidate))
            except ValueError:
                continue
        return str(max(values)) if values else explicit or derived

    lines = ["SKILLS & SENSES", "--------------------------------------------------"]
    for left, right in zip(SKILL_LABELS[:9], SKILL_LABELS[9:]):
        lines.append(f"{row_for(left):<28} {row_for(right)}")
    passive_perception = prefer_max(sense_map.get("Passive Perception"), _derive_passive_from_bonus(skill_map.get("Perception")))
    passive_insight = prefer_max(sense_map.get("Passive Insight"), _derive_passive_from_bonus(skill_map.get("Insight")))
    passive_investigation = prefer_max(sense_map.get("Passive Investigation"), _derive_passive_from_bonus(skill_map.get("Investigation")))
    lines.append("--------------------------------------------------")
    lines.append(" | ".join([
        f"PASSIVE PERCEPTION: {passive_perception or 'UNKNOWN'}",
        f"PASSIVE INSIGHT: {passive_insight or 'UNKNOWN'}",
        f"PASSIVE INVESTIGATION: {passive_investigation or 'UNKNOWN'}",
    ]))
    lines.append("--------------------------------------------------")
    lines.append("Legend: [ ] None  [●] Proficient  [◎] Expertise")
    return "```text\n" + "\n".join(lines) + "\n```"


def _format_combat_actions(sheet_body: str, display_name: str) -> str:
    attack_lines = _extract_combat_lines(sheet_body or "", limit=8)
    attacks_per_action = _extract_attacks_per_action(sheet_body or "")
    blocks = ["### ⚔️ ACTIONS IN COMBAT"]
    if attacks_per_action:
        blocks.append(f"> **Multiattack:** {display_name} makes `{attacks_per_action} attacks per Action`.")
    elif attack_lines:
        blocks.append("> **Table Use:** Review the attacks below for the main combat options.")
    else:
        blocks.append(f"> **Needs Review:** Add {display_name}'s primary attacks and action economy.")
    for line in attack_lines:
        compact = _strip_markdown(line)
        name, _, rest = compact.partition(":")
        if rest:
            detail = rest.strip()
            if "|" in detail:
                first, second = [piece.strip() for piece in detail.split("|", 1)]
                if "`" not in first:
                    first = f"`{first}`"
                if "`" not in second:
                    second = f"`{second}`"
                detail = f"{first} | {second}"
            blocks.append(f"- **{name.strip()}**: {detail}")
        else:
            blocks.append(f"- {compact}")
    return "\n".join(blocks)


def _extract_rule_labels(rules_body: str) -> list[str]:
    text = rules_body or ""
    labels: list[str] = []

    for pattern in (
        r"Racial Traits\s*\(([^)]+)\)",
        r"Feats?:\s*\*?\*?([^:\n*]+)",
        r"Class Features\s*\(([^)]+)\)",
        r"Subclass Features\s*\(([^)]+)\)",
        r"\*\*🥋\s*([^*(\n]+)",
        r"\*\*👊\s*([^*(\n]+)",
        r"\*\*🌿\s*([^*(\n]+)",
        r"\*\*🌟\s*([^*(\n]+)",
    ):
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            candidate = _compact_name(match.group(1))
            if candidate:
                labels.append(candidate)

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("* **"):
            continue
        feature_name = stripped.split("**", 2)[1].strip()
        if any(word in feature_name.lower() for word in ("trait", "feature", "magic", "proficien", "language")):
            continue
        labels.append(_compact_name(feature_name))

    deduped: list[str] = []
    seen: set[str] = set()
    for label in labels:
        lowered = label.lower()
        if not label or lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(label)
    return deduped[:8]


def _extract_item_names(items_body: str) -> list[str]:
    names = []
    for label, value in _split_field_blocks(items_body):
        compact_label = _compact_name(label)
        if compact_label and compact_label.lower() not in {
            "inventory attunement", "attuned items", "notable gear", "companions",
            "encumbrance", "currency",
        }:
            names.append(_compact_name(label))
        if value:
            for line in value.splitlines():
                cleaned = _compact_name(re.sub(r"^\d+\.\s*", "", line.lstrip("• ").strip()))
                if cleaned:
                    names.append(cleaned)
    deduped = []
    seen = set()
    for name in names:
        lowered = name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(name)
    return deduped[:8]


def _build_quick_skills_summary(skills_body: str) -> str:
    skill_map = _parse_skill_map(skills_body or "")
    ranked = []
    for skill_name, bonus in skill_map.items():
        try:
            ranked.append((int(str(bonus).replace("+", "")), skill_name, bonus))
        except ValueError:
            continue
    ranked.sort(key=lambda item: (-item[0], item[1]))
    top = [f"{name} {bonus}" for _, name, bonus in ranked[:6]]
    senses = _parse_sense_map(skills_body or "")
    if senses.get("Passive Perception"):
        top.append(f"Passive Perception {senses['Passive Perception']}")
    return " • ".join(top) if top else MISSING_PLACEHOLDER


def _build_highlight_block(profile_body: str, concept: str | None = None) -> str:
    bullet_matches = re.findall(r"(?m)^[*-]\s+(.*)$", profile_body or "")
    normalized_bullets = []
    for bullet in bullet_matches:
        cleaned = _strip_markdown(bullet)
        if not cleaned:
            continue
        if ":" in cleaned:
            label, value = cleaned.split(":", 1)
            normalized_bullets.append(f"• {label.strip()}: {_truncate_text_block(value.strip(), 130)}")
        else:
            normalized_bullets.append(f"• {_truncate_text_block(cleaned, 130)}")
    if normalized_bullets:
        return "\n".join(normalized_bullets[:3])
    if _looks_preformatted(profile_body):
        stripped = re.sub(r"```(?:\w+)?\n.*?```", "", profile_body or "", flags=re.DOTALL)
        bullet_lines = []
        for raw_line in stripped.splitlines():
            compact = raw_line.strip()
            if not compact or compact.startswith("##") or compact.startswith("###") or compact.startswith(">"):
                continue
            if compact.startswith(("* ", "- ")):
                bullet_lines.append(f"• {_truncate_text_block(_strip_markdown(compact[2:]), 160)}")
        if bullet_lines:
            return "\n".join(bullet_lines[:3])
    sections = _section_map(profile_body)
    highlights = []
    for key in ("appearance", "personality", "backstory", "roleplay notes", "allies companions"):
        value = sections.get(key)
        if value:
            highlights.append(f"• {_truncate_text_block(value, 130)}")
        if len(highlights) >= 3:
            break
    if highlights:
        return "\n".join(highlights)
    if concept:
        return f"• {_truncate_text_block(concept, 180)}"
    return "• Add appearance, personality, and roleplay notes."


def _compose_sheet_body(*, stats: str | None, vitals: str | None, saves: str | None, skills: str | None, senses: str | None, combat: str | None, resources: str | None) -> str:
    sections = []
    if stats:
        sections.append(f"Stats: {stats}")
    if vitals:
        sections.append(f"Vitals: {vitals}")
    if saves:
        sections.append(f"Saves: {saves}")
    if skills:
        sections.append(f"Skills: {skills}")
    if senses:
        sections.append(f"Senses: {senses}")
    if combat:
        sections.append("Combat:\n" + combat)
    if resources:
        sections.append(f"Resources: {resources}")
    return "\n\n".join(section.strip() for section in sections if section and section.strip()).strip()


def normalize_sheet_body(body: str) -> str:
    sections = _section_map(body)
    stats = sections.get("stats") or sections.get("ability scores") or sections.get("abilities")
    vitals = sections.get("vitals") or sections.get("defenses") or sections.get("core")
    saves = sections.get("saves") or sections.get("saving throws")
    skills = sections.get("skills")
    senses = sections.get("senses")
    combat = sections.get("combat")
    resources = sections.get("resources") or sections.get("combat and resources")

    def clean_inline(value: str | None) -> str | None:
        if not value:
            return None
        pieces = _tokenize_inline_values(_strip_markdown(value))
        return " | ".join(pieces) if pieces else _strip_markdown(value)

    def clean_multiline(value: str | None) -> str | None:
        if not value:
            return None
        lines = [line.strip() for line in _strip_markdown_preserve_lines(value).splitlines() if line.strip()]
        if not lines:
            return None
        return "\n".join(line if line.startswith("•") else f"• {line.lstrip('-* ')}" for line in lines)

    return _compose_sheet_body(
        stats=clean_inline(stats),
        vitals=clean_inline(vitals),
        saves=clean_inline(saves),
        skills=clean_inline(skills),
        senses=clean_inline(senses),
        combat=clean_multiline(combat),
        resources=clean_inline(resources),
    ) or (body or "").strip() or MISSING_PLACEHOLDER


def build_skills_card_body(sheet_body: str) -> str:
    sections = _section_map(normalize_sheet_body(sheet_body))
    skills = sections.get("skills")
    senses = sections.get("senses")
    blocks = []
    if skills:
        blocks.append(f"Skills: {skills}")
    if senses:
        blocks.append(f"Senses: {senses}")
    return "\n\n".join(blocks).strip() or f"Skills: {MISSING_PLACEHOLDER}\n\nSenses: {MISSING_PLACEHOLDER}"


def build_items_card_body(body: str) -> str:
    cleaned = (body or "").strip()
    if not cleaned:
        return f"Magic Items\n• {MISSING_PLACEHOLDER}"
    return cleaned


def _format_sheet_dashboard(body: str) -> str:
    if _looks_preformatted(body):
        return body.strip()
    sections = _section_map(body)
    display_name = sections.get("character") or "This character"
    blocks = [
        "## Core Status",
        _build_core_status_resources_block(body, build_skills_card_body(body)),
        "## Ability Scores & Saving Throws",
        _format_ability_save_table(body, build_skills_card_body(body)),
    ]
    combat_actions = _format_combat_actions(body, display_name)
    if combat_actions:
        blocks.extend(["", combat_actions])
    resources_text = sections.get("resources") or sections.get("combat and resources")
    if resources_text:
        blocks.extend(["", "## Resources", "\n".join(f"- {item}" for item in _tokenize_inline_values(resources_text))])
    return "\n".join(block for block in blocks if block).strip() or body.strip() or MISSING_PLACEHOLDER


def _format_profile_body(body: str) -> str:
    if _looks_preformatted(body):
        return body.strip()
    formatted = []
    for label, value in _split_field_blocks(body):
        if label and value:
            formatted.append(f"{_display_section_heading(label)}\n{value}")
        elif label:
            formatted.append(_display_section_heading(label))
        elif value:
            formatted.append(value)
    return "\n\n".join(formatted).strip() or body.strip() or MISSING_PLACEHOLDER


def _format_rules_body(body: str) -> str:
    if _looks_preformatted(body):
        rendered = body.strip()
        if "dndbeyond.com/search" in rendered.lower():
            return rendered
        section = _build_reference_search_section(_extract_rule_labels(rendered))
        return f"{rendered}\n\n{section}".strip() if section else rendered
    formatted = []
    for label, value in _split_field_blocks(body):
        if label and value:
            if "\n" in value:
                lines = [line.strip() for line in value.splitlines() if line.strip()]
                bullet_lines = [line if line.startswith("•") else f"• {line.lstrip('-* ')}" for line in lines]
                formatted.append(f"{_display_section_heading(label)}\n" + "\n".join(bullet_lines))
            else:
                normalized_label = _normalize_section_key(label)
                pieces = _split_top_level_commas(value) if (any(keyword in normalized_label for keyword in ("magic", "spell")) or "," in value or any(keyword in normalized_label for keyword in ("traits", "features", "feats", "proficiencies", "languages", "limited magic", "subclass", "class"))) else _tokenize_inline_values(value)
                if len(pieces) > 1:
                    formatted.append(f"{_display_section_heading(label)}\n" + "\n".join(f"• {piece}" for piece in pieces))
                else:
                    formatted.append(f"{_display_section_heading(label)}\n• {value}")
        elif label:
            formatted.append(_display_section_heading(label))
        elif value:
            formatted.append(value)
    rendered = "\n\n".join(formatted).strip() or body.strip() or MISSING_PLACEHOLDER
    section = _build_reference_search_section(_extract_rule_labels(rendered))
    return f"{rendered}\n\n{section}".strip() if section else rendered


def _format_items_body(body: str) -> str:
    if _looks_preformatted(body):
        rendered = body.strip()
        if "dndbeyond.com/search" in rendered.lower():
            return rendered
        section = _build_reference_search_section(_extract_item_names(rendered), title="## 🔗 Item Reference Searches")
        return f"{rendered}\n\n{section}".strip() if section else rendered
    formatted = []
    for label, value in _split_field_blocks(body):
        if label and value:
            lines = [line.strip() for line in value.splitlines() if line.strip()]
            if not lines:
                formatted.append(f"{_display_section_heading(label)}\n{MISSING_PLACEHOLDER}")
                continue
            bullet_lines = [line if line.startswith("•") else f"• {line.lstrip('-* ')}" for line in lines]
            formatted.append(f"{_display_section_heading(label)}\n" + "\n".join(bullet_lines))
        elif label:
            formatted.append(_display_section_heading(label))
        elif value:
            formatted.append(value)
    rendered = "\n\n".join(formatted).strip() or body.strip() or MISSING_PLACEHOLDER
    section = _build_reference_search_section(_extract_item_names(rendered), title="## 🔗 Item Reference Searches")
    return f"{rendered}\n\n{section}".strip() if section else rendered


def _format_workspace_body(body: str) -> str:
    if _looks_preformatted(body):
        return body.strip()
    sections = _section_map(body)
    formatted = []
    summary_lines = []
    for key, label in (("status", "Status"), ("mode", "Mode"), ("public context", "Public Context"), ("dm notes", "DM Notes")):
        value = sections.get(key)
        if value:
            summary_lines.append(f"**{label}**\n{value}")
    if summary_lines:
        formatted.append("\n\n".join(summary_lines))
    source = sections.get("source")
    if source:
        formatted.append(f"**Source Summary**\n{source}")
    latest_source = sections.get("latest source post")
    if latest_source:
        formatted.append(f"**Latest Source Post**\n{latest_source}")
    needs_review = sections.get("needs review")
    if needs_review:
        lines = [line.strip() for line in needs_review.splitlines() if line.strip()]
        bullet_lines = [line if line.startswith("•") else f"• {line.lstrip('-* ')}" for line in lines]
        formatted.append("**Needs Review**\n" + "\n".join(bullet_lines))
    return "\n\n".join(formatted).strip() or body.strip() or MISSING_PLACEHOLDER


def format_player_card_body(*, card_key: str, body: str) -> str:
    if card_key == "sheet_card":
        return _ensure_blank_line_before_headings(_format_sheet_dashboard(body))
    if card_key == "skills_card":
        return _ensure_blank_line_before_headings(_format_skills_body(body))
    if card_key == "profile_card":
        return _ensure_blank_line_before_headings(_format_profile_body(body))
    if card_key == "rules_card":
        return _ensure_blank_line_before_headings(_format_rules_body(body))
    if card_key == "items_card":
        return _ensure_blank_line_before_headings(_format_items_body(body))
    if card_key == "workspace_card":
        return _ensure_blank_line_before_headings(_format_workspace_body(body))
    return _ensure_blank_line_before_headings((body or "").strip() or MISSING_PLACEHOLDER)


def build_character_card_body(*, display_name: str, player_name: str | None, mode: str, status: str, build_line: str | None, concept: str | None, source_summary: str | None, missing_info: list[str], card_links: dict[str, str], public_publish_state: str = "not published", dm_publish_state: str = "not published", sheet_body: str | None = None, skills_body: str | None = None, profile_body: str | None = None) -> str:
    del mode, status, source_summary, card_links, public_publish_state, dm_publish_state
    if _looks_preformatted(sheet_body or ""):
        core_block = _extract_code_block_from_section(sheet_body or "", ("core status", "core status & resources")) or _build_core_status_resources_block(sheet_body or "", skills_body or "")
        ability_block = _extract_code_block_from_section(sheet_body or "", ("ability scores", "saving throws")) or _format_ability_save_table(sheet_body or "", skills_body or "")
        combat_block = _extract_markdown_section(sheet_body or "", ("actions in combat",), include_heading=True) or _extract_actions_section(sheet_body or "") or _format_combat_actions(sheet_body or "", display_name)
    else:
        core_block = _build_core_status_resources_block(sheet_body or "", skills_body or "")
        ability_block = _format_ability_save_table(sheet_body or "", skills_body or "")
        combat_block = _format_combat_actions(sheet_body or "", display_name)
    if _looks_preformatted(skills_body or ""):
        skills_block = _extract_code_block_from_section(skills_body or "", ("skills & senses", "skills", "senses")) or skills_body or MISSING_PLACEHOLDER
    else:
        skills_block = _format_skills_senses_table(sheet_body or "", skills_body or "")
    lines = [
        f"## {display_name}",
        f"> {concept}" if concept else f"> {MISSING_PLACEHOLDER}",
        "",
        f"**Player:** {player_name or MISSING_PLACEHOLDER}",
        "",
        "**Build**",
        _format_single_line_code_block(build_line or MISSING_PLACEHOLDER),
        "",
        "## Core Status & Resources",
        core_block,
        "",
        "## Ability Scores & Saving Throws",
        ability_block,
        "",
        "## Skills & Senses",
        skills_block,
        "",
        combat_block,
        "",
        "## Signature / Highlights",
        _build_highlight_block(profile_body or "", concept),
    ]
    if missing_info:
        lines.extend(["", "## Needs Review"])
        lines.extend(f"- {item}" for item in missing_info[:8])
    return _ensure_blank_line_before_headings("\n".join(part for part in lines if part).strip())


def build_workspace_status_body(*, mode: str, status: str, source_summary: str | None, missing_info: list[str], public_publish_state: str = "not published", dm_publish_state: str = "not published", source_jump_url: str | None = None) -> str:
    lines = [
        f"Status: `{_display_status_label(status)}`",
        f"Mode: `{_display_mode_label(mode)}`",
        f"Public Context: `{public_publish_state}`",
        f"DM Notes: `{dm_publish_state}`",
    ]
    if source_summary:
        lines.extend(["", "Source", source_summary])
    if source_jump_url:
        lines.extend(["", "Latest Source Post", source_jump_url])
    if missing_info:
        lines.extend(["", "Needs Review"])
        lines.extend(f"• {item}" for item in missing_info[:10])
    return "\n".join(lines).strip()


def build_player_card_messages(*, entity_key: str, display_name: str, card_key: str, body: str) -> list[str]:
    del entity_key, display_name
    rendered_body = format_player_card_body(card_key=card_key, body=body)
    parts = split_player_card_body(body=rendered_body, card_title=CARD_TITLES.get(card_key, card_key.replace("_", " ").title()))
    title = CARD_TITLES.get(card_key, card_key.replace("_", " ").title())
    return [_render_player_card_message(title=title, part=part, part_index=index, part_count=len(parts)) for index, part in enumerate(parts, start=1)]


def _format_skills_body(body: str) -> str:
    if _looks_preformatted(body):
        return body.strip()
    formatted = _format_skills_senses_table("", body)
    return formatted.strip() or body.strip() or MISSING_PLACEHOLDER


def _split_rules_and_items(rules_body: str, items_body: str | None) -> tuple[str, str]:
    itemish_words = ("item", "items", "magic items", "gear", "inventory", "loadout", "companions", "allies")
    retained_rules = []
    extracted_items = []
    for label, value in _split_field_blocks(rules_body or ""):
        normalized = _normalize_section_key(label)
        target_list = extracted_items if normalized and any(word in normalized for word in itemish_words) else retained_rules
        if label and value:
            target_list.append(f"{label}: {value}")
        elif label:
            target_list.append(label)
        elif value:
            target_list.append(value)
    final_rules = "\n\n".join(block.strip() for block in retained_rules if block.strip()).strip()
    final_items = (items_body or "").strip()
    if not final_items and extracted_items:
        final_items = "\n\n".join(block.strip() for block in extracted_items if block.strip()).strip()
    return final_rules or (rules_body or "").strip(), build_items_card_body(final_items)


def enrich_player_workspace_draft(*, draft: dict[str, Any], source_material: str | None) -> dict[str, Any]:
    updated = dict(draft)
    build_line = str(updated.get("build_line") or "")
    level = _extract_level_from_build(build_line)
    source = source_material or ""
    rules_body, items_body = _split_rules_and_items(str(updated.get("rules_card") or ""), str(updated.get("items_card") or ""))
    updated["rules_card"] = rules_body
    updated["items_card"] = items_body
    raw_sheet_body = str(updated.get("sheet_card") or MISSING_PLACEHOLDER)
    preformatted_sheet = _looks_preformatted(raw_sheet_body)
    sheet_body = raw_sheet_body if preformatted_sheet else normalize_sheet_body(raw_sheet_body)
    snapshot = _extract_sheet_snapshot_values(sheet_body)
    source_snapshot = _extract_source_snapshot_values(source)
    for key in ("ac", "max_hp", "hit_dice", "speed", "initiative", "passive"):
        if key not in snapshot and source_snapshot.get(key):
            snapshot[key] = source_snapshot[key]
    if "ac" not in snapshot:
        inferred_ac = _extract_ac_from_source(source)
        if inferred_ac:
            snapshot["ac"] = inferred_ac
    if "pb" not in snapshot:
        inferred_pb = _derive_proficiency_bonus(level)
        if inferred_pb:
            snapshot["pb"] = inferred_pb
    if "speed" not in snapshot:
        inferred_speed = _derive_speed_from_build(build_line, source)
        if inferred_speed:
            snapshot["speed"] = inferred_speed
    if "hit_dice" not in snapshot:
        inferred_hd = _derive_hit_dice(build_line, level)
        if inferred_hd:
            snapshot["hit_dice"] = inferred_hd
    if "attacks_per_action" not in snapshot:
        inferred_attacks = _extract_attacks_per_action(source)
        if inferred_attacks:
            snapshot["attacks_per_action"] = inferred_attacks
    sections = _section_map(sheet_body)
    source_stats_section = _build_stats_section_from_source(source)
    if source_stats_section:
        source_sections = _section_map(source_stats_section)
        if not sections.get("stats") or "unknown" in (sections.get("stats") or "").lower():
            sections["stats"] = source_sections.get("stats", sections.get("stats"))
        if not sections.get("saves") or "unknown" in (sections.get("saves") or "").lower():
            sections["saves"] = source_sections.get("saves", sections.get("saves"))

    if not sections.get("combat"):
        sections["combat"] = _build_combat_section_from_source(source) or sections.get("combat")

    resources_text = sections.get("resources")
    if not resources_text:
        resource_tokens: list[str] = []
        resource_search = "\n".join(filter(None, [str(updated.get("rules_card") or ""), source]))
        for label, pattern in (
            ("Ki Points", r"\bKi(?:\s+Points?)?\s*[:=]?\s*(\d+)\b"),
            ("Lay on Hands", r"\bLay\s+on\s+Hands\s*[:=]?\s*(\d+)\b"),
            ("Wild Shape", r"\bWild\s+Shape\s*[:=]?\s*(\d+)\b"),
            ("Channel Divinity", r"\bChannel\s+Divinity\s*[:=]?\s*(\d+)\b"),
            ("Sorcery Points", r"\bSorcery\s+Points?\s*[:=]?\s*(\d+)\b"),
        ):
            match = re.search(pattern, resource_search, flags=re.IGNORECASE)
            if match:
                resource_tokens.append(f"{label} {match.group(1)}")
        resources_text = " | ".join(resource_tokens) if resource_tokens else sections.get("resources")
    if preformatted_sheet:
        updated["sheet_card"] = raw_sheet_body
    else:
        vitals_tokens = []
        if snapshot.get("ac"):
            vitals_tokens.append(f"AC {snapshot['ac']}")
        if snapshot.get("current_hp") and snapshot.get("max_hp"):
            vitals_tokens.append(f"HP {snapshot['current_hp']}/{snapshot['max_hp']}")
        elif snapshot.get("max_hp"):
            vitals_tokens.append(f"HP {snapshot['max_hp']}")
        if snapshot.get("hit_dice"):
            vitals_tokens.append(f"Hit Dice {snapshot['hit_dice']}")
        if snapshot.get("pb"):
            vitals_tokens.append(f"PB +{snapshot['pb']}")
        if snapshot.get("speed"):
            vitals_tokens.append(f"Speed {snapshot['speed']} ft")
        if snapshot.get("initiative"):
            vitals_tokens.append(f"Init {snapshot['initiative']}")
        if snapshot.get("passive"):
            vitals_tokens.append(f"Passive {snapshot['passive']}")
        if snapshot.get("attacks_per_action"):
            vitals_tokens.append(f"Atk/Action {snapshot['attacks_per_action']}")
        updated["sheet_card"] = _compose_sheet_body(
            stats=sections.get("stats"),
            vitals=" | ".join(vitals_tokens) if vitals_tokens else sections.get("vitals"),
            saves=sections.get("saves"),
            skills=sections.get("skills"),
            senses=sections.get("senses"),
            combat=sections.get("combat"),
            resources=resources_text,
        ) or sheet_body
    existing_skills_card = str(updated.get("skills_card") or "").strip()
    source_skills_card = _build_skills_card_from_source(source)
    if not existing_skills_card or _skills_card_is_sparse(existing_skills_card):
        updated["skills_card"] = source_skills_card or build_skills_card_body(updated["sheet_card"])
    else:
        updated["skills_card"] = existing_skills_card
    updated["items_card"] = build_items_card_body(updated.get("items_card") or "")
    missing = list(updated.get("missing_info", []))
    resolved_terms = []
    if snapshot.get("ac"):
        resolved_terms.extend(["ac", "armor class"])
    if snapshot.get("pb"):
        resolved_terms.extend(["pb", "proficiency"])
    if snapshot.get("speed"):
        resolved_terms.append("speed")
    if snapshot.get("hit_dice"):
        resolved_terms.extend(["hit dice", "hd"])
    if resolved_terms:
        updated["missing_info"] = [item for item in missing if not any(term in item.lower() for term in resolved_terms)]
    return updated


def apply_sheet_stat_updates(body: str, updates: dict[str, str]) -> str:
    normalized = normalize_sheet_body(body)
    sections = _section_map(normalized)
    snapshot = _extract_sheet_snapshot_values(normalized)
    snapshot.update({key: value for key, value in updates.items() if value})
    vitals_tokens = []
    if snapshot.get("ac"):
        vitals_tokens.append(f"AC {snapshot['ac']}")
    if snapshot.get("current_hp") and snapshot.get("max_hp"):
        vitals_tokens.append(f"HP {snapshot['current_hp']}/{snapshot['max_hp']}")
    elif snapshot.get("max_hp"):
        vitals_tokens.append(f"HP {snapshot['max_hp']}")
    if snapshot.get("hit_dice"):
        vitals_tokens.append(f"Hit Dice {snapshot['hit_dice']}")
    if snapshot.get("pb"):
        vitals_tokens.append(f"PB +{snapshot['pb']}")
    if snapshot.get("speed"):
        vitals_tokens.append(f"Speed {snapshot['speed']} ft")
    if snapshot.get("initiative"):
        vitals_tokens.append(f"Init {snapshot['initiative']}")
    if snapshot.get("passive"):
        vitals_tokens.append(f"Passive {snapshot['passive']}")
    return _compose_sheet_body(
        stats=sections.get("stats"),
        vitals=" | ".join(vitals_tokens) if vitals_tokens else sections.get("vitals"),
        saves=sections.get("saves"),
        skills=sections.get("skills"),
        senses=sections.get("senses"),
        combat=sections.get("combat"),
        resources=sections.get("resources"),
    ) or normalized


def apply_workspace_updates(body: str, updates: dict[str, str]) -> str:
    sections = _section_map(body)
    needs_review = sections.get("needs review", "")
    if needs_review:
        lines = [line.strip() for line in needs_review.splitlines() if line.strip()]
        filtered = []
        for line in lines:
            lowered = line.lower()
            if updates.get("ac") and ("ac" in lowered or "armor class" in lowered):
                continue
            if updates.get("pb") and ("pb" in lowered or "proficiency" in lowered):
                continue
            if updates.get("speed") and "speed" in lowered:
                continue
            if updates.get("hit_dice") and ("hit dice" in lowered or "hd" in lowered):
                continue
            if updates.get("max_hp") and "hp" in lowered:
                continue
            filtered.append(line if line.startswith("•") else f"• {line.lstrip('-* ')}")
        sections["needs review"] = "\n".join(filtered)
    rebuilt = []
    for key in ("status", "mode", "public context", "dm notes"):
        value = sections.get(key)
        if value:
            rebuilt.append(f"{key.title()}: {value}")
    if sections.get("source summary") or sections.get("source"):
        rebuilt.append(f"\nSource Summary\n{sections.get('source summary') or sections.get('source')}")
    if sections.get("latest source post"):
        rebuilt.append(f"\nLatest Source Post\n{sections['latest source post']}")
    if sections.get("needs review"):
        rebuilt.append(f"\nNeeds Review\n{sections['needs review']}")
    return "\n".join(block.strip() for block in rebuilt if block.strip()).strip() or body
