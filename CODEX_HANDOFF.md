# AIDM Codex Handoff

Use this file to quickly brief a new Codex chat on the current project state.

## Repo and Runtime

- Repo path: `/Users/max/Documents/Max/Projecs and Ideas/Discord AI DM FOR VM`
- Primary stack:
  - Discord bot
  - Gemini API
  - Supabase-backed memory/state
- Current branch: `main`
- `origin/main` is behind local work; there are local commits not yet pushed beyond `3ba06f8`

## Current Local Commit Position

- `013a97d` `Refactor voice transcription and audio-native summaries`
- `a9bfe0a` `Wire separate Gemini chat and summary models`
- `3ba06f8` `(origin/main)` `Refine grouped commands and utility handling`

## Implemented Command Surface

### Grouped commands

- `/ask dm`
- `/ask campaign`
- `/channel start`
- `/channel send`
- `/channel summarize`
- `/channel set_always_on`
- `/memory list`
- `/memory assign`
- `/memory delete`
- `/memory reset`

### Standalone commands

- `/reference`
- `/feedback`
- `/invite`

## Command / Memory Behavior

- Supabase memory assignments are the source of truth.
- Channel/thread deletion should not delete the memory itself.
- `/memory list` supports whole-category overviews and shows unassigned memories.
- `/reference` supports:
  - old Discord messages
  - supported Discord attachments
  - public URLs
- Public URLs use direct fetch first, then Gemini URL Context fallback.
- `/channel send` mirrors transferred content into the target memory.

## Prompt Model

- Shared system prompt is neutral and memory-disciplined.
- `/ask dm` is for official/general D&D rules/lore/mechanics.
- `/ask campaign` is for campaign memory, homebrew, NPCs, inventory, and in-campaign facts.

## Voice / Transcript Model Split

Environment variables now support separate model roles:

- `GEMINI_CHAT_MODEL`
- `GEMINI_TRANSCRIBE_MODEL`
- `GEMINI_SUMMARY_MODEL`
- `GEMINI_TTS_MODEL`

Current intended values:

- `GEMINI_CHAT_MODEL=gemini-3-flash-preview`
- `GEMINI_TRANSCRIBE_MODEL=gemini-3.1-flash-lite-preview`
- `GEMINI_SUMMARY_MODEL=gemini-3-flash-preview`
- `GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts`

## Voice Pipeline Status

### Implemented

- recording uses env-driven `mp3` settings
- default chunk size is `20 min`
- chunk metadata is stored in `transcript_manifest.json`
- each chunk is transcribed into structured JSON
- merged transcript is rebuilt from the manifest
- transcript is posted to `#session-summary`
- transcript is archived to `transcript_archive.txt`
- summaries are generated from audio windows, not only transcript retelling
- summary outputs:
  - objective summary
  - narrative summary
- retention flags exist:
  - `KEEP_AUDIO_FILES`
  - `KEEP_TRANSCRIPT_FILES`

### Current transcript target format

Example:

```text
[00:12:31][IC][Speaker: Max][Character: Solanis][Lang: RO+EN] ...
```

### Open validation areas

- speaker labeling quality
- `IC` / `OOC` / `META` / `UNCLEAR` quality
- `RO` / `EN` / `RO+EN` tagging quality
- whether transcript should later be added as secondary context in the final summary-reduce stage
- whether summary windows should remain `1` chunk or move to `2`
- `.srt` generation is not implemented yet

## Offline Audio Test

There is now an offline runner:

- `/Users/max/Documents/Max/Projecs and Ideas/Discord AI DM FOR VM/offline_audio_test.py`

Example usage:

```bash
python3 offline_audio_test.py "/Users/max/Documents/pyscriptsmacros/scripttranscribe/corpselight sessions archive/Corpselight-Session-4-Pyramid.mp3"
```

Optional output dir:

```bash
python3 offline_audio_test.py "/absolute/path/to/file.mp3" --output-dir "/Users/max/Documents/Max/Projecs and Ideas/Discord AI DM FOR VM/offline_test_outputs"
```

It writes:

- transcript
- objective summary
- narrative summary
- manifest JSON

## Recommended `.env` Audio Block

```env
GEMINI_CHAT_MODEL=gemini-3-flash-preview
GEMINI_TRANSCRIBE_MODEL=gemini-3.1-flash-lite-preview
GEMINI_SUMMARY_MODEL=gemini-3-flash-preview
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts

AUDIO_PROMPT="Transcribe this D&D session audio. Identify speakers if possible. Mix of Romanian and English."
AUDIO_CHUNK_SECONDS=1200
AUDIO_SUMMARY_WINDOW_CHUNKS=1
AUDIO_BITRATE=128k
AUDIO_SAMPLE_RATE=44100
AUDIO_CHANNELS=1
FFMPEG_INPUT_FORMAT=avfoundation
FFMPEG_INPUT_DEVICE=:0

KEEP_AUDIO_FILES=true
KEEP_TRANSCRIPT_FILES=true
```

## Important User Preferences Already Decided

- preserve spoken language as spoken; do not normalize everything to one language
- use `RO`, `EN`, `RO+EN`
- speaker labeling is important but must be best-effort
- use `Unknown` instead of faking certainty
- current priority is in-person single-device recordings
- session start will include each player saying:
  - real name
  - character name
- quality matters more than minimal cost
- transcript should be posted to `#session-summary`
- summaries should also be posted there
- `.srt` can come later
- `/invite` should later also create a session voice channel and support auto-join flow

## Immediate Next Steps

1. Run offline audio test on a real recorded session.
2. Review transcript/speaker/tag quality.
3. Review objective and narrative summary quality.
4. Tune `AUDIO_SUMMARY_WINDOW_CHUNKS` if needed.
5. Add `.srt` generation after transcript quality is acceptable.
