# AIDM TODO

This file captures the current state of the Gemini + Supabase refactor based on the implementation work and design decisions already made.

## Locked Decisions

- Hard cutover from OpenAI runtime behavior to Gemini.
- App-owned logical memories in Supabase are the source of truth.
- Old OpenAI thread IDs are not reused as active runtime state.
- Existing Discord history stays in Discord.
- Default `/invite` channel set stays expanded:
  - `gameplay`
  - `telldm`
  - `session-summary`
  - `feedback`
  - `npcs`
  - `character-sheets`
  - `lore-and-teasers`
  - `items`
  - `dm-planning`
- Discord thread memory inherits parent channel memory unless explicitly overridden.
- `session-summary` uses the same main gameplay memory unless intentionally separated later.
- `DM_ROLE_NAME` is configurable via env.
- Files and context assets stay in Discord, not Supabase Storage.
- One Supabase project is used, with isolation by guild and campaign/category.

## Done

- Supabase schema created and verified.
- Gemini text generation integrated.
- Core storage moved off `threads.json` runtime behavior and into Supabase.
- `/invite` rewritten to create logical app memories and channel assignments.
- `/tellme` and `/askdm` working on Gemini + Supabase.
- Prompt system centralized into `prompts/`.
- Discord masked links are normalized into plain URLs before sending.
- Legacy campaign structure imported for category `1340326317345734686` (`Corpselight`):
  - campaign row
  - memory rows
  - channel rows
  - thread rows
  - channel/thread memory assignments
  - `always_on` flags

## Current Focus

- Redesign prompt behavior before more feature work.
- Keep the shared system prompt neutral.
- Let command-specific prompts steer the role and output style.
- Tighten memory discipline in prompts to reduce bleed.

## Next Prompt Pass

Write and then implement prompt revisions for:

- Shared system prompt
- `/tellme`
- `/askdm`
- Transcript objective summary
- Transcript narrative summary
- `/summarize`
- `/feedback`

## Next Implementation Steps

- Wire the approved prompt drafts into code.
- Add TODO-backed separation between transcript objective summary and transcript narrative recap.
- Improve `/summarize` so it can later account for supported attachment contents.
- Re-test:
  - `/tellme`
  - `/askdm`
  - `/summarize`
  - `/feedback`
  - transcript/session-summary path

## Later

- Build a dedicated gameplay/DM prompt separate from the shared system prompt.
- Add a balancing layer for gameplay:
  - party level
  - party composition
  - optimization level
  - magic items
  - encounter intent
  - rest cadence
- Plan optional local ignored docs/reference ingestion for user-supplied rulebooks and campaign docs.
- Evaluate whether a different model/provider should be used later for some tasks:
  - Minimax
  - Kimi
  - Qwen3
  - Gemini
- Revisit legacy/maintenance commands:
  - `/listmemory`
  - `/delete_memory`
  - `/reset_memory`
  - `/repairthread`
- Decide whether and when to add `/context_link`.
- Rework voice capture/runtime for VPS use.
- If possible, send raw audio to an AI model that can translate and transcribe directly instead of relying only on traditional speech-to-text, especially because sessions can mix two languages.
- Extend transcript output so it can also be exported or represented as SRT.
- Add context support per campaign for stable reference details such as character appearance, character sheets, and other reusable campaign facts.
- Add image generation from summaries:
  - Generate a story recap plus literal transcript and literal summary outputs.
  - Derive roughly 5-20 visual scene prompts from the session.
  - Generate images for those scenes.
  - Use campaign context such as character looks, sheets, and other references.
  - Reuse ideas from short-form video / YouTube Shorts style scene selection where useful.
- Add Docker and deployment cleanup later.

## Local-Only Artifacts

These should stay local and be ignored or untracked as needed:

- `threads.json`
- `transcript.txt`
- `transcript_archive.txt`
- `transcript_archive copy.txt`
- `.DS_Store`
- local one-off migration helpers such as `scripts/import_legacy_category.py`

## Notes

- The current legacy import was intentionally minimal. It migrated structure only, not old hidden provider memory.
- Campaign continuity seeding from old summaries/transcripts can be revisited later, but is not required now.
- The next major design problem after prompt work is gameplay balancing and richer DM-mode behavior.
- `/summarize` should later:
  - collect target messages
  - inspect attachments
  - extract readable text from supported file types
  - include attachment-derived text in the summary prompt
  - identify when an attachment was present but unreadable
