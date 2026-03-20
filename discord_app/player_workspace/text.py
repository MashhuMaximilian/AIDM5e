import re
from urllib.parse import quote_plus

from .constants import (
    MAX_PLAYER_CARD_MESSAGE_LENGTH,
    MISSING_PLACEHOLDER,
    MODE_LABELS,
    STATUS_LABELS,
)


def slugify_entity_key(value: str) -> str:
    lowered = (value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "player"


def _display_mode_label(mode: str | None) -> str:
    normalized = (mode or "").strip().lower()
    return MODE_LABELS.get(normalized, (mode or "").strip().title() or MODE_LABELS["idea"])


def _display_status_label(status: str | None) -> str:
    normalized = (status or "").strip().lower().replace(" ", "_")
    return STATUS_LABELS.get(normalized, (status or "").strip().replace("_", " ").title() or STATUS_LABELS["draft"])


def _is_missing_placeholder(text: str | None) -> bool:
    normalized = (text or "").strip().lower()
    return not normalized or "pending confirmation" in normalized or normalized == MISSING_PLACEHOLDER.lower()


def _normalize_bonus_token(value: str) -> str:
    cleaned = (value or "").strip().replace("−", "-").replace("–", "-").replace("—", "-")
    if not cleaned:
        return cleaned
    if cleaned.startswith(("+", "-")):
        return cleaned
    if re.fullmatch(r"\d+", cleaned):
        return f"+{cleaned}"
    return cleaned


def _extract_pdf_page_text(source_material: str, page_number: int) -> str:
    text = source_material or ""
    pattern = re.compile(
        rf"\[PDF Page {page_number}\]\s*(.*?)(?=\[PDF Page {page_number + 1}\]|\Z)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    return text


def _truncate_embed_value(value: str, limit: int = 1024) -> str:
    cleaned = (value or "").strip()
    if len(cleaned) <= limit:
        return cleaned or MISSING_PLACEHOLDER
    return cleaned[: limit - 3].rstrip() + "..."


def _split_field_blocks(body: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    chunks = [chunk.strip() for chunk in (body or "").split("\n\n") if chunk.strip()]
    for chunk in chunks:
        lines = [line.rstrip() for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        if len(lines) == 1 and not lines[0].startswith("•") and ":" not in lines[0]:
            blocks.append((lines[0], ""))
            continue
        first = lines[0]
        if not first.startswith("•") and ":" in first:
            label, _, remainder = first.partition(":")
            rest = [remainder.strip()] if remainder.strip() else []
            rest.extend(line.strip() for line in lines[1:])
            blocks.append((label.strip(), "\n".join(line for line in rest if line).strip()))
            continue
        if not first.startswith("•"):
            blocks.append((first, "\n".join(line.strip() for line in lines[1:]).strip()))
            continue
        blocks.append(("", "\n".join(line.strip() for line in lines).strip()))
    return blocks


def _normalize_section_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (label or "").strip().lower()).strip()


def _display_section_heading(label: str) -> str:
    normalized = _normalize_section_key(label)
    words = set(normalized.split())
    if "racial" in words:
        return "## 🌌 Racial Traits"
    if "feat" in words or "feats" in words:
        return "## 📜 Feats"
    if "class" in words and "subclass" not in words:
        return f"## ⚔️ {label}"
    if "subclass" in words:
        return f"## ✨ {label}"
    if "magic" in words or "spell" in words or "spellcasting" in words:
        return "## ✨ Magic"
    if "proficiencies" in words or "proficiency" in words or "languages" in words or "language" in words:
        return "## 🛠️ Proficiencies"
    if "attuned" in words:
        return "## 💎 Attuned Items"
    if "gear" in words or "inventory" in words or "loadout" in words:
        return "## 🎒 Inventory & Attunement"
    if "companions" in words or "companion" in words or "allies" in words:
        return "## 🐾 Companions"
    if "currency" in words:
        return "## 💰 Currency"
    if "capacity" in words or "carry" in words or "encumbrance" in words:
        return "## 🎒 Encumbrance"
    return f"## {label}"


def _section_map(body: str) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for label, value in _split_field_blocks(body):
        if not label:
            continue
        normalized = _normalize_section_key(label)
        if normalized:
            mapped[normalized] = value.strip()
    return mapped


def _truncate_text_block(value: str, limit: int) -> str:
    cleaned = " ".join((value or "").split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _looks_preformatted(body: str) -> bool:
    text = (body or "").strip()
    return bool(
        text
        and (
            "```" in text
            or re.search(r"(?m)^\s*##\s", text)
            or re.search(r"(?m)^\s*###\s", text)
        )
    )


def _tokenize_inline_values(text: str) -> list[str]:
    raw = (text or "").replace("\n", " | ")
    parts = [piece.strip(" •") for piece in raw.split("|")]
    return [part for part in parts if part]


def _wrap_tags(values: list[str], *, max_items: int = 8) -> str:
    limited = values[:max_items]
    if not limited:
        return MISSING_PLACEHOLDER
    return " ".join(f"`{item}`" for item in limited)


def _split_top_level_commas(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        if char == "," and depth == 0:
            piece = "".join(current).strip()
            if piece:
                parts.append(piece)
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _extract_code_blocks(text: str) -> list[str]:
    return re.findall(r"```(?:\w+)?\n.*?```", text or "", flags=re.DOTALL)


def _extract_markdown_section(text: str, keywords: tuple[str, ...], *, include_heading: bool = False) -> str | None:
    lines = (text or "").splitlines()
    collecting = False
    captured: list[str] = []
    heading_line = ""
    for line in lines:
        stripped = line.strip()
        if re.match(r"^##+\s+", stripped):
            lowered = stripped.lower()
            if any(keyword.lower() in lowered for keyword in keywords):
                collecting = True
                heading_line = line.rstrip()
                captured = [heading_line] if include_heading else []
                continue
            if collecting:
                break
        if collecting:
            captured.append(line.rstrip())
    result = "\n".join(captured).strip()
    return result or None


def _extract_code_block_from_section(text: str, keywords: tuple[str, ...]) -> str | None:
    section = _extract_markdown_section(text, keywords)
    if not section:
        return None
    codeblocks = _extract_code_blocks(section)
    return codeblocks[0] if codeblocks else None


def _extract_actions_section(text: str) -> str | None:
    match = re.search(r"(?ms)^### .*?(?=^\s*## |\Z)", text or "")
    return match.group(0).strip() if match else None


def _ensure_blank_line_before_headings(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n").strip()
    if not cleaned:
        return cleaned
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"(?m)(?<!\n)\n(#{2,}\s)", r"\n\n\1", cleaned)
    return cleaned.strip()


def _strip_markdown(text: str) -> str:
    cleaned = (text or "").replace("```text", "").replace("```", "")
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    return " ".join(cleaned.split()).strip()


def _strip_markdown_preserve_lines(text: str) -> str:
    cleaned = (text or "").replace("```text", "").replace("```", "")
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    lines = []
    for line in cleaned.splitlines():
        compact = " ".join(line.split()).strip()
        if compact:
            lines.append(compact)
    return "\n".join(lines).strip()


def _compact_name(value: str) -> str:
    item = _strip_markdown(value or "")
    item = re.sub(r"\(.*?\)", "", item).strip()
    item = item.strip("[]")
    item = item.split(":", 1)[0].strip()
    item = item.split(".", 1)[0].strip() if len(item) > 40 else item
    return item


def _format_single_line_code_block(value: str) -> str:
    cleaned = _strip_markdown(value or "")
    return f"```text\n{cleaned or MISSING_PLACEHOLDER}\n```"


def _format_metric_row(label: str, value: str, *, dots: int = 6) -> str:
    del dots
    label_text = label.upper()
    dot_count = max(1, 12 - len(label_text))
    return f"{label_text}{'.' * dot_count}: {value}"


def _split_resource_label_and_value(token: str) -> tuple[str, str]:
    cleaned = _strip_markdown(token)
    match = re.match(r"([A-Za-z /'-]+?)\s+([+\-]?\d.*)$", cleaned)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return cleaned, ""


def _render_player_card_message(*, title: str, part: str, part_index: int, part_count: int) -> str:
    sections = [f"**{title}**"]
    if part_count > 1:
        sections.append(f"• Part: `{part_index}/{part_count}`")
    sections.append(part)
    return "\n\n".join(section for section in sections if section)


def split_player_card_body(*, body: str, card_title: str) -> list[str]:
    cleaned_body = (body or "").strip() or MISSING_PLACEHOLDER

    def available_text_len(part_count: int) -> int:
        sample = _render_player_card_message(title=card_title, part="", part_index=part_count, part_count=part_count)
        return MAX_PLAYER_CARD_MESSAGE_LENGTH - len(sample) - 2

    def split_units(text: str) -> list[str]:
        units: list[str] = []
        last = 0
        for match in re.finditer(r"```(?:\w+)?\n.*?```", text, flags=re.DOTALL):
            before = text[last:match.start()]
            units.extend(chunk.strip() for chunk in before.split("\n\n") if chunk.strip())
            units.append(match.group(0).strip())
            last = match.end()
        tail = text[last:]
        units.extend(chunk.strip() for chunk in tail.split("\n\n") if chunk.strip())
        return units or [text]

    def chunk_text(text: str, budget: int) -> list[str]:
        paragraphs = split_units(text)
        parts: list[str] = []
        current = ""

        def flush_current() -> None:
            nonlocal current
            if current.strip():
                parts.append(current.strip())
            current = ""

        for paragraph in paragraphs:
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= budget:
                current = candidate
                continue
            if current:
                flush_current()
            if len(paragraph) <= budget:
                current = paragraph
                continue
            if paragraph.startswith("```") and paragraph.endswith("```"):
                parts.append(paragraph)
                continue
            lines = [line for line in paragraph.splitlines() if line.strip()] or [paragraph]
            line_buffer = ""
            for line in lines:
                line_candidate = line if not line_buffer else f"{line_buffer}\n{line}"
                if len(line_candidate) <= budget:
                    line_buffer = line_candidate
                    continue
                if line_buffer:
                    parts.append(line_buffer.strip())
                    line_buffer = ""
                while len(line) > budget:
                    parts.append(line[:budget].rstrip())
                    line = line[budget:]
                line_buffer = line
            if line_buffer:
                current = line_buffer
        flush_current()
        return parts or [text[:budget].rstrip()]

    part_count = 1
    while True:
        budget = available_text_len(part_count)
        if budget < 1:
            raise ValueError("Player card metadata is too large to fit in a Discord message.")
        parts = chunk_text(cleaned_body, budget)
        next_count = len(parts)
        if next_count == part_count:
            break
        part_count = next_count
    return parts


def build_reference_link(name: str) -> str:
    cleaned = re.sub(r"^[\d\W_]+", "", (name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""

    canonical = cleaned.lower()
    canonical = re.sub(r"\b(class|class features|subclass|subclass features|racial traits|race traits|feat|feats|magic|proficiencies|languages)\b", "", canonical).strip()
    canonical = re.sub(r"\s+", " ", canonical)

    exact_links = {
        "monk": "https://www.dndbeyond.com/classes/monk",
        "druid": "https://www.dndbeyond.com/classes/druid",
        "paladin": "https://www.dndbeyond.com/classes/paladin",
        "warlock": "https://www.dndbeyond.com/classes/warlock",
        "way of the open hand": "https://dnd5e.wikidot.com/monk:open-hand",
        "circle of the stars": "https://dnd5e.wikidot.com/druid:stars",
        "oath of the ancients": "https://dnd5e.wikidot.com/paladin:ancients",
        "hexblade": "https://dnd5e.wikidot.com/warlock:hexblade",
        "stout halfling": "https://dnd5e.wikidot.com/lineage:halfling-stout",
        "halfling": "https://dnd5e.wikidot.com/lineage:halfling",
        "magic initiate": "https://www.dndbeyond.com/feats/1789162-magic-initiate",
        "magic initiate druid": "https://www.dndbeyond.com/feats/1789162-magic-initiate",
        "ring of the ram": "https://www.dndbeyond.com/magic-items/9228971-ring-of-the-ram",
    }
    if canonical in exact_links:
        return f"<{exact_links[canonical]}>"

    slug = canonical
    slug = slug.replace("&", " and ")
    slug = re.sub(r"[’']", "", slug)
    slug = re.sub(r"\([^)]*\)", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")

    classes = {
        "artificer", "barbarian", "bard", "cleric", "druid", "fighter",
        "monk", "paladin", "ranger", "rogue", "sorcerer", "warlock", "wizard",
    }
    feats = {
        "alert", "athlete", "charger", "crossbow-expert", "crusher", "defensive-duelist",
        "dual-wielder", "fey-touched", "great-weapon-master", "healer", "heavy-armor-master",
        "keen-mind", "lucky", "magic-initiate", "mobile", "observant", "polearm-master",
        "resilient", "sentinel", "shadow-touched", "sharpshooter", "skilled", "spell-sniper",
        "telekinetic", "telepathic", "tough", "war-caster",
    }
    spells = {
        "animal-shapes", "aura-of-vitality", "blight", "call-lightning", "confusion",
        "cure-wounds", "dispel-magic", "entangle", "faerie-fire", "fire-storm",
        "greater-restoration", "guidance", "guiding-bolt", "heal", "ice-knife",
        "lesser-restoration", "light", "mass-cure-wounds", "misty-step", "moonbeam",
        "pass-without-trace", "poison-spray", "polymorph", "primal-savagery", "reverse-gravity",
        "revivify", "sanctuary", "scorching-ray", "shillelagh", "sunbeam", "thorn-whip",
        "thunderclap", "wall-of-fire", "wall-of-stone",
    }
    magic_items = {
        "ring-of-the-ram", "circlet-of-blasting", "sending-stones",
    }

    if slug in classes:
        return f"<https://www.dndbeyond.com/classes/{slug}>"
    if slug in feats:
        return f"<https://www.dndbeyond.com/feats/{slug}>"
    if slug in spells:
        return f"<https://www.dndbeyond.com/spells/{slug}>"
    if slug in magic_items:
        return f"<https://www.dndbeyond.com/magic-items/{slug}>"
    return ""
