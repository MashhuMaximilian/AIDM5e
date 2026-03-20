import logging
import re
from typing import Any

from ai_services.gemini_client import gemini_client

from .constants import MISSING_PLACEHOLDER


logger = logging.getLogger(__name__)


def _clean_multiline(value: Any) -> str:
    if isinstance(value, list):
        value = "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _normalize_missing_info(items: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = str(item or "").strip().lstrip("-• ").strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(cleaned)
    return normalized


def _unwrap_markdown_response(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            if lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
    return text


def _extract_markdown_section(text: str, keywords: tuple[str, ...], *, include_heading: bool = False) -> str | None:
    lines = (text or "").splitlines()
    collecting = False
    captured: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^##+\s+", stripped):
            lowered = stripped.lower()
            if any(keyword.lower() in lowered for keyword in keywords):
                collecting = True
                captured = [line.rstrip()] if include_heading else []
                continue
            if collecting:
                break
        if collecting:
            captured.append(line.rstrip())
    result = "\n".join(captured).strip()
    return result or None


def _extract_code_blocks(text: str) -> list[str]:
    return re.findall(r"```(?:\w+)?\n.*?```", text or "", flags=re.DOTALL)


def _extract_actions_section(text: str) -> str | None:
    match = re.search(r"(?ms)^### .*?(?=^\s*## |\Z)", text or "")
    return match.group(0).strip() if match else None


def _strip_markdown_preserve_lines(text: str) -> str:
    cleaned = (text or "").replace("```text", "").replace("```", "")
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    lines = []
    for line in cleaned.splitlines():
        compact = " ".join(line.split()).strip()
        if compact:
            lines.append(compact)
    return "\n".join(lines).strip()


def _extract_profile_fields(profile_card: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    codeblocks = _extract_code_blocks(profile_card or "")
    profile_text = codeblocks[0] if codeblocks else profile_card or ""
    profile_text = profile_text.replace("```text", "").replace("```", "")
    pair_pattern = re.compile(r"([A-Z][A-Z .&]+?:\s*.*?)(?=(?:\s{2,}[A-Z][A-Z .&]+?:)|$)")

    for line in profile_text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("[") or set(raw) <= {"-"}:
            continue
        segments = pair_pattern.findall(raw) or [raw]
        for segment in segments:
            if ":" not in segment:
                continue
            label, value = segment.split(":", 1)
            normalized = re.sub(r"[^A-Z]", "", label.upper())
            cleaned_value = value.strip()
            if cleaned_value:
                fields[normalized] = cleaned_value
    return fields


def _infer_build_line_from_profile(profile_card: str, fallback_name: str | None) -> str:
    fields = _extract_profile_fields(profile_card)
    level = fields.get("LEVEL", "")
    race = fields.get("RACE", "")
    class_name = fields.get("CLASS", "")
    subclass = fields.get("SUBCLASS", "")

    build_bits = []
    if level:
        build_bits.append(f"Level {level}")
    if race:
        build_bits.append(race)
    if class_name:
        build_bits.append(f"{class_name} ({subclass})" if subclass and subclass not in class_name else class_name)
    elif subclass:
        build_bits.append(subclass)
    return " ".join(build_bits) if build_bits else (fallback_name or MISSING_PLACEHOLDER)


def _parse_concept_from_profile(profile_card: str) -> str:
    for line in (profile_card or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            return stripped.lstrip("> ").strip().strip("*").strip('"')
    return ""


def _parse_missing_info(text: str) -> list[str]:
    section = _extract_markdown_section(text, ("needs review", "missing info"), include_heading=False) or ""
    return _normalize_missing_info(section.splitlines())


def _parse_workspace_response(
    raw_text: str,
    *,
    character_name: str | None,
    source_labels: list[str],
) -> dict[str, Any]:
    text = _unwrap_markdown_response(raw_text)
    profile_card = _extract_markdown_section(text, ("character profile",), include_heading=True) or ""
    core = _extract_markdown_section(text, ("core status & resources", "core status"), include_heading=True) or ""
    ability = _extract_markdown_section(text, ("ability scores & saving throws",), include_heading=True) or ""
    actions = _extract_actions_section(text) or ""
    skills_card = _extract_markdown_section(text, ("skills & senses",), include_heading=True) or ""
    rules_card = _extract_markdown_section(
        text,
        ("class features & magic", "class features & traits"),
        include_heading=True,
    ) or ""
    items_card = _extract_markdown_section(text, ("inventory & attunement",), include_heading=True) or ""
    sheet_card = "\n\n".join(part for part in (core, ability, actions) if part).strip()
    return {
        "build_line": _infer_build_line_from_profile(profile_card, character_name),
        "concept": _parse_concept_from_profile(profile_card),
        "profile_card": profile_card,
        "sheet_card": sheet_card,
        "skills_card": skills_card,
        "rules_card": rules_card,
        "items_card": items_card,
        "source_summary": ", ".join(source_labels) if source_labels else "User-supplied sources",
        "missing_info": _parse_missing_info(text),
    }


def _fallback_workspace_draft(
    *,
    mode: str,
    character_name: str | None,
    player_name: str | None,
    source_labels: list[str],
    source_material: str | None,
) -> dict[str, Any]:
    concept = "Draft character workspace. Fill in the missing sections below."
    if source_material:
        compact = " ".join(source_material.split())
        concept = compact[:220].rstrip() + ("..." if len(compact) > 220 else "")

    build_bits = [bit for bit in [character_name, player_name] if bit]
    build_line = " / ".join(build_bits) if build_bits else MISSING_PLACEHOLDER
    source_summary = ", ".join(source_labels) if source_labels else f"{mode.title()} draft"
    return {
        "build_line": build_line,
        "concept": concept,
        "profile_card": (
            "## 👤 CHARACTER PROFILE\n"
            f"> {MISSING_PLACEHOLDER}\n\n"
            "```text\n"
            "[ CHARACTER LEVEL, RACE, & CLASS ]\n"
            "------------------------------------------------------------------\n"
            "LEVEL.....: UNKNOWN            RACE......: UNKNOWN\n"
            "CLASS.....: UNKNOWN            SUBCLASS..: UNKNOWN\n"
            "XP........: UNKNOWN            PLAYER....: UNKNOWN\n"
            "BACKGROUND: UNKNOWN            ALIGNMENT.: UNKNOWN\n"
            "DEITY.....: UNKNOWN\n"
            "------------------------------------------------------------------\n"
            "```\n"
        ),
        "sheet_card": (
            "## Core Status & Resources\n"
            "```text\n"
            "CORE STATUS                       RESOURCES & POOLS\n"
            "----------------------------      ------------------------------\n"
            "AC ........ UNKNOWN               HIT DICE ..... UNKNOWN\n"
            "HP ........ UNKNOWN               RESOURCE ..... UNKNOWN\n"
            "SPEED ..... UNKNOWN               RESOURCE ..... UNKNOWN\n"
            "INIT ...... UNKNOWN               RESOURCE ..... UNKNOWN\n"
            "PB ........ UNKNOWN               P. PERCEPTION . UNKNOWN\n"
            "----------------------------      ------------------------------\n"
            "```\n"
        ),
        "skills_card": "## 🧠 SKILLS & SENSES\n```text\nSKILLS & SENSES\nUNKNOWN\n```",
        "rules_card": "## ⚔️ CLASS FEATURES & MAGIC\n- UNKNOWN",
        "items_card": "## 🎒 INVENTORY & ATTUNEMENT\n- UNKNOWN",
        "source_summary": source_summary,
        "missing_info": [
            "Build details",
            "Profile details",
            "Core mechanics",
            "Skills and saving throws",
            "Rules and inventory details",
        ],
    }


def _build_workspace_prompt(
    *,
    mode: str,
    character_name: str | None,
    player_name: str | None,
    source_labels: list[str],
    source_material: str | None,
    has_files: bool,
) -> str:
    supplemental_text = ""
    if source_material:
        compact = source_material.strip()
        if has_files:
            compact = compact[:1500]
            if compact:
                supplemental_text = (
                    "\nSupplemental notes or extracted text (files are still the primary truth):\n"
                    f"{compact}\n"
                )
        else:
            compact = compact[:8000]
            supplemental_text = f"\nSource text / notes:\n{compact}\n"

    return (
        "Analyze the attached character sheet sources and return the character in the exact standardized format below.\n"
        "Act as an expert Dungeons & Dragons player, experienced DM, and data architect.\n"
        "The source may be a PDF, screenshot, document export, homebrew page, or mixed notes.\n"
        "If attached files are provided, use them as the primary truth and read the sheet closely.\n"
        "Return one complete markdown document only. Do not explain your process.\n"
        "Read the source closely and fill the template exactly. If a number is visible on the sheet, do not replace it with `UNKNOWN`.\n"
        "Page 1 usually contains the combat sheet: ability scores, modifiers, saving throws, skills, passive senses, AC, HP, hit dice, initiative, speed, attacks, resources.\n"
        "Later pages usually contain profile, inventory, item descriptions, and spells.\n\n"
        "Rules:\n"
        "- Never use `#` titles, only `##` and `###`.\n"
        "- Put one empty line before every `##` or `###` heading unless it is the first line of the document.\n"
        "- Any section shown below in a code block must be returned in a code block.\n"
        "- `### ⚔️ ACTIONS IN COMBAT` must NOT be in a code block.\n"
        "- If a value is missing or genuinely unreadable, write `UNKNOWN` instead of omitting the row.\n"
        "- Keep the full table shapes intact even when some values are `UNKNOWN`.\n"
        "- Copy ability scores, modifiers, and saving throws from the source into the ability table.\n"
        "- Copy all 18 skills into the skills table and preserve proficiency/expertise markers when the source supports them.\n"
        "- Include class resource pools in `RESOURCES & POOLS` when present, such as Ki Points, Wild Shape, Lay on Hands, Rage, Sorcery Points, Channel Divinity, Pact Slots, or Superiority Dice.\n"
        "- Distinguish clearly between racial traits, feats, class features, subclass features, magic, proficiencies, and inventory.\n"
        "- A martial character with feat-based or item-based spells is still martial unless the sheet clearly shows full spellcasting progression.\n"
        "- For spellcasters or hybrids, include spellcasting ability, spell save DC, spell attack bonus, and spells grouped by level.\n"
        "- Use the actual class, subclass, feat, spell, race/species, and item names from the source instead of generic labels.\n"
        "- Finish with `## Needs Review` and list any uncertain or missing facts as bullets. If nothing is missing, write `- None`.\n\n"
        f"Mode: {mode}\n"
        f"Character hint: {character_name or 'UNKNOWN'}\n"
        f"Player hint: {player_name or 'UNKNOWN'}\n"
        f"Source labels: {', '.join(source_labels) if source_labels else 'None'}\n"
        f"{supplemental_text}\n"
        "Use this exact framework:\n\n"
        "## 👤 CHARACTER PROFILE — [NAME]\n"
        '> ***"[Character Quote]"***\n\n'
        "```text\n"
        "[ CHARACTER LEVEL, RACE, & CLASS ]\n"
        "------------------------------------------------------------------\n"
        "LEVEL.....: [Lvl]               RACE......: [Race]\n"
        "CLASS.....: [Class]             SUBCLASS..: [Subclass]\n"
        "XP........: [Value]             PLAYER....: [Name]\n"
        "BACKGROUND: [Background]        ALIGNMENT.: [Alignment]\n"
        "DEITY.....: [Deity]\n"
        "------------------------------------------------------------------\n"
        "```\n"
        "* **Appearance:** ...\n"
        "* **Personality:** ...\n"
        "* **Backstory:** ...\n"
        "* **Roleplay Notes:** ...\n"
        "* **Allies:** ...\n\n"
        "## Core Status & Resources\n"
        "```text\n"
        "CORE STATUS                       RESOURCES & POOLS\n"
        "----------------------------      ------------------------------\n"
        "AC ........ [Value]               HIT DICE ..... [X]d[Y]\n"
        "HP ........ [Current]/[Max]       [RESOURCE 1] . [Value]\n"
        "SPEED ..... [Value]               [RESOURCE 2] . [Value]\n"
        "INIT ...... [Value]               [RESOURCE 3] . [Value]\n"
        "PB ........ [Value]               P. PERCEPTION . [Value]\n"
        "----------------------------      ------------------------------\n"
        "```\n\n"
        "## Ability Scores & Saving Throws\n"
        "```text\n"
        "ABILITY SCORES & SAVING THROWS\n"
        "+---------+-------+-----+------+\n"
        "| ABILITY | SCORE | MOD | SAVE |\n"
        "+---------+-------+-----+------+\n"
        "| [●] STR |  [#]  | [#] |  [#] |\n"
        "| [ ] DEX |  [#]  | [#] |  [#] |\n"
        "| [ ] CON |  [#]  | [#] |  [#] |\n"
        "| [ ] INT |  [#]  | [#] |  [#] |\n"
        "| [ ] WIS |  [#]  | [#] |  [#] |\n"
        "| [ ] CHA |  [#]  | [#] |  [#] |\n"
        "+---------+-------+-----+------+\n"
        "● -> Proficient    ◎ -> Expertise\n"
        "```\n\n"
        "## 🧠 SKILLS & SENSES\n"
        "```text\n"
        "SKILLS & SENSES\n"
        "--------------------------------------------------\n"
        "[ ] Acrobatics .... [#]     [ ] Medicine ...... [#]\n"
        "[ ] Animal Hand ... [#]     [ ] Nature ........ [#]\n"
        "[ ] Arcana ........ [#]     [ ] Perception .... [#]\n"
        "[ ] Athletics ..... [#]     [ ] Performance ... [#]\n"
        "[ ] Deception ..... [#]     [ ] Persuasion .... [#]\n"
        "[ ] History ....... [#]     [ ] Religion ...... [#]\n"
        "[ ] Insight ....... [#]     [ ] Sleight/Hand .. [#]\n"
        "[ ] Intimidation .. [#]     [ ] Stealth ....... [#]\n"
        "[ ] Investigation . [#]     [ ] Survival ...... [#]\n"
        "--------------------------------------------------\n"
        "PASSIVE PERCEPTION: [#] | PASSIVE INSIGHT: [#] | PASSIVE INVESTIGATION: [#]\n"
        "--------------------------------------------------\n"
        "Legend: [ ] None  [●] Proficient  [◎] Expertise\n"
        "```\n\n"
        "### ⚔️ ACTIONS IN COMBAT\n"
        "> **Multiattack:** [Name] makes `[#] attacks per Action`.\n"
        "* **[Weapon Name]:** `+[#] to hit` | `[Dice] + [#]` [Damage Type]\n\n"
        "## ⚔️ CLASS FEATURES & MAGIC\n"
        "**🌌 Racial Traits**\n"
        "> `[Trait 1]` • `[Trait 2]` • `[Trait 3]`\n"
        "**📜 Feats**\n"
        "* **[Feat Name]:** concise mechanical summary.\n"
        "**🥋 / 🌿 Class Features**\n"
        "* **[Feature Group]:** concise mechanical summary with backticked values.\n"
        "**👊 / 🌟 Subclass Features**\n"
        "* **[Feature Name]:** concise mechanical summary with backticked values.\n"
        "**✨ Magic**\n"
        "> **Spellcasting Ability:** WIS `(DC 17 | +9 to hit)`\n"
        "* **Cantrips:** *Spell, Spell*\n"
        "* **Lvl 1:** *Spell, Spell*\n"
        "**🛠️ Proficiencies**\n"
        "* **Tools:** ...\n"
        "* **Languages:** ...\n\n"
        "## 🎒 INVENTORY & ATTUNEMENT\n"
        "**💎 Attuned Items `[X / 3]`**\n"
        "1. `[Item 1]`\n"
        "2. `[Item 2]`\n"
        "**⚔️ Notable Gear**\n"
        "* **[Item]:** brief mechanical note.\n"
        "**🐾 Companions**\n"
        "* **[Companion]:** brief note.\n\n"
        "```text\n"
        "[🎒 ENCUMBRANCE — LIFTING AND CARRYING ]\n"
        "------------------------------------------------------------------\n"
        " WEIGHT CARRIED: [#] lb          CARRY CAPACITY: [#] lb\n"
        "PUSH/DRAG/LIFT: [#] lb\n"
        "------------------------------------------------------------------\n"
        "```\n\n"
        "```text\n"
        "[💰 CURRENCY ]\n"
        "------------------------------------------------------------------\n"
        "COPPER....: [#]   SILVER....: [#]   ELECTRUM..: [#]\n"
        "GOLD......: [#]   PLATINUM..: [#]\n"
        "------------------------------------------------------------------\n"
        "```\n\n"
        "## Needs Review\n"
        "- missing or uncertain field\n"
    )


def generate_player_workspace_draft(
    *,
    mode: str,
    character_name: str | None,
    player_name: str | None,
    source_labels: list[str],
    source_material: str | None,
    source_file_paths: list[str] | None = None,
) -> dict[str, Any]:
    if not source_material or not source_material.strip():
        return _fallback_workspace_draft(
            mode=mode,
            character_name=character_name,
            player_name=player_name,
            source_labels=source_labels,
            source_material=source_material,
        )

    prompt = _build_workspace_prompt(
        mode=mode,
        character_name=character_name,
        player_name=player_name,
        source_labels=source_labels,
        source_material=source_material,
        has_files=bool(source_file_paths),
    )

    try:
        raw = (
            gemini_client.generate_text_from_files(source_file_paths, prompt)
            if source_file_paths
            else gemini_client.generate_text(prompt)
        )
        draft = _parse_workspace_response(
            raw,
            character_name=character_name,
            source_labels=source_labels,
        )
        if any(draft.get(key) for key in ("profile_card", "sheet_card", "skills_card", "rules_card", "items_card")):
            return draft
        raise ValueError("Workspace draft came back empty.")
    except Exception as exc:
        logger.warning("Falling back to local player workspace draft: %s", exc)
        return _fallback_workspace_draft(
            mode=mode,
            character_name=character_name,
            player_name=player_name,
            source_labels=source_labels,
            source_material=source_material,
        )
