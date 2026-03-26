# AIDM TODO

## Next Up

- [ ] Continue workspace-thread polish for `/create npc` and `/create other`
  - [ ] validate card updates from mixed file types in real Discord threads
  - [ ] keep improving when AIDM should stay silent vs acknowledge dropped notes/files
  - [ ] test card targeting against natural phrases instead of exact card titles
  - [ ] decide whether `Other` needs stronger common-entity examples beyond the current prompt few-shots
  - [ ] decide whether other-workspace metadata ever needs a hidden non-message storage path later

- [ ] Revisit `/create player`
  - [ ] validate the new markdown-first import/idea pipeline with real character sheets
  - [ ] test heading/slot mapping against messy Gemini output from real PDFs
  - [ ] verify summary card consistency on import:
    - [ ] HP bar
    - [ ] AC / DC / PB / speed snapshot
    - [ ] hit dice
    - [ ] player name fallback
  - [ ] decide product behavior for player brainstorming vs canonical workspace editing
  - [ ] write clean, human-readable campaign context into `#context`
  - [ ] decide how character image references should be attached or linked

- [ ] Test the Discord-native context workflow end-to-end against the image pipeline
  - [ ] use real `#context` character descriptions and image references
  - [ ] verify scene selection quality against existing summaries
  - [ ] verify that generated images stay grounded in campaign context
  - [ ] identify where missing prior-session context still hurts image quality

- [ ] Improve image-generation UX
  - [ ] decide how `/generate image` should evolve for richer source selection
  - [ ] improve user-facing failure messages for image generation
  - [ ] decide whether scene-selection rationale should stay visible, become optional, or move elsewhere

## Voice / Transcript

- [ ] Keep testing `AUDIO_SUMMARY_WINDOW_CHUNKS=1` vs `2`
- [ ] Decide whether final audio-summary reduction should later receive merged transcript as secondary context
- [ ] Revisit summary prompt instructions for tone, uncertainty, and delivery cues
- [ ] Harden malformed transcript JSON recovery further

## Live Voice Validation

- [ ] Live-test the rebuilt voice pipeline in Discord voice on Linux
  - [ ] recording lifecycle
  - [ ] bot auto-join behavior
  - [ ] bot auto-leave / finalization behavior
  - [ ] transcript posting to `#session-summary`
  - [ ] objective summary posting
  - [ ] narrative summary posting
  - [ ] retention flag behavior with `KEEP_AUDIO_FILES` / `KEEP_TRANSCRIPT_FILES`

## Deployment / Platform

- [ ] Test Linux audio capture strategy
- [ ] Test Windows audio capture strategy
- [ ] Decide the Docker / device strategy for live voice capture
- [ ] Clarify VPS / server deployment expectations for voice recording

## Settings / Billing

- [ ] Expand `/settings` beyond `/settings images`
  - [ ] define `/settings campaign`
  - [ ] define `/settings global`

- [ ] Keep settings split by responsibility
  - [ ] app defaults stay in `.env`
  - [ ] campaign behavior belongs in `/settings campaign`
  - [ ] creative style guidance stays in `#context` rather than `/settings`

- [ ] Design creator-hosted API key support
  - [ ] decide whether API keys attach per guild or per campaign
  - [ ] likely handle this under `/settings global` for guild-level ownership
  - [ ] decide how the runtime resolves which key to use for a given request

- [ ] Design campaign-level billing / monetization model
  - [ ] decide whether monetization is credit-based or flat monthly
  - [ ] decide whether billing scope is guild-level or campaign-level
  - [ ] decide which settings should be DM-editable vs owner/admin-only

- [ ] Consider later advanced image settings
  - [ ] keep image mode / quality / post channel under campaign settings
  - [ ] decide whether model overrides should ever be user-configurable

## Later

- [ ] Consider moving long stable workspace/system prompt bodies into dedicated files under `prompts/`
- [ ] Revisit whether `/reference` should support more attachment/document types
- [ ] Consider whether a separate art / gallery channel is worthwhile
- [ ] Consider TTS story output later, with cost/server impact review
- [ ] Compare `gemini-3-flash-preview` vs `gemini-3.1-flash-lite-preview` on real D&D audio
- [ ] Decide whether chat should remain on `gemini-3-flash-preview`
- [ ] Evaluate whether different providers/models should be used later for some tasks
- [ ] Add a feature map document such as `map.md`
