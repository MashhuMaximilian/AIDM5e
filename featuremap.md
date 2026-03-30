# AIDM Feature Map

This file is a high-level map of the currently implemented product surface.
It is meant to answer: what features exist, where they live, and what still counts as validation or later expansion rather than missing implementation.

## Core Campaign Scaffold

`/invite` creates a campaign category scaffold with:

- public channels:
  - `#help`
  - `#gameplay`
  - `#telldm`
  - `#context`
  - `#session-summary`
  - `#feedback`
  - `#npcs`
  - `#worldbuilding`
  - `#character-sheets`
  - `#lore-and-teasers`
  - `#items`
- DM-private channels:
  - `#dm-planning`
  - `#monsters`
  - `#encounters`
- voice:
  - `session-voice`

`/invite` also:
- initializes default campaign memories
- posts a structured onboarding/help guide into `#help`
- posts an AI greeting in `#help`
- includes a Party Voice Roster Template in the help guide

## Help / Onboarding

`#help` is:
- `always_on = ON`
- guided by a dedicated onboarding/support system prompt

`/help topic:<name>` currently covers:
- invite
- create
- context
- settings
- ask
- channel
- generate
- memory
- reference
- feedback

## Context / Memory

Context is managed through Discord-first surfaces:
- `#context`
- `#dm-planning`

Commands:
- `/context add`
- `/context clear`
- `/context list`

Scopes:
- public evergreen
- session-only
- DM-private

Memory behavior includes:
- channel memory assignment
- thread memory assignment
- always-on support for channels and threads
- memory inspection/reset flows

## BYOK / Global API Keys

Guild-scoped BYOK is implemented for Gemini.

Command surface:
- `/settings global set-api-key`
- `/settings global rotate-api-key`
- `/settings global api-key-status`
- `/settings global remove-api-key`

Behavior:
- key ownership is per guild
- management is owner/admin-only
- no creator-hosted fallback key is used for guild traffic
- missing key returns setup instructions
- invalid key fails gracefully

Storage/runtime model:
- guild keys are stored in Supabase/Postgres
- keys are encrypted at rest
- one app-level master encryption key is supplied by runtime config
- runtime key resolution is guild-aware

Runtime coverage:
- normal assistant replies
- player workspace creation/import
- custom workspace prepass
- encounter snapshot updates
- image generation
- live/offline voice transcription and session-image flows

## Workspace System

General workspace model:
- cards are the official record
- conversation is the workshop
- cards are pinned embeds inside workspace threads
- AIDM can update one card or multiple cards
- natural card targeting is supported better than before

Implemented workspace types:
- player
- npc
- other
- monster
- encounter

### Player Workspace

Command:
- `/create player`

Location:
- threads under `#character-sheets`

Pipeline:
- markdown-first create/import flow
- idea mode
- import mode from notes/files/messages
- card splitting into managed slots
- one canonical workspace thread by default
- conversational-by-default workshop behavior inside the thread
- explicit update/apply/sync wording controls card edits
- brainstorming should stay conversational and AIDM should suggest card updates when something sounds settled

Managed player cards:
- Character Summary
- Profile Card
- Skills & Actions
- Rules Card
- Items Card
- Reference Links

### NPC Workspace

Command:
- `/create npc`

Location:
- threads under `#npcs`

Default cards:
- Summary Card
- Profile Card
- Personality & Hooks
- Stat Block
- Relationships

### Other Workspace

Command:
- `/create other`

Location:
- threads under `#worldbuilding`

Behavior:
- custom card inventory designed by prepass prompt
- reusable for locations, factions, quests, spells, items, and other campaign entities

### Monster Workspace

Command:
- `/create monster`

Location:
- DM-private threads under `#monsters`

Purpose:
- reusable combat-first creature source sheet
- supports canon, homebrew, imported, and mixed variants

Default cards:
- Summary Card
- Core Stat Block
- Traits, Magic & Features
- Actions, Reactions & Legendary
- Tactics, Phases & Scaling
- Lore, Hooks & Variants

### Encounter Workspace

Command:
- `/create encounter`

Location:
- DM-private threads under `#encounters`

Purpose:
- DM-only encounter planning / scripting / balancing workspace

Default cards:
- Summary Card
- Enemy Roster
- Balance & Threat
- Battlefield & Hazards
- Phases, Scripts & Triggers
- Outcome, Rewards & Aftermath

### Encounter Helpers

Command group:
- `/encounter add`

Current behavior:
- run inside an encounter thread
- snapshots a monster or NPC source thread into the encounter
- updates roster/balance cards without live sync back to the source thread

## Gameplay -> Workspace Sync

When AIDM replies in `#gameplay`, it can run a second extraction pass and push updates into character workspaces.

Auto-safe updates currently target player workspaces for:
- HP damage / healing
- temporary HP
- conditions
- exhaustion
- hit dice
- similar explicit transient combat-state changes

Confirmation-first updates:
- inventory/items
- spells known/prepared
- level-up
- major canon/build/profile changes

If a player workspace thread does not exist:
- AIDM can create a lightweight tracker thread under `#character-sheets`

Later expansion:
- encounter-local monster/NPC state updates

## Voice / Transcript Pipeline

Voice recording:
- chunked recording
- transcript manifest tracking
- Gemini structured transcription

Supports:
- fallback room/audio capture flow
- Discord per-user stream capture when `discord-ext-voice-recv` is available

Speaker attribution:
- can use Discord username as upstream speaker hint
- supports uncertainty labels like `Name (possibly multiple speakers)` when needed
- transcript rebuild merges per-user chunks by absolute time

Outputs:
- final transcript
- objective summary
- narrative summary
- posts to `#session-summary`

Archive flow:
- uploads session audio + transcript artifacts to Supabase Storage for the configured guild
- then cleans up local files

## Image Pipeline

Commands / settings:
- `/generate image`
- `/settings images`

Current image system:
- one-off image generation
- campaign-level image settings
- image prompting informed by compiled Discord context
- post-session image flow exists in current architecture

## Reference / Retrieval

Commands:
- `/reference`
- `/ask dm`
- `/ask campaign`
- `/channel summarize`

Supported sources:
- selected messages
- attachments
- public URLs

URL flow:
- direct fetch first
- Gemini URL-context fallback

## Settings Surface

Currently implemented:
- `/settings images`

Planned/partially designed:
- `/settings campaign`
- `/settings global`
- BYOK / per-guild API-key support

## Deployment / Runtime

Current state:
- Dockerfile exists
- docker-compose exists
- voice-related runtime dependencies are containerized
- current Docker setup is suitable for bot runtime and offline processing

Not yet fully hardened:
- production secret management
- deployment flow to Hetzner
- persistent volume strategy
- CI/CD promotion from `development` to `main`

## Current Big Design Topics

Still intentionally unresolved:
- BYOK storage model
- final player workspace behavior:
  - one thread with smarter mode switching
  - or two-thread brainstorm/canon split
- production deployment hardening on Hetzner
