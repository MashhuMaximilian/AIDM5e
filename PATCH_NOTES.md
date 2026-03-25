# AIDM Patch Notes

This file tracks the implemented state of the Gemini + Supabase rewrite and the major design decisions already made.

## Current Architecture

- Gemini is the active LLM provider.
- Supabase-backed campaign/channel/thread metadata is the runtime source of truth.
- Chat transcript rows are no longer persisted in Supabase.
- Discord remains the source of visible history, files, and channel structure.
- Existing Discord attachments are read on demand; they are not blindly copied into long-term memory.
- Local-only artifacts remain out of git and should not drive runtime behavior.
- A first Docker runtime scaffold now exists for the bot.

## Default Campaign Layout

`/invite` currently creates the default text-channel layout:

- `gameplay`
- `telldm`
- `context`
- `session-summary`
- `feedback`
- `npcs`
- `worldbuilding`
- `character-sheets`
- `lore-and-teasers`
- `items`
- `dm-planning`

`/invite` also creates the default voice channel:

- `session-voice`

The intended live flow is that AIDM auto-joins a campaign voice channel when someone joins, including the default session voice channel created by `/invite`.

`/invite` now also posts a starter onboarding message back into the channel where the command was invoked so new campaigns immediately get usage guidance without having to hunt through the scaffold.
If `/invite` is run outside a category, it now creates a new category automatically and scaffolds the campaign there.

## Prompt System

- Prompt system is centralized under `/Users/max/Documents/Max/Projecs and Ideas/Discord AI DM FOR VM/prompts/`.
- Shared system prompt was rewritten to be:
  - neutral
  - memory-disciplined
  - Discord-aware
- Query, summary, feedback, reference, and transcript prompts were redesigned.
- `/ask dm` is positioned for general D&D rules/lore/mechanics knowledge.
- `/ask campaign` is positioned for campaign memory, homebrew, NPCs, inventory, and applied in-campaign facts.

## Retrieval and Context

- `/channel summarize` can read selected historical Discord attachments.
- `/reference` can read:
  - selected messages
  - supported attachments
  - public URLs
- Public URL reading uses direct fetch first and Gemini URL Context as fallback.
- Google Docs / Sheets remain out of scope for now.
- `/context add` stores transcript/summary support context in three scopes:
  - public evergreen
  - session-only
  - DM-private
- Added clearer Phase 1 context commands:
  - `/context add`
  - `/context clear`
  - `/context list`
- `#context` is the human-facing public/session authoring surface, while `#dm-planning` remains the DM-private surface.
- `/context add` and `/context clear` now publish canonical managed context entries directly into those Discord channels.
- `/context list` now shows the effective compiled context state so you can sanity-check what transcript/summary runs will consume.
- Live voice transcript/summary runs now use compiler-built Discord context packets instead of falling back to local files.
- Local files under `voice_context/` remain only for explicit offline override runs.
- Session-only context now has an explicit lifecycle rule: it stays active until you replace it or clear it; it does not expire automatically.
- Managed context entries can now preserve image attachment references from selected Discord messages, along with optional human-friendly tags.
- The current long-term direction remains: Discord messages and attachments are the durable context source of truth, runtime packets are compiled in memory, and context payloads are not stored in Supabase.

## Commands and Memory UX

- Slash commands were regrouped into domain-based groups:
  - `/ask`
  - `/channel`
  - `/memory`
- Added `/help` as a topic-based onboarding command for grouped commands, `/invite`, and campaign setup flow.
- `/help topic:Context` reflects the `/context add|clear|list` workflow.
- `/context summary` was removed after the transition to `/context add`.
- Standalone commands remain:
  - `/reference`
  - `/feedback`
  - `/invite`
- Memory inspection now supports:
  - single-target inspection
  - whole-category overview
  - grouped display by memory
  - thread inheritance vs thread override display
  - unassigned memory visibility
- `/channel send` now mirrors transferred content into the target memory and posts a short acknowledgment there.
- `/channel send` no longer writes transferred content into a Supabase transcript-history table.
- `/memory reset` no longer clears Supabase chat transcript rows because that storage path has been removed.
- Dense list formatting was normalized for Discord output.
- Utility command error handling was improved and old command duplication issues were cleaned up.
- Command registration was modularized out of `discord_app/bot_commands.py` into command-group modules under `/Users/max/Documents/Max/Projecs and Ideas/Discord AI DM FOR VM/discord_app/commands/`.
- Any incoming message that contains a public URL can now trigger the same fetch-first URL reading path that `/reference` uses.

## Workspace Threads

- Added `/create npc` and `/create other` workspace scaffolding.
- `/create npc` creates workspace threads under `#npcs` and assigns a dedicated NPC memory to the thread.
- `/create other` creates workspace threads under `#worldbuilding` and reuses the parent channel's `worldbuilding` memory.
- NPC/Other workspace cards are created as blank cards and are no longer auto-filled immediately after thread creation.
- Workspace card updates now:
  - work even when Discord pinning fails
  - fall back to thread history/embed discovery instead of using pins as the source of truth
  - support broad requests like "update the cards"
  - read PDF, text, DOCX, and image attachments more reliably when Discord omits content types
- Workspace welcome messages for NPC/Other no longer need to expose the raw internal metadata block to the user.
- Always-on message handling now ignores Discord system messages such as pin notifications.
- Typing indicators for workspace and thread replies now target the active thread instead of the parent channel.

## Model Configuration

The codebase now supports separate Gemini model roles:

- `GEMINI_CHAT_MODEL`
- `GEMINI_TRANSCRIBE_MODEL`
- `GEMINI_SUMMARY_MODEL`
- `GEMINI_TTS_MODEL`
- `GEMINI_IMAGE_MODEL`
- `GEMINI_IMAGE_HQ_MODEL`
- `GEMINI_IMAGE_DEFAULT_ASPECT_RATIO`

Current intended configuration:

- chat: `gemini-3-flash-preview`
- transcript: `gemini-3.1-flash-lite-preview`
- summary: `gemini-3-flash-preview`
- future TTS: `gemini-2.5-flash-preview-tts`
- default image: `gemini-3.1-flash-image-preview`
- optional HQ image: `gemini-3-pro-image-preview`

## Voice / Transcript Pipeline

The old transcript flow has been substantially refactored.

### Recording

- audio recording is now configured around `mp3`
- default chunk length is `1200` seconds (`20 min`)
- audio settings are env-driven:
  - chunk seconds
  - bitrate
  - sample rate
  - channels
  - ffmpeg input format
  - ffmpeg input device

### Structured Transcript Capture

- each recorded chunk is tracked in `transcript_manifest.json`
- each chunk is transcribed through Gemini into structured JSON
- transcript segments now target:
  - best-effort timestamp
  - `IC` / `OOC` / `META` / `RULES` / `COMBAT` / `UNCLEAR`
  - recurring `Unknown 1` / `Unknown 2` / `Unknown 3` style room-audio speaker labels
  - cautious character attribution, including `MAYBE <name>` style fallbacks when needed
- transcript prompting now uses:
  - stronger single-device/in-person guidance
  - session-start introduction handling when present
  - chunk-local `roster_hints` for later chunks
- public and session context can now be mined for roster candidates such as `Phil playing Kogone`, which are fed back into transcript prompting as identification aids

## Database Lifecycle

- Deleting a Discord category now explicitly removes the associated campaign data from the runtime database:
  - campaign
  - memories
  - channel assignments
  - thread assignments
  - channels
  - threads
- Orphaned guild rows are also cleaned up when the deleted category was the guild's last campaign.
- Category deletion now also uses the stored campaign channel/thread IDs to delete leftover Discord child channels, so they do not remain uncategorized in the server UI.

## Docker / Deployment

- Added:
  - `/Users/max/Documents/Max/Projecs and Ideas/Discord AI DM FOR VM/Dockerfile`
  - `/Users/max/Documents/Max/Projecs and Ideas/Discord AI DM FOR VM/.dockerignore`
  - `/Users/max/Documents/Max/Projecs and Ideas/Discord AI DM FOR VM/docker-compose.yml`
- The Docker image includes:
  - Python 3.11
  - `ffmpeg`
  - voice-related native dependencies needed by the current bot stack
- The compose setup mounts runtime artifacts from the project directory so transcripts, audio files, and context files survive container restarts.
- The current Docker setup is suitable for:
  - bot runtime
  - offline audio processing
- Live host-audio capture in Docker is still treated as a Linux-specific follow-up, not a solved macOS Docker Desktop workflow.
  - speaker
  - character when clear
  - `RO` / `EN` / `RO+EN`
- the final session transcript is rebuilt from the manifest
- timestamp normalization now repairs mixed-baseline Gemini offsets before the final session transcript is merged

### Audio-Native Summary Flow

- summary generation is no longer based only on transcript retelling
- audio files are grouped into summary windows
- those windows are summarized directly from audio
- final outputs are reduced into:
  - objective summary
  - narrative summary

### Session Image Flow

- Added a product-phase image pipeline that works without storing scenes in Supabase.
- Scene candidates are derived in memory from:
  - objective summary
  - narrative summary
  - compiled Discord context packet
- The number of generated scenes is dynamic rather than fixed.
- Final image prompts are built from:
  - a reusable D&D-style house block
  - optional campaign style shift from context
  - scene-specific visual instructions
- Image generation now supports:
  - automated post-session generation after summaries
  - manual `/generate image`
- `/settings images` controls per-campaign automated behavior:
  - `mode`
  - `quality`
  - `max_scenes`
  - `include_dm_context`
  - `post_channel`
- `/generate image` supports:
  - latest summary
  - selected message IDs
  - last N messages
  - custom prompt
  - extra `directives`
  - quality and aspect-ratio overrides
- Quality routing is app-controlled:
  - `fast` -> Flash image model
  - `hq` -> Pro image model
  - `auto` -> policy-based selection
- Aspect ratio is chosen per scene, with `GEMINI_IMAGE_DEFAULT_ASPECT_RATIO` as the fallback.

### Transcript Outputs

- transcript file is posted to `#session-summary`
- transcript text is appended to `transcript_archive.txt`
- retention flags now exist:
  - `KEEP_AUDIO_FILES`
  - `KEEP_TRANSCRIPT_FILES`

### Offline Audio Testing

- an offline runner now exists:
  - `/Users/max/Documents/Max/Projecs and Ideas/Discord AI DM FOR VM/offline_audio_test.py`
- it can process existing audio files, including files outside the repo
- long source recordings are now split into chunk-sized temporary segments using `AUDIO_CHUNK_SECONDS` so offline tests better mirror the live pipeline
- it outputs:
  - transcript
  - objective summary
  - narrative summary
  - manifest JSON
- it can now also optionally run the image pipeline after summaries via:
  - `--generate-images`
  - `--image-quality`
  - `--image-aspect-ratio`
  - `--image-max-scenes`
  - `--image-ref`
- added a dedicated offline image runner:
  - `/Users/max/Documents/Max/Projecs and Ideas/Discord AI DM FOR VM/offline_image_test.py`
  - this can test summary -> scene -> image flow without rerunning transcription

## Local-Only Artifacts

These stay local and should not drive runtime behavior:

- `threads.json`
- `transcript.txt`
- `transcript_manifest.json`
- `transcript_archive.txt`
- `audio_files/`
- `offline_test_outputs/`
- local sourcebooks and personal references under `sources/`
- local migration helpers under `scripts/`

## Notable Local Commits Since `origin/main`

- `4d736bb` `Polish command UX and memory overview`
- `2616d95` `Refine utility commands and project notes`
- `3ba06f8` `Refine grouped commands and utility handling`
- `a9bfe0a` `Wire separate Gemini chat and summary models`
- `013a97d` `Refactor voice transcription and audio-native summaries`
- `d1bfc97` `Refactor voice pipeline and add summary context workflow`
- `aa07b92` `Harden chunk-local transcript timestamp repair`
- `2465f18` `Add context channel mirroring and invite voice scaffold`
- `4269575` `Stop tracking Codex handoff notes`
- `f80cbf6` `Remove transcript row storage and tighten context cleanup`
- `dc0c150` `Remove migration shims after package reorg`
- `5bb2d65` `Normalize chunk-relative transcript timestamps`
- `a5af6b9` `Improve speaker and roster transcript handling`

## Next Major Focus

The next major work area is validating and tuning the rebuilt voice pipeline with:

- offline real-session audio
- live Discord voice tests
- summary window tuning
- transcript/speaker/tag quality review
- later `.srt` generation
