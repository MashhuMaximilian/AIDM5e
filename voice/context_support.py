from pathlib import Path

from config import (
    VOICE_CONTEXT_DIR,
    VOICE_DM_CONTEXT_PATH,
    VOICE_INCLUDE_DM_CONTEXT,
    VOICE_PUBLIC_CONTEXT_PATH,
    VOICE_SESSION_CONTEXT_PATH,
)


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

    sections = []
    if public_text:
        sections.append("Public evergreen context:\n" + public_text)
    if session_text:
        sections.append("Session-only context:\n" + session_text)
    if dm_text:
        sections.append("DM-private context:\n" + dm_text)

    if not sections:
        return None

    guidance = (
        "Reference context is provided below for names, spelling, character/campaign facts, and public continuity.\n"
        "Use it to improve identification and consistency, but do not invent events or dialogue that are unsupported by the audio.\n"
        "If context conflicts with the audio, prefer the audio and note the uncertainty.\n"
    )
    return guidance + "\n\n" + "\n\n".join(sections)
