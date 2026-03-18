# AIDM TODO

## Current Status

- [x] Voice pipeline refactored into dedicated packages under `voice/`
- [x] Offline audio test runner added and long files split by `AUDIO_CHUNK_SECONDS`
- [x] Audio-native summary flow implemented
- [x] Transcript timestamps repaired enough for current Gemini-based testing
- [x] `/invite` creates the default text-channel scaffold
- [x] `/invite` creates `session-voice`
- [x] `/invite` creates `#context`
- [x] `/context summary` writes runtime context files
- [x] `/context summary` mirrors public/session updates into `#context`
- [x] `/context summary` mirrors DM-private updates safely
- [x] `CODEX_HANDOFF.md` removed from git tracking and ignored
- [x] Supabase `memory_messages` storage path removed from runtime code
- [x] Initial Docker runtime scaffold added

## Next Test Pass

- [ ] Live-test the rebuilt voice pipeline in Discord voice:
  - [ ] recording lifecycle
  - [ ] bot auto-join behavior
  - [ ] bot auto-leave/finalization behavior
  - [ ] transcript posting to `#session-summary`
  - [ ] objective summary posting
  - [ ] narrative summary posting
  - [ ] retention flag behavior with `KEEP_AUDIO_FILES` / `KEEP_TRANSCRIPT_FILES`

- [x] Validate context behavior in Discord:
  - [x] `/context summary` user response no longer exposes local file paths
  - [x] public/session updates visibly land in `#context`
  - [x] DM-private updates only mirror metadata in `#context`
  - [x] DM-private full content mirrors to `#dm-planning` when present
  - [x] context updates affect the next live voice run without restarting the bot

- [x] Validate category deletion cleanup end-to-end:
  - [x] deleting a category removes its campaign row from Supabase
  - [x] deleting a category removes related memories
  - [x] deleting a category removes related channels
  - [x] deleting a category removes related threads
  - [x] deleting a category removes channel/thread assignment rows
  - [x] deleting the last campaign in a guild removes orphaned guild metadata
  - [x] deleting a category also removes its previously-created child channels from Discord instead of leaving them uncategorized

## Voice / Transcript Quality

- [ ] Improve speaker labeling for in-person single-device recordings
- [ ] Use session-start roster introduction more explicitly in transcript prompts
- [ ] Keep testing `AUDIO_SUMMARY_WINDOW_CHUNKS=1` vs `2`
- [ ] Decide whether final audio-summary reduction should later receive merged transcript as secondary context
- [ ] Revisit summary prompt instructions for tone, uncertainty, and delivery cues
- [ ] Decide whether to add extra transcript modes such as `RULES` or `COMBAT`
- [ ] Add `.srt` generation from the structured transcript data
- [ ] Harden malformed transcript JSON recovery further
- [ ] Add offline support for `.m4a` inputs or conversion helpers

## Context System

- [ ] Decide whether `#context` should be:
  - [ ] the main authoring surface
  - [ ] a mirror/audit trail only

- [ ] Add a stronger evergreen context workflow for:
  - [ ] party roster
  - [ ] character names
  - [ ] recurring spelling/nomenclature
  - [ ] stable campaign facts

- [ ] Add a stronger session-only context workflow for:
  - [ ] next/current session notes
  - [ ] imported gameplay clarifications
  - [ ] temporary summary guidance

- [ ] Keep DM-private context separate from public summary context
- [ ] Decide whether and when to add `/context_link`

## Deployment / Platform

- [x] Smoke-test the new Docker setup:
  - [x] `docker compose up --build` starts the bot cleanly
  - [x] env loading works inside the container
  - [x] Discord login works from the container
  - [x] offline audio test works inside the container
- [ ] Test Linux audio capture strategy
- [ ] Test Windows audio capture strategy
- [ ] Decide the Docker/device strategy for live voice capture
- [ ] Clarify VPS/server deployment expectations for voice recording

## Product / Feature Work

- [ ] Improve error handling and user-facing failure messages across commands
- [ ] Revisit whether `/reference` should support more attachment/document types
- [ ] Add image generation from summaries
- [ ] Add `/generate image`
- [ ] Add `/create player` / `/create npc` persona flows
- [ ] Consider TTS story output later, with cost/server impact review

## Model / Provider Strategy

- [ ] Compare `gemini-3-flash-preview` vs `gemini-3.1-flash-lite-preview` on real D&D audio
- [ ] Decide whether chat should remain on `gemini-3-flash-preview`
- [ ] Evaluate whether different providers/models should be used later for some tasks

## Cleanup / Documentation

- [ ] Decide whether any additional runtime DB tables are still needed beyond campaign/channel/thread metadata
- [ ] Add a feature map document such as `map.md`
- [ ] Decide whether `PATCH_NOTES.md` and `TODO.md` remain the main project-tracking docs
