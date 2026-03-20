import re

from .constants import ABILITY_NAMES, ABILITY_ORDER, BASE_SPEEDS, CLASS_HIT_DIE_SIDES, SAVE_LABELS, SKILL_LABELS, SKILL_TO_ABILITY
from .text import (
    _extract_pdf_page_text,
    _normalize_bonus_token,
    _section_map,
    _strip_markdown,
    _strip_markdown_preserve_lines,
    _tokenize_inline_values,
)


def _skills_card_is_sparse(skills_card: str) -> bool:
    skills = str(skills_card or "").lower()
    if not skills.strip() or "pending confirmation" in skills or "needs review." == skills.strip():
        return True
    if "skills" not in skills and "acrobatics" not in skills:
        return True
    if not any(skill_name in skills for skill_name in ("acrobatics", "perception", "insight", "stealth", "arcana", "survival", "investigation")):
        return True
    return False


def _parse_ability_scores(text: str) -> list[tuple[str, str, str]]:
    cleaned = _strip_markdown(text or "")
    inline = re.findall(r"\b(STR|DEX|CON|INT|WIS|CHA)\s*:?\s*(\d+)\s*\(([+-]\d+)\)", cleaned)
    if inline:
        return inline
    table_matches = re.findall(
        r"\|\s*(?:\[[^\]]*\]\s*)?(STR|DEX|CON|INT|WIS|CHA)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
        cleaned,
        flags=re.IGNORECASE,
    )
    return [(abbr.upper(), score.strip(), mod.strip()) for abbr, score, mod, _save in table_matches]


def _ability_score_map(text: str) -> dict[str, tuple[str, str]]:
    return {abbr: (score, mod) for abbr, score, mod in _parse_ability_scores(text)}


def _extract_ability_map_from_source(source_text: str) -> dict[str, tuple[str, str]]:
    text = _strip_markdown_preserve_lines(source_text or "")
    found: dict[str, tuple[str, str]] = {}
    label_to_abbr = {name.lower(): abbr for abbr, name in ABILITY_NAMES.items()}
    for label, abbr in label_to_abbr.items():
        patterns = (
            rf"([+\-]?\d+)\s+{re.escape(label)}\s+(\d+)\b",
            rf"{re.escape(label)}\s+(\d+)\s+([+\-]?\d+)\b",
            rf"{re.escape(label)}\s*[:=]?\s*(\d+)\s*\(([+\-]?\d+)\)",
            rf"{re.escape(label)}\s*[:=]?\s*([+\-]?\d+)\s*\((\d+)\)",
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            first, second = match.group(1), match.group(2)
            values = [first, second]
            score = next((value for value in values if re.fullmatch(r"\d+", value) and 1 <= int(value) <= 30), None)
            mod = next((value for value in values if re.fullmatch(r"[+\-]?\d+", value) and -10 <= int(value) <= 10 and value != score), None)
            if score:
                if not mod:
                    mod_val = (int(score) - 10) // 2
                    mod = f"{mod_val:+d}"
                else:
                    mod = _normalize_bonus_token(mod)
                found[abbr] = (score, mod)
                break
    return found


def _parse_labeled_bonus_map(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in _tokenize_inline_values(_strip_markdown(value)):
        match = re.match(r"(.+?)\s+([+-]?\d+)$", token.strip())
        if not match:
            continue
        result[match.group(1).strip()] = _normalize_bonus_token(match.group(2))
    return result


def _parse_save_map(skills_body: str) -> dict[str, str]:
    sections = _section_map(skills_body)
    labeled = _parse_labeled_bonus_map(sections.get("saving throws", ""))
    normalized: dict[str, str] = {}
    for label, bonus in labeled.items():
        compact = label.strip().upper()
        for abbr in ABILITY_ORDER:
            if compact == abbr or compact.startswith(ABILITY_NAMES[abbr].upper()):
                normalized[abbr] = bonus
                break
    table_matches = re.findall(
        r"\|\s*(?:\[[^\]]*\]\s*)?(STR|DEX|CON|INT|WIS|CHA)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
        _strip_markdown(skills_body or ""),
        flags=re.IGNORECASE,
    )
    for abbr, _score, _mod, save in table_matches:
        normalized[abbr.upper()] = save.strip()
    return normalized


def _extract_save_map_from_source(source_text: str) -> dict[str, str]:
    raw_map = _extract_named_bonus_map(source_text or "", SAVE_LABELS)
    normalized: dict[str, str] = {}
    for label, bonus in raw_map.items():
        normalized[label] = bonus
    return normalized


def _parse_skill_map(skills_body: str) -> dict[str, str]:
    sections = _section_map(skills_body)
    labeled = _parse_labeled_bonus_map(sections.get("skills", ""))
    normalized: dict[str, str] = {label.strip(): bonus for label, bonus in labeled.items()}
    aliases = {"Animal Hand": "Animal Handling", "Sleight/Hand": "Sleight of Hand"}
    label_pattern = "|".join(re.escape(label) for label in sorted([*SKILL_LABELS, *aliases.keys()], key=len, reverse=True))
    for match in re.finditer(
        rf"\[(?P<marker>[^\]]*)\]\s*(?P<label>{label_pattern})\s*\.{{1,}}\s*(?P<bonus>[+\-]?\d+|UNKNOWN)",
        _strip_markdown(skills_body or ""),
        flags=re.IGNORECASE,
    ):
        label = match.group("label").strip()
        normalized[aliases.get(label, label)] = _normalize_bonus_token(match.group("bonus"))
    return normalized


def _parse_sense_map(skills_body: str) -> dict[str, str]:
    sections = _section_map(skills_body)
    labeled = _parse_labeled_bonus_map(sections.get("senses", ""))
    senses: dict[str, str] = {label: value.lstrip("+") for label, value in labeled.items()}
    cleaned = _strip_markdown(skills_body or "")
    for label in ("Passive Perception", "Passive Insight", "Passive Investigation"):
        pattern = re.escape(label).replace(r"\ ", r"\s+") + r"[\s:.|]+(\d+|UNKNOWN)"
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            senses[label] = match.group(1)
    return senses


def _proficiency_marker(*, bonus: str | None, ability_mod: str | None, pb: str | None) -> str:
    if not bonus or not ability_mod or not pb:
        return " "
    try:
        bonus_val = int(str(bonus).replace("+", ""))
        mod_val = int(str(ability_mod).replace("+", ""))
        pb_val = int(str(pb).replace("+", ""))
    except ValueError:
        return " "
    delta = bonus_val - mod_val
    if delta >= pb_val * 2:
        return "◎"
    if delta >= pb_val:
        return "●"
    return " "


def _extract_named_bonus_map(source_text: str, labels: tuple[str, ...] | tuple[tuple[str, str], ...]) -> dict[str, str]:
    text = (source_text or "").replace("−", "-").replace("–", "-").replace("—", "-")
    found: dict[str, str] = {}
    for item in labels:
        if isinstance(item, tuple):
            label, output_label = item
        else:
            label, output_label = item, item
        escaped = re.escape(label)
        patterns = (
            rf"([+\-]?\d+)\s*{escaped}\b",
            rf"{escaped}\s*[:=]?\s*([+\-]?\d+)\b",
            rf"{escaped}\s*\(([-+]?\d+)\)",
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                found[output_label] = _normalize_bonus_token(match.group(1))
                break
    return found


def _extract_passive_senses_from_source(source_text: str) -> dict[str, str]:
    text = (source_text or "").replace("−", "-").replace("–", "-").replace("—", "-")
    extracted: dict[str, str] = {}
    patterns = {
        "Passive Perception": (r"Passive\s+Perception\s*[:=]?\s*(\d+)\b", r"Perception\s*\((\d+)\)"),
        "Passive Investigation": (r"Passive\s+Investigation\s*[:=]?\s*(\d+)\b", r"Investigation\s*\((\d+)\)"),
        "Passive Insight": (r"Passive\s+Insight\s*[:=]?\s*(\d+)\b", r"Insight\s*\((\d+)\)"),
    }
    for label, options in patterns.items():
        for pattern in options:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                extracted[label] = match.group(1)
                break
    return extracted


def _build_skills_card_from_source(source_material: str) -> str | None:
    source_text = source_material or ""
    first_page = _extract_pdf_page_text(source_text, 1)
    searchable = "\n\n".join(part for part in (first_page, source_text) if part)
    skills = _extract_named_bonus_map(searchable, SKILL_LABELS)
    senses = _extract_passive_senses_from_source(searchable)
    if len(skills) < 6 and not senses:
        return None
    blocks: list[str] = []
    if skills:
        skill_tokens = [f"{label} {_normalize_bonus_token(value)}" for label in SKILL_LABELS if (value := skills.get(label))]
        if skill_tokens:
            blocks.append("Skills: " + " | ".join(skill_tokens))
    if senses:
        sense_tokens = [f"{label} {value}" for label, value in senses.items()]
        if sense_tokens:
            blocks.append("Senses: " + " | ".join(sense_tokens))
    return "\n\n".join(blocks).strip() or None


def _build_stats_section_from_source(source_material: str) -> str | None:
    source_text = source_material or ""
    first_page = _extract_pdf_page_text(source_text, 1)
    searchable = "\n\n".join(part for part in (first_page, source_text) if part)
    ability_map = _extract_ability_map_from_source(searchable)
    save_map = _extract_save_map_from_source(searchable)
    if not ability_map and not save_map:
        return None

    stat_tokens: list[str] = []
    for abbr in ABILITY_ORDER:
        score, mod = ability_map.get(abbr, ("UNKNOWN", "UNKNOWN"))
        stat_tokens.append(f"{abbr} {score} ({mod})")

    save_tokens: list[str] = []
    for abbr in ABILITY_ORDER:
        if save := save_map.get(abbr):
            save_tokens.append(f"{abbr} {save}")

    parts = [f"Stats: {' | '.join(stat_tokens)}"]
    if save_tokens:
        parts.append(f"Saves: {' | '.join(save_tokens)}")
    return "\n\n".join(parts)


def _build_combat_section_from_source(source_material: str) -> str | None:
    text = _strip_markdown_preserve_lines(_extract_pdf_page_text(source_material or "", 1) or source_material or "")
    lines: list[str] = []
    attacks_per_action = _extract_attacks_per_action(text)
    if attacks_per_action:
        lines.append(f"Multiattack: {attacks_per_action} attacks per Action")

    attack_patterns = (
        r"(?m)^([A-Za-z][A-Za-z0-9 '+()/,\-]+?)\s+(?:\d+\s*ft|\d+/\d+)\s+([+\-]?\d+)\s+vs\s+AC\s+(.+)$",
        r"(?m)^([A-Za-z][A-Za-z0-9 '+()/,\-]+?)\s*\|\s*([+\-]?\d+)\s*to hit\s*\|\s*(.+)$",
    )
    seen: set[str] = set()
    for pattern in attack_patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            name = match.group(1).strip()
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            hit = _normalize_bonus_token(match.group(2))
            detail = match.group(3).strip()
            lines.append(f"{name}: {hit} to hit | {detail}")
            if len(lines) >= 6:
                break
        if len(lines) >= 6:
            break

    return "\n".join(lines).strip() or None


def _extract_attacks_per_action(text: str) -> str | None:
    cleaned = _strip_markdown(text or "")
    patterns = (
        r"\b(\d+)\s+Attacks?\s*/\s*Attack Action\b",
        r"\bAttacks?\s*/\s*Action\s*:?\s*(\d+)\b",
        r"\bAttacks?\s+per\s+Action\s*:?\s*(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_combat_lines(sheet_body: str, *, limit: int = 4) -> list[str]:
    combat = _section_map(sheet_body).get("combat", "")
    if not combat:
        return []
    lines = [line.strip() for line in combat.splitlines() if line.strip()]
    cleaned = []
    for line in lines:
        compact = _strip_markdown(line.lstrip("•*- ").strip())
        if compact:
            cleaned.append(compact)
    return cleaned[:limit]


def _extract_level_from_build(build_line: str) -> int | None:
    match = re.search(r"\bLevel\s+(\d+)\b", build_line or "", flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _derive_proficiency_bonus(level: int | None) -> str | None:
    if level is None:
        return None
    return str(2 + max(level - 1, 0) // 4)


def _derive_hit_dice(build_line: str, level: int | None) -> str | None:
    if level is None or "/" in (build_line or ""):
        return None
    lowered = (build_line or "").lower()
    for class_name, die_side in CLASS_HIT_DIE_SIDES.items():
        if class_name in lowered:
            return f"{level}d{die_side}"
    return None


def _derive_speed_from_build(build_line: str, source_material: str) -> str | None:
    movement_bonus = re.search(r"speed increases by\s+(\d+)\s+feet", source_material or "", flags=re.IGNORECASE)
    build_lower = (build_line or "").lower()
    for ancestry, base_speed in BASE_SPEEDS.items():
        if ancestry in build_lower:
            return str(base_speed + int(movement_bonus.group(1))) if movement_bonus else str(base_speed)
    return None


def _extract_ac_from_source(source_material: str) -> str | None:
    patterns = (
        r"\bAC equals\s+(\d+)\b",
        r"Unarmored Defense.*?\((\d+)\)",
        r"\bARMOR CLASS\b.*?\b(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, source_material or "", flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1)
    return None


def _extract_aurora_window_tokens(source_material: str) -> list[str]:
    source = (source_material or "").replace("\n", " | ")
    match = re.search(r"(Level\s+\d+[^|]+)\|", source, flags=re.IGNORECASE)
    if not match:
        return []
    segment = source[match.start():]
    attack_marker = segment.find("2 Attacks / Attack Action")
    if attack_marker != -1:
        segment = segment[:attack_marker]
    return [token.strip() for token in segment.split("|") if token.strip()]


def _extract_source_snapshot_values(source_material: str) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    searchable = "\n\n".join(part for part in (_extract_pdf_page_text(source_material, 1), source_material or "") if part)
    hp_pair = re.search(r"\bHP[\s:.\-]+(\d+)\s*/\s*(\d+)\b", searchable, flags=re.IGNORECASE)
    if hp_pair:
        snapshot["current_hp"] = hp_pair.group(1)
        snapshot["max_hp"] = hp_pair.group(2)
    else:
        max_hp = re.search(r"\b(?:Max(?:imum)?|HP Max|Current Hit Points)[\s:.\-]+(\d+)\b", searchable, flags=re.IGNORECASE)
        if max_hp:
            snapshot["max_hp"] = max_hp.group(1)
    generic_patterns = {
        "ac": (r"\bAC[\s:.\-]+(\d+)\b", r"\bArmor Class\b.*?\b(\d+)\b"),
        "pb": (r"\b(?:PB|Proficiency Bonus|Proficiency)[\s:.\-]+\+?(\d+)\b",),
        "speed": (r"\bSpeed[\s:.\-]+(\d+)\s*ft\b",),
        "hit_dice": (r"\bHit Dice[\s:.\-]+([0-9]+d[0-9]+(?:\s*/\s*[0-9]+d[0-9]+)?)\b",),
        "initiative": (r"\bInitiative[\s:.\-]+([+\-]?\d+)\b", r"\bInit[\s:.\-]+([+\-]?\d+)\b"),
        "passive": (r"\bPassive Perception[\s:.\-]+(\d+)\b", r"\bP\.\s*Perception[\s:.\-]+(\d+)\b"),
        "attacks_per_action": (r"\b(\d+)\s+Attacks?\s*/\s*Attack Action\b", r"\bAttacks?\s+per\s+Action[\s:.\-]+(\d+)\b"),
    }
    for key, patterns in generic_patterns.items():
        if snapshot.get(key):
            continue
        for pattern in patterns:
            match = re.search(pattern, searchable, flags=re.IGNORECASE | re.DOTALL)
            if match:
                snapshot[key] = match.group(1)
                break
    tokens = _extract_aurora_window_tokens(source_material)
    if tokens:
        if "ac" not in snapshot:
            for index, token in enumerate(tokens):
                if "unarmored defense" in token.lower() and index + 1 < len(tokens) and re.fullmatch(r"\d+", tokens[index + 1]):
                    snapshot["ac"] = tokens[index + 1]
                    break
        if "hit_dice" not in snapshot:
            for index, token in enumerate(tokens):
                if re.fullmatch(r"\d+d\d+", token, flags=re.IGNORECASE):
                    snapshot["hit_dice"] = token
                    if "max_hp" not in snapshot and index > 0 and re.fullmatch(r"\d+", tokens[index - 1]):
                        snapshot["max_hp"] = tokens[index - 1]
                    break
        if "speed" not in snapshot:
            for token in tokens:
                ft_match = re.fullmatch(r"(\d+)ft\.?", token, flags=re.IGNORECASE)
                if ft_match:
                    snapshot["speed"] = ft_match.group(1)
                    break
        attack_index = next((i for i, token in enumerate(tokens) if "attacks / attack action" in token.lower()), -1)
        if attack_index >= 2:
            initiative_token = tokens[attack_index - 1]
            passive_token = tokens[attack_index - 2]
            initiative_match = re.fullmatch(r"([+-]?\d+)", initiative_token)
            passive_match = re.fullmatch(r"(\d+)", passive_token)
            if initiative_match and "initiative" not in snapshot:
                snapshot["initiative"] = initiative_match.group(1)
            if passive_match and "passive" not in snapshot:
                snapshot["passive"] = passive_match.group(1)
    return snapshot


def _extract_sheet_snapshot_values(body: str) -> dict[str, str]:
    text = _strip_markdown(body)
    snapshot: dict[str, str] = {}
    hp_pair = re.search(r"\bHP[\s:.\-]+(\d+)\s*/\s*(\d+)\b", text, flags=re.IGNORECASE)
    if hp_pair:
        snapshot["current_hp"] = hp_pair.group(1)
        snapshot["max_hp"] = hp_pair.group(2)
    else:
        max_hp = re.search(r"\b(?:Max(?:imum)?\s+HP|HP|Current Hit Points)[\s:.\-]+(\d+)\b", text, flags=re.IGNORECASE)
        if max_hp:
            snapshot["max_hp"] = max_hp.group(1)
    patterns = {
        "ac": r"\bAC[\s:.\-]+(\d+)\b",
        "pb": r"\b(?:PB|Proficiency(?: Bonus)?)[\s:.\-]+\+?(\d+)\b",
        "speed": r"\bSpeed[\s:.\-]+(\d+)\s*ft\b",
        "hit_dice": r"\bHit Dice[\s:.\-]+([0-9]+d[0-9]+(?:\s*/\s*[0-9]+d[0-9]+)?)\b",
        "initiative": r"\bInit(?:iative)?[\s:.\-]+([+\-]?\d+)\b",
        "passive": r"\b(?:Passive(?:\s+Perception)?|P\.\s*Perception)[\s:.\-]+(\d+)\b",
        "attacks_per_action": r"\b(?:Atk/Action|Attacks?/Action|Attacks?\s+per\s+Action)\s*:?\s*(\d+)\b",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            snapshot[key] = match.group(1)
    return snapshot


def parse_core_stat_updates(text: str) -> dict[str, str]:
    raw = text or ""
    updates: dict[str, str] = {}
    patterns = {
        "ac": r"\bAC\s*[:=]?\s*(\d+)\b",
        "pb": r"\b(?:PB|Proficiency Bonus)\s*[:=]?\s*\+?(\d+)\b",
        "speed": r"\bSpeed\s*[:=]?\s*(\d+)\s*ft\b",
        "max_hp": r"\b(?:Max(?:imum)?\s*HP|HP\s*max|max\s*HP)\s*[:=]?\s*(\d+)\b",
        "current_hp": r"\b(?:Current\s*HP|HP\s*current)\s*[:=]?\s*(\d+)\b",
        "hit_dice": r"\b(?:Hit Dice|HD)\s*[:=]?\s*([0-9]+d[0-9]+)\b",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            updates[key] = match.group(1)
    generic_hp = re.search(r"\bHP\s*[:=]?\s*(\d+)\b", raw, flags=re.IGNORECASE)
    if generic_hp and "max_hp" not in updates and "current_hp" not in updates:
        updates["max_hp"] = generic_hp.group(1)
    return updates
