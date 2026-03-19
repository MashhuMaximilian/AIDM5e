# AIDM

AIDM is a Discord bot for running and organizing tabletop RPG campaigns. It combines:

- grouped campaign/rules commands
- channel and thread memory assignment
- transcript and recap generation from voice sessions
- Discord-native campaign context management
- offline and Docker-friendly voice testing

The current stack uses Gemini for chat, transcript, and summary work, with Supabase storing campaign/channel/thread metadata only.

## Quick Start

### Local

```bash
git clone https://github.com/MashhuMaximilian/AIDM5e.git
cd AIDM5e
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 aidm.py
```

### Docker

```bash
docker compose up --build -d
docker compose logs -f
docker compose down
```

Docker is a good fit for:

- normal bot runtime
- command testing
- offline audio processing

Live host-audio capture in Docker is mainly a Linux deployment problem. macOS Docker Desktop is fine for bot runtime and offline tests, but not the final answer for host microphone/system-audio capture.

## Required Environment

At minimum, configure:

```env
DISCORD_BOT_TOKEN=
DISCORD_CLIENT_ID=
DISCORD_GUILD_ID=
DM_ROLE_NAME=Dungeon Master

GEMINI_API_KEY=
GEMINI_CHAT_MODEL=gemini-3-flash-preview
GEMINI_TRANSCRIBE_MODEL=gemini-3.1-flash-lite-preview
GEMINI_SUMMARY_MODEL=gemini-3-flash-preview
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts
GEMINI_IMAGE_MODEL=gemini-3.1-flash-image-preview
GEMINI_IMAGE_HQ_MODEL=gemini-3-pro-image-preview
GEMINI_IMAGE_DEFAULT_ASPECT_RATIO=4:3

DIRECT_CONNECTION_STRING=
# or the SUPABASE_DB_* variables instead
```

## Voice / Audio Settings

Current defaults:

```env
AUDIO_PROMPT="Transcribe this D&D session audio. The speakers may switch between Romanian and English, sometimes in the same exchange. Identify speakers if possible."
AUDIO_CHUNK_SECONDS=1200
AUDIO_SUMMARY_WINDOW_CHUNKS=1
AUDIO_BITRATE=128k
AUDIO_SAMPLE_RATE=44100
AUDIO_CHANNELS=1
KEEP_AUDIO_FILES=false
KEEP_TRANSCRIPT_FILES=false
VOICE_INCLUDE_DM_CONTEXT=false
```

### FFMPEG input configuration

Use host-appropriate ffmpeg capture settings. Example for macOS:

```env
# FFMPEG configuration for audio capture (macOS example)
# Linux might use pulse or alsa | Windows might use dshow
FFMPEG_INPUT_FORMAT=avfoundation
FFMPEG_INPUT_DEVICE=:0
```

Notes:

- `AUDIO_BITRATE`, `AUDIO_SAMPLE_RATE`, and `AUDIO_CHANNELS` control the recorded audio encoding.
- The macOS defaults above are appropriate for local testing on a Mac.
- Linux and Windows will usually need different capture backends and device names.

## Campaign Setup Flow

1. Create a Discord category for the campaign.
2. Create one starter text channel inside that category.
3. Run `/invite` in that channel.
4. Read the onboarding message that AIDM posts back in the invoking channel.
5. Run `/help topic:Context`.
6. Add party roster, spelling fixes, and session guidance with `/context add`.

`/invite` creates the default scaffold:

- `#gameplay`
- `#telldm`
- `#context`
- `#session-summary`
- `#feedback`
- `#npcs`
- `#character-sheets`
- `#lore-and-teasers`
- `#items`
- `#dm-planning`
- `session-voice`

## Command Surface

Grouped commands:

- `/ask`
- `/channel`
- `/memory`
- `/context`
- `/settings`
- `/generate`

Standalone commands:

- `/help`
- `/reference`
- `/feedback`
- `/invite`

Use `/help` with a topic for the current workflow. The most important topics are:

- `/help topic:Invite`
- `/help topic:Context`
- `/help topic:Settings`
- `/help topic:Ask`

## Context Model

Context is Discord-native.

Source of truth:

- `#context` for public and session context
- `#dm-planning` for DM-private context

Supabase does **not** store context payloads such as text or images.

### Context scopes

- `Public Evergreen`
  - long-lived campaign facts
  - roster, spellings, factions, locations, stable continuity
- `Session Only`
  - current or next-session guidance
  - active until you explicitly replace or clear it
  - there is no automatic expiry
- `DM Private`
  - DM-only context
  - excluded from player-facing runs unless explicitly enabled

### Context commands

- `/context add`
- `/context clear`
- `/context list`
- `/context summary` (legacy alias)

Recommended usage:

```text
/context add scope:Public Evergreen action:Append note:<party roster> tags:roster,spelling
/context add scope:Session Only action:Replace channel:#gameplay last_n:20
/context clear scope:Session Only
```

### Image-aware context

When `/context add` ingests selected Discord messages:

- text content is preserved in the managed context entry
- image attachments are preserved as image references
- non-image readable attachments are still text-extracted when possible
- tags are optional and human-friendly

Good starter tags:

- `roster`
- `character`
- `npc`
- `location`
- `item`
- `spelling`
- `scene`
- `style`
- `visual-reference`

Tags are optional. They help later scene/image workflows, but basic usage should not depend on them.

## Image Generation

There are now two image-generation paths:

- automated post-session image generation after voice summaries
- manual `/generate image` runs

### Automated campaign image settings

Use `/settings images` per campaign/category to control:

- `mode`: `off` or `auto`
- `quality`: `auto`, `fast`, or `hq`
- `max_scenes`: optional cap for automatic image count
- `include_dm_context`: whether DM-private context can influence automatic images
- `post_channel`: where the generated images are posted

Creative style should stay in `#context` / `#dm-planning`, not in `/settings`.

### Manual image generation

`/generate image` supports:

- `source_mode: latest_summary`
- `source_mode: message_ids`
- `source_mode: last_n`
- `source_mode: custom_prompt`
- optional `directives`
- optional `quality`
- optional `aspect_ratio`
- optional message/image references from selected Discord messages

For manual generation, `quality` controls model policy:

- `fast` -> `GEMINI_IMAGE_MODEL`
- `hq` -> `GEMINI_IMAGE_HQ_MODEL`
- `auto` -> app decides based on scene/reference complexity

For automated generation, aspect ratio is chosen per scene, with `GEMINI_IMAGE_DEFAULT_ASPECT_RATIO` used as a fallback.

## Voice Pipeline

The voice pipeline currently does this:

1. records chunked audio
2. transcribes each chunk into structured JSON
3. rebuilds a merged session transcript
4. produces audio-native objective and narrative summaries
5. posts outputs to `#session-summary`

Transcript mode labels currently include:

- `IC`
- `OOC`
- `META`
- `RULES`
- `COMBAT`
- `UNCLEAR`

The transcript flow uses:

- recurring `Unknown 1`, `Unknown 2`, `Unknown 3` style speaker labels
- cautious character attribution such as `MAYBE <name>`
- roster hints derived from earlier chunks and campaign context

## Offline Audio Testing

You can test existing audio files without a live Discord session:

```bash
python3 offline_audio_test.py "/absolute/path/to/session.mp3" --output-dir "/absolute/path/to/output"
```

Optional explicit offline context overrides still exist:

```bash
python3 offline_audio_test.py "/absolute/path/to/session.mp3" \
  --public-context "/absolute/path/to/public.txt" \
  --session-context "/absolute/path/to/session.txt" \
  --dm-context "/absolute/path/to/dm.txt" \
  --include-dm-context
```

### Offline image testing

You can test scene extraction and image generation directly from existing summaries:

```bash
python3 offline_image_test.py \
  "/absolute/path/to/objective_summary.md" \
  "/absolute/path/to/narrative_summary.md" \
  --output-dir "/absolute/path/to/output" \
  --quality auto
```

To test the full offline audio -> summary -> image path in one run:

```bash
python3 offline_audio_test.py "/absolute/path/to/session.mp3" \
  --output-dir "/absolute/path/to/output" \
  --generate-images \
  --image-quality auto
```

These file overrides are for explicit offline runs only. Live runtime context now comes from compiled Discord-managed context entries.

## Runtime Artifacts

Common local runtime artifacts:

- `audio_files/`
- `offline_test_outputs/`
- `transcript.txt`
- `transcript_manifest.json`
- `transcript_archive.txt`

These are runtime artifacts, not campaign source of truth.

## Current Design Direction

The current context/runtime direction is:

- Discord messages and attachments are the durable context source of truth
- context packets are compiled in memory at runtime
- Supabase stores metadata, not context payloads
- future image generation will consume compiled text + image references from context

## Contributing

Recommended workflow:

```bash
git checkout -b your-feature-name
```

Keep changes focused, test what you touch, and prefer updating the docs when a workflow or command surface changes.
