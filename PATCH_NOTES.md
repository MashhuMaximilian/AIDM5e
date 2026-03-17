# AIDM Patch Notes

This file tracks what has been implemented, what changed, and the current shape of the Gemini + Supabase rewrite.

## Architecture Decisions

- Hard cutover from OpenAI runtime behavior to Gemini.
- Supabase-backed app-owned memories are the source of truth.
- Old OpenAI thread IDs are not reused as active runtime state.
- Existing Discord history remains in Discord.
- Files and context assets stay in Discord, not Supabase Storage.
- One Supabase project is used, with isolation by guild and campaign/category.
- Default `/invite` layout:
  - `gameplay`
  - `telldm`
  - `session-summary`
  - `feedback`
  - `npcs`
  - `character-sheets`
  - `lore-and-teasers`
  - `items`
  - `dm-planning`

## Core Migration

- Supabase schema created and verified.
- Gemini text generation integrated.
- Core runtime moved off `threads.json` behavior and onto Supabase.
- `/invite` rewritten to create logical memories and channel assignments.
- Legacy campaign structure imported for category `1340326317345734686` (`Corpselight`):
  - campaign row
  - memory rows
  - channel rows
  - thread rows
  - channel/thread memory assignments
  - `always_on` flags

## Prompt System

- Prompt system centralized into `prompts/`.
- Shared system prompt rewritten to be neutral, memory-disciplined, and Discord-aware.
- `/tellme`, `/askdm`, `/summarize`, `/feedback`, transcript summary prompts, and reference-reading prompts were redesigned.
- Discord masked links are normalized into plain URLs before sending.

## Retrieval and Context

- `/summarize` can now read selected historical attachments from Discord messages.
- `/reference` was added:
  - reads selected messages
  - reads supported attachments
  - reads public URLs
- Public URL reading uses direct fetch first and Gemini URL Context as fallback.
- Google Docs/Sheets remain out of scope for now.

## Command and Memory UX

- `/tellme` and `/askdm` clearly default to `#telldm` when no target is specified.
- Slash-command descriptions were tightened across the utility command set.
- Dense list formatting was normalized for Discord output.
- `/feedback` now uses the `#feedback` memory when generating its recap.
- `/listmemory` now supports:
  - single-target inspection
  - whole-category overview when no parameters are passed
  - grouping by memory name
  - explicit thread inheritance vs thread override display
- `/send` now:
  - copies selected Discord-visible content to the target
  - mirrors that transferred content into the target memory
  - posts a short AIDM acknowledgment in the target memory/channel
- Fast utility commands were moved away from deferred followups where possible to reduce the lingering Discord “thinking” indicator.
- `/repairthread` was retired from the active command surface.

## Voice / Transcript Direction

- Transcription is now aimed at Gemini rather than OpenAI.
- Transcript/session-summary prompt split was designed for:
  - objective factual record
  - narrative recap
- Runtime still needs a fuller session-summary implementation pass.

## Local-Only Artifacts

These stay local and should not drive runtime behavior:

- `threads.json`
- `transcript.txt`
- `transcript_archive.txt`
- `transcript_archive copy.txt`
- `.DS_Store`
- local migration helpers such as `scripts/import_legacy_category.py`
- local sourcebooks and personal references under `sources/`

## Notes

- The legacy import was intentionally structural only; it did not restore hidden provider memory.
- The next major design area after utility-command cleanup is the transcript/session-summary flow, followed by richer gameplay/balancing behavior.
