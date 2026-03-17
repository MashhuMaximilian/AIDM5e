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

- Refine and test the behavior of the commands that now work on Gemini + Supabase.
- Tighten formatting and memory behavior based on real Discord testing.
- Finish the utility-command verification pass with real Discord tests, not just code review.
- Prepare the transcript/session-summary flow for the next implementation phase.

## Immediate Next

- Check and test the remaining utility commands:
  - `/delete_memory`
  - `/reset_memory`
  - `/send`
  - `/startnew`
  - `/assign_memory`
  - `/set_always_on`
- Re-test the recently polished command UX:
  - `/tellme`
  - `/askdm`
  - `/reference`
  - `/listmemory`
  - `/feedback`
- Review whether any command responses should state the effective target channel/memory more explicitly.
- Add more real-world prompt tuning based on live outputs, not just abstract prompt design.
- Decide whether `/tellme` and `/askdm` should keep defaulting to `#telldm` long-term or default to the invoking channel.

## Remaining Functional Tasks

- Split transcript/session-summary output into separate artifacts:
  - objective/literal transcript-derived session record
  - narrative story recap
  - raw transcript attachment/output
- Add TODO-backed separation between transcript objective summary and transcript narrative recap in runtime behavior, not only in prompt text.
- Improve `/summarize` so it fully accounts for supported attachment contents in message slices.
- Re-test:
  - `/tellme`
  - `/askdm`
  - `/summarize`
  - `/feedback`
  - `/reference`
  - transcript/session-summary path
- Decide when to add `/context_link`.

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
- Consider whether some features should use a different model/provider than the main gameplay/reference flow.
- Revisit legacy/maintenance commands:
  - `/delete_memory`
  - `/reset_memory`
  - `/repairthread`
- Rework voice capture/runtime for VPS use.
- If possible, send raw audio to an AI model that can translate and transcribe directly instead of relying only on traditional speech-to-text, especially because sessions can mix two languages.
- Direct audio-to-Gemini remains one of the most promising future directions, especially because sessions can involve 5-6 speakers and switch between Romanian and English, plus in-game / out-of-game / meta talk.
- Revisit the current 180-second chunking flow and decide whether transcript should remain the main intermediate artifact or just a failsafe/redundancy layer.
- Extend transcript output so it can also be exported or represented as SRT.
- Add transcript + translation + narrative flow that can produce:
  - transcript
  - literal summary
  - story summary
  - later possibly TTS output
- Add context support per campaign for stable reference details such as character appearance, character sheets, and other reusable campaign facts.
- Use the context idea per campaign for each character, such as how they look, reference images, character sheets, and other persistent campaign details.
- Add image generation from summaries:
  - Generate a story recap plus literal transcript and literal summary outputs.
  - Derive roughly 5-20 visual scene prompts from the session.
  - Generate images for those scenes.
  - Use campaign context such as character looks, sheets, and other references.
  - Reuse ideas from short-form video / YouTube Shorts style scene selection where useful.
  - Explore reusing ideas from `/Users/max/dev/YoutubeShorts`.
- Add `/generate image`.
- Add new command `/create player` or `/create npc`:
  - create an agent/persona that can impersonate a character
  - feed it character sheet, backstory, ideals, flaws, etc.
- Consider TTS story output later:
  - maybe Qwen or another model/provider
  - check cost and server load before committing to it
- Fix platform portability in the voice pipeline:
  - current ffmpeg capture path is Mac-specific
  - make it portable and/or rely on mp3-based handling that is not tied to the current capture setup
- Add Docker and deployment cleanup later.
- Make a feature map document such as `map.md`, then decide whether it should be tracked or ignored.
- Make a patch notes folder or patch-notes workflow, and decide whether it should be tracked or ignored.

## Local-Only Artifacts

These should stay local and be ignored or untracked as needed:

- `threads.json`
- `transcript.txt`
- `transcript_archive.txt`
- `transcript_archive copy.txt`
- `.DS_Store`
- local one-off migration helpers such as `scripts/import_legacy_category.py`
- local sourcebooks and personal reference materials under `sources/`

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
- Public URL reading is now supported in `/reference`, with direct fetch first and Gemini URL Context as fallback. Google Docs/Sheets remain out of scope for now.
- `/listmemory` now supports:
  - single-target inspection
  - whole-category overview when no parameters are passed
  - grouping by memory name
  - explicit thread inheritance vs thread override display
