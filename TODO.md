# AIDM TODO

## Immediate

- [ ] Run the offline audio test against real session recordings and review:
  - [ ] transcript quality
  - [ ] speaker labeling quality
  - [ ] `IC` / `OOC` / `META` / `UNCLEAR` tagging quality
  - [ ] `RO` / `EN` / `RO+EN` tagging quality
  - [ ] objective summary quality
  - [ ] narrative summary quality
- [ ] Live-test the rebuilt voice pipeline in Discord voice:
  - [ ] recording lifecycle
  - [ ] bot auto-leave when nobody is left
  - [ ] transcript posting to `#session-summary`
  - [ ] objective summary posting
  - [ ] narrative summary posting
  - [ ] retention flag behavior with `KEEP_AUDIO_FILES` / `KEEP_TRANSCRIPT_FILES`
- [ ] Tune `AUDIO_SUMMARY_WINDOW_CHUNKS` after first real test:
  - [ ] compare `1` chunk windows vs `2` chunk windows
  - [ ] decide whether 20-minute or 40-minute summary windows are better
- [ ] Live-test the new context workflow in Discord:
  - [ ] `/context summary` writes the expected local file
  - [ ] `/context summary` mirrors public/session updates into `#context`
  - [ ] `/context summary` user response reflects the published channel instead of a local path
  - [ ] DM-private context only mirrors safely
  - [ ] context updates affect the next live voice run without restarting the bot
- [ ] Decide whether final audio-summary reduction should later receive merged transcript as secondary context.
- [ ] Review the new offline chunk-splitting behavior on long source recordings and confirm the transcript improves over the single-file test.

## Next

- [ ] Add `.srt` generation from the structured transcript data.
- [ ] Harden transcript JSON parsing and malformed-model-output recovery.
- [ ] Improve error handling and user-facing failure messages across utility commands.
- [ ] Add offline testing support for additional audio inputs:
  - [ ] `.m4a`
  - [ ] optional conversion helpers
- [ ] Validate the new `/invite` scaffold in Discord:
  - [ ] `#context` exists
  - [ ] default session voice channel exists
  - [ ] AIDM auto-joins that voice flow correctly
- [ ] Validate category deletion cleanup:
  - [ ] deleting a category removes its campaign metadata from the database
  - [ ] deleting the last campaign in a guild removes orphaned guild metadata too
- [ ] Revisit whether `/reference` should support more attachment/document types beyond the current set.
- [ ] Decide whether transcript should also be used as final-summary grounding context after audio-summary quality is evaluated.
- [ ] Design a dedicated context-injection flow for summaries and future media generation:
  - [ ] public evergreen context such as party composition and stable character facts
  - [ ] session-only context for the next/current summary run
  - [ ] private DM-only context kept separate from public player-facing summary context
  - [ ] selectors similar to summarize/reference (`message_ids`, `last_n`, etc.)
  - [ ] decide whether `#context` should become the primary authoring surface or remain a mirror/audit trail

## Voice / Transcript

- [ ] Improve speaker labeling for in-person single-device recordings.
- [ ] Use session-start roster introduction more explicitly in transcript prompts.
- [ ] Decide whether to add extra transcript modes such as `RULES` or `COMBAT`.
- [ ] Add optional SRT export alongside transcript posting.
- [ ] Revisit summary prompt instructions for tone, uncertainty, and delivery cues.
- [ ] Improve portability of live voice capture:
  - [ ] Linux capture path
  - [ ] Windows capture path
  - [ ] Docker/device strategy
  - [ ] VPS/server deployment expectations

## Context and Content

- [ ] Add per-campaign context for stable reference details such as:
  - [ ] character appearance
  - [ ] character sheets
  - [ ] reusable campaign facts
- [ ] Add a public party-composition / campaign-reference workflow so summaries can consistently know:
  - [ ] party roster
  - [ ] character names
  - [ ] class/race/background shorthand
  - [ ] recurring terms and spelling
- [ ] Decide whether and when to add `/context_link`.
- [ ] Design context scopes:
  - [ ] evergreen campaign context
  - [ ] session-only temporary context
  - [ ] DM-private context
- [ ] Plan optional local ignored docs/reference ingestion for user-supplied rulebooks and campaign docs.
- [ ] Build a dedicated gameplay/DM prompt separate from the shared system prompt.
- [ ] Add a balancing layer for gameplay:
  - [ ] party level
  - [ ] party composition
  - [ ] optimization level
  - [ ] magic items
  - [ ] encounter intent
  - [ ] rest cadence

## Media Generation

- [ ] Add image generation from summaries:
  - [ ] derive 5-20 visual scene prompts
  - [ ] generate images for those scenes
  - [ ] use campaign context such as character looks and sheets
  - [ ] explore reuse from `/Users/max/dev/YoutubeShorts`
- [ ] Add `/generate image`.
- [ ] Add `/create player` or `/create npc`:
  - [ ] character impersonation/persona agent
  - [ ] feed character sheet, backstory, ideals, flaws, etc.
- [ ] Consider TTS story output later, with cost/server impact review.

## Model / Provider Strategy

- [ ] Compare `gemini-3-flash-preview` vs `gemini-3.1-flash-lite-preview` on real D&D audio.
- [ ] Decide whether chat should remain on `gemini-3-flash-preview`.
- [ ] Evaluate whether different models/providers should be used later for some tasks:
  - [ ] Minimax
  - [ ] Kimi
  - [ ] Qwen3
  - [ ] Gemini

## Project Hygiene

- [ ] Add Docker and deployment cleanup.
- [ ] Decide whether any non-transcript memory table is still needed now that `memory_messages` is gone.
- [ ] Make a feature map document such as `map.md` and decide whether to track it.
- [ ] Decide whether `PATCH_NOTES.md`, `TODO.md`, and the Codex handoff file should remain the standard project-tracking docs.
