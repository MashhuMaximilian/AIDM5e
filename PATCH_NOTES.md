# AIDM Patch Notes

This file tracks the implemented state of the Gemini + Supabase rewrite and the major design decisions already made.

## Current Architecture

- Gemini is the active LLM provider.
- Supabase-backed app-owned memories are the runtime source of truth.
- Discord remains the source of visible history, files, and channel structure.
- Existing Discord attachments are read on demand; they are not blindly copied into long-term memory.
- Local-only artifacts remain out of git and should not drive runtime behavior.

## Default Campaign Layout

`/invite` currently creates the default text-channel layout:

- `gameplay`
- `telldm`
- `session-summary`
- `feedback`
- `npcs`
- `character-sheets`
- `lore-and-teasers`
- `items`
- `dm-planning`

Planned next:
- add a default session voice channel and auto-join flow for AIDM.

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

## Commands and Memory UX

- Slash commands were regrouped into domain-based groups:
  - `/ask`
  - `/channel`
  - `/memory`
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
- Dense list formatting was normalized for Discord output.
- Utility command error handling was improved and old command duplication issues were cleaned up.

## Model Configuration

The codebase now supports separate Gemini model roles:

- `GEMINI_CHAT_MODEL`
- `GEMINI_TRANSCRIBE_MODEL`
- `GEMINI_SUMMARY_MODEL`
- `GEMINI_TTS_MODEL`

Current intended configuration:

- chat: `gemini-3-flash-preview`
- transcript: `gemini-3.1-flash-lite-preview`
- summary: `gemini-3-flash-preview`
- future TTS: `gemini-2.5-flash-preview-tts`

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
  - `IC` / `OOC` / `META` / `UNCLEAR`
  - speaker
  - character when clear
  - `RO` / `EN` / `RO+EN`
- the final session transcript is rebuilt from the manifest

### Audio-Native Summary Flow

- summary generation is no longer based only on transcript retelling
- audio files are grouped into summary windows
- those windows are summarized directly from audio
- final outputs are reduced into:
  - objective summary
  - narrative summary

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

## Next Major Focus

The next major work area is validating and tuning the rebuilt voice pipeline with:

- offline real-session audio
- live Discord voice tests
- summary window tuning
- transcript/speaker/tag quality review
- later `.srt` generation
