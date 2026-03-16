# Prompt Layout

This folder centralizes prompt text and explains where each prompt is used.

## Files

- `system/aidm_prompt.txt`
  - Global system instruction for Gemini.
  - Loaded at startup and sent on every model request.
  - Used by chat replies, slash-command answers, summaries, and transcript retelling.

- `query_prompts.py`
  - Prompt templates for `/tellme` and `/askdm`.
  - These become the current user request that is combined with memory history.

- `summary_prompts.py`
  - Prompt builders for `/summarize` and feedback recap flows.

- `transcription_prompts.py`
  - Default audio transcription prompt.
  - Transcript retelling prompts for session chapterization.
  - Final full-session recap prompt.

## Runtime Prompt Stack

Most model calls use this structure:

1. System prompt from `system/aidm_prompt.txt`
2. Memory wrapper from `assistant_interactions.py`
   - current memory name
   - prior stored memory history
   - current user request
3. Feature-specific user prompt
   - query prompt
   - summary prompt
   - feedback prompt
   - transcript retelling prompt

## Discord Formatting Rule

Discord does not reliably render Markdown masked links like `[label](https://example.com)`
in normal bot message content.

We therefore enforce this in two layers:

1. Prompt guidance tells the model to use plain URLs.
2. Send-time formatting strips masked links into plain URLs before sending.
