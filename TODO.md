# AIDM TODO

## Current Status

- [x] Voice pipeline refactored into dedicated packages under `voice/`
- [x] Offline audio test runner added and long files split by `AUDIO_CHUNK_SECONDS`
- [x] Audio-native summary flow implemented
- [x] Transcript timestamps repaired enough for current Gemini-based testing
- [x] `/invite` creates the default text-channel scaffold
- [x] `/invite` creates `session-voice`
- [x] `/invite` creates `#context`
- [x] `/invite` posts onboarding guidance back into the channel where it was invoked
- [x] `/help` exists as a topic-based command for onboarding and grouped command discovery
- [x] `/context add` and `/context clear` publish canonical managed context entries into Discord
- [x] `/context list` shows the effective compiled context state
- [x] `/context summary` removed from the command surface after the `/context add` transition
- [x] `/settings images` exists for per-campaign automatic image-generation behavior
- [x] `/generate image` exists for manual image generation from summaries, selected messages, or a custom prompt
- [x] Offline image test runner exists
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

- [x] Improve speaker labeling for in-person single-device recordings
- [x] Use session-start roster introduction more explicitly in transcript prompts
- [x] Add explicit `RULES` / `COMBAT` transcript modes
- [x] Use public/session context to derive roster candidates such as `Phil playing Kogone`
- [x] Carry forward chunk-level roster hints to later transcript chunks
- [ ] Keep testing `AUDIO_SUMMARY_WINDOW_CHUNKS=1` vs `2`
- [ ] Decide whether final audio-summary reduction should later receive merged transcript as secondary context
- [ ] Revisit summary prompt instructions for tone, uncertainty, and delivery cues
- [ ] Add `.srt` generation from the structured transcript data
- [ ] Harden malformed transcript JSON recovery further
- [ ] Add offline support for `.m4a` inputs or conversion helpers

## Context System

- [x] Phase 0:
  - [x] `/help` explains grouped commands and context usage
  - [x] `/invite` posts campaign onboarding in the invoking channel

- [ ] Phase 1: Discord-native context workflow
  - [x] Treat `#context` as the main human authoring surface
  - [x] Treat `#dm-planning` as the DM-private authoring surface
  - [x] Clarify `Public Evergreen` vs `Session Only` vs `DM Private` behavior in command UX
  - [x] Add clearer command entrypoints with `/context add`, `/context clear`, and `/context list`
  - [x] Remove `/context summary` after the transition to `/context add`
  - [x] Keep session context easy to replace/clear manually instead of guessing expiration dates

- [ ] Phase 2: Context compilation without DB payload storage
  - [x] Use Discord-managed context messages as the preferred source of truth for context
  - [x] Avoid storing context text/image payloads in Supabase
  - [x] Compile transcript context packets in memory from Discord-managed context entries
  - [x] Compile summary context packets in memory from Discord-managed context entries
  - [x] Remove the live/runtime local-file fallback under `voice_context/`
  - [x] Keep session context manual: it remains active until explicitly replaced or cleared
  - [ ] Decide how much explicit offline file override support should remain long-term

- [ ] Phase 3: Image-aware context
  - [x] Support image references from `#context` / `#dm-planning` in the compiled context flow
  - [x] Clarify how text descriptions and image references should be combined for later scene generation
  - [x] Define optional user-facing tags/examples without making them mandatory
  - [x] Expose compiled image-aware context to the future scene/image generation pipeline

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
- [x] Add image generation from summaries
- [x] Add `/generate image`
- [x] Add automated post-session image generation controlled by `/settings images`
- [x] Add offline image testing from summaries and from the offline audio pipeline
- [ ] Test the new Discord context workflow end-to-end against the image pipeline
- [ ] Decide how `/generate image` should evolve for richer message/source selection UX
- [ ] Add `/create player` / `/create npc` persona flows
- [ ] Consider TTS story output later, with cost/server impact review
- [ ] Consider whether a separate art/gallery channel is worthwhile later

## Model / Provider Strategy

- [ ] Compare `gemini-3-flash-preview` vs `gemini-3.1-flash-lite-preview` on real D&D audio
- [ ] Decide whether chat should remain on `gemini-3-flash-preview`
- [ ] Evaluate whether different providers/models should be used later for some tasks

## Cleanup / Documentation

- [ ] Decide whether any additional runtime DB tables are still needed beyond campaign/channel/thread metadata
- [ ] Add a feature map document such as `map.md`
- [ ] Decide whether `PATCH_NOTES.md` and `TODO.md` remain the main project-tracking docs
