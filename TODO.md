# AIDM TODO

## Now

- [ ] Live-test the recently updated command UX:
  - [ ] `/tellme`
  - [ ] `/askdm`
  - [ ] `/reference`
  - [ ] `/listmemory`
  - [ ] `/feedback`
- [ ] Live-test the remaining utility commands end-to-end:
  - [ ] `/delete_memory`
  - [ ] `/reset_memory`
  - [ ] `/send`
  - [ ] `/startnew`
  - [ ] `/assign_memory`
  - [ ] `/set_always_on`
- [ ] Decide whether `/tellme` and `/askdm` should keep defaulting to `#telldm` or default to the invoking channel.
- [ ] Keep tuning formatting and prompt behavior from real Discord outputs.

## Next

- [ ] Split transcript/session-summary runtime into:
  - [ ] objective/literal session record
  - [ ] narrative story recap
  - [ ] raw transcript output
- [ ] Improve `/summarize` attachment handling further where needed.
- [ ] Decide whether and when to add `/context_link`.
- [ ] Re-test the full transcript/session-summary path after the next implementation pass.

## Later

- [ ] Build a dedicated gameplay/DM prompt separate from the shared system prompt.
- [ ] Add a balancing layer for gameplay:
  - [ ] party level
  - [ ] party composition
  - [ ] optimization level
  - [ ] magic items
  - [ ] encounter intent
  - [ ] rest cadence
- [ ] Plan optional local ignored docs/reference ingestion for user-supplied rulebooks and campaign docs.
- [ ] Evaluate whether different models/providers should be used later for some tasks:
  - [ ] Minimax
  - [ ] Kimi
  - [ ] Qwen3
  - [ ] Gemini
- [ ] Rework voice capture/runtime for VPS use.
- [ ] If possible, send raw audio to an AI model that can translate and transcribe directly for bilingual sessions.
- [ ] Revisit the current 180-second chunking flow and decide whether transcript should stay the main intermediate artifact or only a failsafe.
- [ ] Extend transcript output so it can also be exported or represented as SRT.
- [ ] Add transcript + translation + narrative flow that can produce:
  - [ ] transcript
  - [ ] literal summary
  - [ ] story summary
  - [ ] optional TTS output later
- [ ] Add per-campaign context for stable reference details such as:
  - [ ] character appearance
  - [ ] character sheets
  - [ ] reusable campaign facts
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
- [ ] Fix platform portability in the voice pipeline:
  - [ ] remove Mac-specific assumptions
  - [ ] make mp3-based handling portable
- [ ] Add Docker and deployment cleanup.
- [ ] Make a feature map document such as `map.md` and decide whether to track it.
- [ ] Make a patch-notes workflow/folder and decide whether it should be tracked.
