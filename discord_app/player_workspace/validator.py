from __future__ import annotations

import re

from .schema import CharacterDraft, ValidationIssue, ValidationResult


def _required_sections_for_mode(mode: str) -> tuple[str, ...]:
    if mode == "idea":
        return ("profile",)
    return ("profile", "core_status", "abilities", "skills", "rules", "items")


def _required_fields_for_mode(mode: str) -> tuple[str, ...]:
    if mode == "idea":
        return ("character_name",)
    return ("character_name", "build_line")


def _has_meaningful_core_status(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    upper = cleaned.upper()
    return "AC" in upper and "HP" in upper and "PB" in upper


def _has_meaningful_abilities(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if cleaned.upper().count("UNKNOWN") >= 12:
        return False
    return bool(re.search(r"\|\s*(?:\[[●◎ ]\]\s*)?(?:STR|DEX|CON|INT|WIS|CHA)\s*\|\s*\d+", cleaned, re.IGNORECASE))


def _has_meaningful_skills(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if cleaned.upper().count("UNKNOWN") >= 12:
        return False
    return bool(re.search(r"(Acrobatics|Perception|Insight|Stealth).*?[+-]\d+", cleaned, re.IGNORECASE))


def _has_meaningful_actions(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if "needs review" in lowered:
        return False
    return bool(
        re.search(
            r"^\s*[*-]\s+\*\*.+?(?::\*\*|\*\*:)",
            cleaned,
            re.MULTILINE,
        )
    )


def _section_is_complete(name: str, value: str, draft: CharacterDraft) -> bool:
    if name == "core_status":
        return _has_meaningful_core_status(value)
    if name == "abilities":
        return _has_meaningful_abilities(value)
    if name == "skills":
        return _has_meaningful_skills(value)
    if name == "actions":
        return _has_meaningful_actions(value)
    return bool((value or "").strip())


def validate_draft(draft: CharacterDraft) -> ValidationResult:
    missing_sections: list[str] = []
    missing_fields: list[str] = []
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    section_values = {
        "profile": draft.sections.profile,
        "core_status": draft.sections.core_status,
        "abilities": draft.sections.abilities,
        "skills": draft.sections.skills,
        "actions": draft.sections.actions,
        "rules": draft.sections.rules,
        "items": draft.sections.items,
    }

    for section in _required_sections_for_mode(draft.mode):
        if not _section_is_complete(section, section_values.get(section, ""), draft):
            missing_sections.append(section)
            severity = "error" if section in {"profile", "core_status", "abilities", "skills"} and draft.mode == "import" else "warning"
            issue = ValidationIssue(f"Missing required section: {section}.", severity=severity, section=section)
            (errors if severity == "error" else warnings).append(issue)

    identity = draft.identity
    field_values = {
        "character_name": identity.character_name,
        "build_line": identity.build_line,
    }
    for field in _required_fields_for_mode(draft.mode):
        if not (field_values.get(field) or "").strip():
            missing_fields.append(field)
            severity = "error" if field == "character_name" else "warning"
            issue = ValidationIssue(f"Missing required field: {field}.", severity=severity, section="identity")
            (errors if severity == "error" else warnings).append(issue)

    if draft.mode == "import" and not _section_is_complete("actions", draft.sections.actions, draft):
        warnings.append(ValidationIssue("Actions in combat were not extracted.", severity="warning", section="actions"))
        missing_sections.append("actions")

    renderable = bool(identity.character_name or draft.identity.build_line or draft.concept or any(value.strip() for value in section_values.values()))
    ok = not errors
    return ValidationResult(
        ok=ok,
        renderable=renderable,
        errors=errors,
        warnings=warnings,
        missing_sections=sorted(dict.fromkeys(missing_sections)),
        missing_fields=sorted(dict.fromkeys(missing_fields)),
    )
