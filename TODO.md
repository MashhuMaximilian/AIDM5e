# AIDM TODO

## Next Up

- [ ] Continue workspace-thread polish for `/create npc` and `/create other`
  - [ ] improve when AIDM should stay silent vs acknowledge dropped notes/files
  - [ ] decide whether `Other` needs stronger common-entity prompt examples beyond the current few-shots
  - [ ] decide whether other-workspace metadata ever needs a hidden non-message storage path later

- [ ] Revisit `/create player`
  - [ ] decide product behavior for player brainstorming vs canonical workspace editing
  - [ ] write clean, human-readable campaign context into `#context`
  - [ ] decide how character image references should be attached or linked

- [ ] Extend gameplay sync beyond player sheets
  - [ ] update encounter-local monster state from gameplay
  - [ ] support encounter phase progression, conditions, and resource trackers
  - [ ] decide if any NPC updates should flow back into reusable source threads or stay encounter-local

- [ ] Improve image-generation UX
  - [ ] decide how `/generate image` should evolve for richer source selection
  - [ ] improve user-facing failure messages for image generation
  - [ ] decide whether scene-selection rationale should stay visible, become optional, or move elsewhere

## Voice / Transcript

- [ ] Decide whether to enrich transcript prompts further with the party roster template from `#context`
- [ ] Decide the default audio-summary windowing strategy
- [ ] Decide whether final audio-summary reduction should later receive merged transcript as secondary context
- [ ] Revisit summary prompt instructions for tone, uncertainty, and delivery cues
- [ ] Harden malformed transcript JSON recovery further

## Deployment / Platform

- [ ] Decide the Docker / device strategy for live voice capture
- [ ] Clarify VPS / server deployment expectations for voice recording
- [ ] Design the production deploy flow for `development` -> `main`

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
  - [ ] decide how guild-owned API keys are stored server-side for production use
  - [ ] decide rotation / deletion / fallback behavior when a guild key is missing or revoked

- [ ] Design campaign-level billing / monetization model
  - [ ] decide whether monetization is credit-based or flat monthly
  - [ ] decide whether billing scope is guild-level or campaign-level
  - [ ] decide which settings should be DM-editable vs owner/admin-only

- [ ] Consider later advanced image settings
  - [ ] keep image mode / quality / post channel under campaign settings
  - [ ] decide whether model overrides should ever be user-configurable

## Later

- [ ] Decide product behavior for brainstorming vs strict workspace editing before deployment hardening
- [ ] Consider moving long stable workspace/system prompt bodies into dedicated files under `prompts/`
- [ ] Revisit whether `/reference` should support more attachment/document types
- [ ] Consider whether a separate art / gallery channel is worthwhile
- [ ] Consider TTS story output later, with cost/server impact review
- [ ] Compare `gemini-3-flash-preview` vs `gemini-3.1-flash-lite-preview` on real D&D audio
- [ ] Decide whether chat should remain on `gemini-3-flash-preview`
- [ ] Evaluate whether different providers/models should be used later for some tasks
- [ ] Add a feature map document such as `map.md`
