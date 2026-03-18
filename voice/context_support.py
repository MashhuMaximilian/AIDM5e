import re
from pathlib import Path

from config import (
    VOICE_CONTEXT_DIR,
    VOICE_DM_CONTEXT_PATH,
    VOICE_INCLUDE_DM_CONTEXT,
    VOICE_PUBLIC_CONTEXT_PATH,
    VOICE_SESSION_CONTEXT_PATH,
)


def extract_roster_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        cleaned = candidate.strip()
        if not cleaned or cleaned.lower() in seen:
            return
        seen.add(cleaned.lower())
        candidates.append(cleaned)

    for raw_line in text.splitlines():
        line = raw_line.strip(" \t-*•")
        if not line:
            continue

        playing_match = re.search(
            r"(?i)\b([A-Za-z][A-Za-z0-9'_-]{1,40})\s+(?:is\s+)?(?:playing|plays|as)\s+([A-Za-z][A-Za-z0-9'_-]{1,40})\b",
            line,
        )
        if playing_match:
            add(f"Roster candidate: player/voice {playing_match.group(1)} is associated with character {playing_match.group(2)}.")

        if ("class" in line.lower() or "race" in line.lower() or "background" in line.lower()) and "|" in line:
            name = line.split("|", 1)[0].strip()
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9' _-]{1,40}", name):
                add(f"Known character candidate from context: {name}.")

    return candidates


def _read_optional_text(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    if not path.exists() or not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def get_context_file_path(scope: str) -> Path:
    scope_map = {
        "public": Path(VOICE_PUBLIC_CONTEXT_PATH),
        "session": Path(VOICE_SESSION_CONTEXT_PATH),
        "dm": Path(VOICE_DM_CONTEXT_PATH),
    }
    path = scope_map[scope].expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_context_text(scope: str, text: str, mode: str = "replace") -> Path:
    path = get_context_file_path(scope)
    cleaned = text.strip()
    if mode == "append" and path.exists() and path.read_text(encoding="utf-8").strip():
        existing = path.read_text(encoding="utf-8").rstrip()
        path.write_text(existing + "\n\n" + cleaned + "\n", encoding="utf-8")
    else:
        path.write_text(cleaned + "\n", encoding="utf-8")
    return path


def clear_context_text(scope: str) -> Path:
    path = get_context_file_path(scope)
    path.write_text("", encoding="utf-8")
    return path


def read_context_text(scope: str) -> str:
    path = get_context_file_path(scope)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def load_voice_context(
    *,
    public_context_path: str | None = None,
    session_context_path: str | None = None,
    dm_context_path: str | None = None,
    include_dm_context: bool | None = None,
) -> str | None:
    public_text = _read_optional_text(public_context_path or VOICE_PUBLIC_CONTEXT_PATH)
    session_text = _read_optional_text(session_context_path or VOICE_SESSION_CONTEXT_PATH)
    dm_allowed = VOICE_INCLUDE_DM_CONTEXT if include_dm_context is None else include_dm_context
    dm_text = _read_optional_text(dm_context_path or VOICE_DM_CONTEXT_PATH) if dm_allowed else None
    return build_context_block(public_text=public_text, session_text=session_text, dm_text=dm_text)


def build_context_block(
    public_text: str | None = None,
    session_text: str | None = None,
    dm_text: str | None = None,
) -> str | None:
    sections = []
    if public_text and public_text.strip():
        sections.append("Public evergreen context:\n" + public_text.strip())
    if session_text and session_text.strip():
        sections.append("Session-only context:\n" + session_text.strip())
    if dm_text and dm_text.strip():
        sections.append("DM-private context:\n" + dm_text.strip())

    if not sections:
        return None

    roster_candidates: list[str] = []
    for text in (public_text, session_text, dm_text):
        if text:
            roster_candidates.extend(extract_roster_candidates(text))

    roster_block = ""
    if roster_candidates:
        deduped = []
        seen = set()
        for item in roster_candidates:
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(item)
        roster_block = "\n\nDerived roster candidates:\n" + "\n".join(f"- {item}" for item in deduped)

    guidance = (
        "Reference context is provided below for names, spelling, character/campaign facts, and public continuity.\n"
        "Use it to improve identification and consistency, but do not invent events or dialogue that are unsupported by the audio.\n"
        "If context conflicts with the audio, prefer the audio and note the uncertainty.\n"
    )
    return guidance + roster_block + "\n\n" + "\n\n".join(sections)
