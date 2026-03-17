DEFAULT_AUDIO_PROMPT = (
    "Transcribe this D&D session audio. The speakers may switch between Romanian and English, "
    "sometimes in the same exchange. Identify speakers if possible. Pay attention to whether the "
    "speech appears to be in-game, out-of-game, mechanical discussion, joking, planning, or meta "
    "commentary. If speaker identity or mode is unclear, mark it as uncertain instead of guessing."
)


def build_transcript_capture_prompt(
    chunk_index: int,
    start_offset_seconds: int,
    duration_seconds: int,
    extra_instructions: str | None = None,
) -> str:
    prompt = (
        "You are transcribing a D&D session audio chunk.\n\n"
        "Return only valid JSON. Do not wrap it in code fences. Do not add commentary.\n\n"
        "The speakers may switch between Romanian and English, sometimes in the same sentence. "
        "Preserve the original spoken language exactly as spoken.\n\n"
        "Goal:\n"
        "- produce a best-effort structured transcript for this chunk\n"
        "- identify speakers when possible\n"
        "- identify character names when reasonably clear\n"
        "- tag each segment as one of: IC, OOC, META, UNCLEAR\n"
        "- tag each segment language as one of: RO, EN, RO+EN\n"
        "- provide best-effort timestamps relative to the start of this audio chunk\n"
        "- if speaker identity is uncertain, use Unknown\n"
        "- if character identity is uncertain, use null\n"
        "- if a timestamp is uncertain, still estimate it as best you can\n"
        "- ignore obvious dead air, page flips, and filler unless they matter to understanding the moment\n\n"
        "Chunk metadata:\n"
        f"- chunk_index: {chunk_index}\n"
        f"- session_start_offset_seconds: {start_offset_seconds}\n"
        f"- expected_duration_seconds: {duration_seconds}\n\n"
        "Return JSON with exactly this top-level shape:\n"
        "{\n"
        '  "chunk_index": number,\n'
        '  "start_offset_seconds": number,\n'
        '  "duration_seconds": number,\n'
        '  "notes": [string],\n'
        '  "segments": [\n'
        "    {\n"
        '      "offset_seconds": number,\n'
        '      "speaker": string,\n'
        '      "character": string or null,\n'
        '      "lang": "RO" | "EN" | "RO+EN",\n'
        '      "mode": "IC" | "OOC" | "META" | "UNCLEAR",\n'
        '      "text": string\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- segments must be in chronological order\n"
        "- merge adjacent lines from the same speaker only when they are clearly part of the same utterance\n"
        "- keep text readable and lightly cleaned, but do not rewrite meaning\n"
        "- do not translate\n"
        "- do not invent dialogue\n"
        "- do not hallucinate speaker names\n"
    )
    if extra_instructions:
        prompt += f"\nAdditional instructions:\n{extra_instructions}\n"
    return prompt


def build_audio_summary_chunk_prompt(
    window_index: int,
    start_offset_seconds: int,
    end_offset_seconds: int,
) -> str:
    return (
        "You are analyzing D&D session audio directly.\n\n"
        "Return only valid JSON. Do not wrap it in code fences. Do not add commentary.\n\n"
        "You are given one or more contiguous audio chunk files from the same D&D session window. "
        "Use the audio itself as the primary source. Pay attention not only to literal words, but also "
        "to tone, urgency, hesitation, emotional shifts, and how things are said when that affects interpretation.\n\n"
        "Window metadata:\n"
        f"- window_index: {window_index}\n"
        f"- session_start_offset_seconds: {start_offset_seconds}\n"
        f"- session_end_offset_seconds: {end_offset_seconds}\n\n"
        "Return JSON with exactly this shape:\n"
        "{\n"
        '  "window_index": number,\n'
        '  "start_offset_seconds": number,\n'
        '  "end_offset_seconds": number,\n'
        '  "objective_notes": [string],\n'
        '  "narrative_notes": [string],\n'
        '  "notable_cues": [string],\n'
        '  "uncertainties": [string]\n'
        "}\n\n"
        "Rules:\n"
        "- objective_notes should capture concrete events, decisions, reveals, combats, and important meta decisions\n"
        "- narrative_notes should capture scene flow, mood, tension, and memorable beats without inventing facts\n"
        "- notable_cues should capture meaningful tone or delivery clues only when they matter\n"
        "- uncertainties should list unclear speakers, unclear wording, or unclear interpretation\n"
        "- preserve Romanian and English meaning correctly\n"
        "- do not invent scenes or facts that are not supported by the audio\n"
    )


def build_audio_objective_summary_prompt(window_notes: str) -> str:
    return (
        "You are in transcript archivist mode.\n\n"
        "Using the audio-derived session notes below, write a factual, objective session record.\n\n"
        "Requirements:\n"
        "- prioritize concrete events in order\n"
        "- focus mostly on gameplay, but include important meta decisions when they affected the session\n"
        "- preserve uncertainty explicitly instead of guessing\n"
        "- be useful for continuity later\n"
        "- do not turn this into a story\n\n"
        "Then, after the objective record, add a compact continuity block in exactly this format:\n\n"
        "==========START SESSION==========\n"
        "Title:\n"
        "Key Events:\n"
        "NPCs:\n"
        "Items:\n"
        "Unresolved Threads:\n"
        "Player Plans / Next Steps:\n"
        "==========END SESSION============\n\n"
        f"Audio-derived notes:\n{window_notes}"
    )


def build_audio_narrative_summary_prompt(window_notes: str) -> str:
    return (
        "You are in narrative recap mode.\n\n"
        "Using the audio-derived session notes below, write a story-like session recap that remains faithful to what happened.\n\n"
        "Requirements:\n"
        "- stay true to events, decisions, and outcomes\n"
        "- you may use literary flow, pacing, and atmosphere\n"
        "- do not invent facts or scenes\n"
        "- preserve meaningful tension, tone, and dramatic beats captured from the audio notes\n"
        "- use chaptered scenes only when the session length justifies it; otherwise keep it as a cohesive recap\n"
        "- preserve uncertainty cautiously if the notes mark something unclear\n\n"
        f"Audio-derived notes:\n{window_notes}"
    )


def build_transcript_objective_prompt(transcript: str) -> str:
    return (
        "You are in transcript archivist mode.\n\n"
        "Your task is to turn the transcript into a factual, objective session record.\n\n"
        "Write like a precise historical record or court chronicle:\n"
        "- faithful to the transcript,\n"
        "- event-by-event,\n"
        "- minimally interpretive,\n"
        "- emotionally restrained,\n"
        "- highly accurate.\n\n"
        "Goals:\n"
        "- Record what happened in the order it happened.\n"
        "- Preserve important facts, decisions, revelations, combats, locations, NPC interactions, and consequences.\n"
        "- Preserve uncertainty when the transcript is unclear.\n"
        "- Use the names actually present in the transcript when they are clear.\n"
        "- If a name or detail is unclear, mark it as uncertain instead of inventing.\n"
        "- Do not embellish, dramatize, or add flavor beyond what is needed for clarity.\n"
        "- Do not invent dialogue, scenes, outcomes, motivations, or transitions.\n"
        "- Do not rewrite events into a cinematic story.\n\n"
        "Language and speaker handling:\n"
        "- The session may contain both Romanian and English, sometimes mixed in the same exchange.\n"
        "- Correctly interpret both languages and preserve the meaning across them.\n"
        "- Pay attention to who is speaking when possible.\n"
        "- When it is possible to distinguish in-game speech, out-of-game discussion, table talk, or meta commentary, reflect that clearly.\n"
        "- If speaker identity or mode of speech is unclear, mark it as uncertain instead of guessing.\n"
        "- Preserve important switches between roleplay, mechanics discussion, jokes, planning, and meta conversation when they matter to understanding the session.\n\n"
        "Formatting:\n"
        "- Use clean sectioning when useful.\n"
        "- Use bullets only if they improve factual clarity.\n"
        "- Keep the tone formal, clear, and precise.\n"
        "- This output should feel like an objective campaign record.\n\n"
        "Future-awareness:\n"
        "- This summary may later be paired with additional campaign context such as character sheets, character appearance references, scene references, or other campaign documents.\n"
        "- For now, use only the transcript and provided context, and do not invent details from absent materials.\n\n"
        "Output priorities:\n"
        "- chronology\n"
        "- factual accuracy\n"
        "- clarity\n"
        "- continuity usefulness\n\n"
        f"Transcript content:\n{transcript}"
    )


def build_transcript_chunk_prompt(chunk: str, chapter_num: int, is_first: bool, is_last: bool) -> str:
    guidance = (
        "You are in narrative recap mode.\n\n"
        "Your task is to turn the transcript into a story-like session recap that is enjoyable to read while remaining faithful to the transcript.\n\n"
        "Goals:\n"
        "- Stay 100% true to the events, decisions, and outcomes in the transcript.\n"
        "- You may smooth wording, pacing, and transitions.\n"
        "- You may weave dialogue naturally into narration when supported by the transcript.\n"
        "- You may add atmosphere, rhythm, and literary flow.\n"
        "- You may not invent facts, scenes, outcomes, motivations, lore, or dialogue that are unsupported by the transcript.\n"
        "- If a detail is unclear, keep it cautious or mark it as uncertain rather than inventing.\n\n"
        "Language and speaker handling:\n"
        "- The session may contain both Romanian and English, sometimes mixed naturally at the table.\n"
        "- Correctly interpret meaning across both languages.\n"
        "- Pay close attention to who is speaking when possible.\n"
        "- Notice when speech appears to be in-character, out-of-character, mechanical discussion, joking, planning, or meta commentary.\n"
        "- When those distinctions matter to the flow of the session, preserve them clearly in the recap.\n"
        "- If speaker identity or roleplay/meta boundaries are unclear, do not guess; stay cautious.\n\n"
        "Style:\n"
        "- Write like a strong fantasy session chronicler.\n"
        "- Keep it vivid, readable, and emotionally engaging.\n"
        "- Use chapters or scene divisions when useful.\n"
        "- Avoid repetition.\n"
        "- Keep the prose tighter and cleaner than the raw transcript.\n\n"
        "Formatting:\n"
        "- Use headers, separators, emphasis, or quotes when they improve readability or atmosphere.\n"
        "- Formatting may be decorative only when it also serves clarity, pacing, emphasis, or mood.\n"
        "- Do not over-format every paragraph.\n\n"
        "Future-awareness:\n"
        "- This recap may later be paired with additional campaign context such as character appearance references, character sheets, scene references, or other campaign documents.\n"
        "- For now, use only the transcript and provided context, and do not invent details from materials that are not present.\n\n"
    )

    if is_first:
        return (
            f"{guidance}"
            "Great! We'll start a fresh session story retelling. The transcript you see is from "
            "another D&D session. Disregard any output you produced earlier for chapter numbering. "
            "Base your response solely on the transcript chunk and the following instructions. "
            "This is the first prompt only. Do not include any session recap. Do not think of "
            "previous sessions. Treat this chunk as a fresh continuation. Begin your response with "
            f"'Chapter 1: [Title from the Action]'.\n\nTranscript chunk:\n{chunk}"
        )

    if is_last:
        return (
            f"{guidance}"
            f"This is the final chunk of the transcript. Continue the story from where you left "
            f"off in Chapter {chapter_num - 1}. Retell the concluding part of the D&D session in "
            "a vivid third-person story, accurately and exactly following the transcript. Do not "
            "provide a session recap in this response. Begin your response with "
            f"'Chapter {chapter_num}: [Ending Title]'.\n\nTranscript chunk:\n{chunk}"
        )

    return (
        f"{guidance}"
        f"Continue the story from where you left off in Chapter {chapter_num - 1}. Do not "
        "consider any earlier retellings or chapter numbers beyond continuing the next chapter. "
        "Retell this next chunk of the D&D session in a vivid third-person narrative, sticking "
        "solely to the transcript events. Do not include a session recap yet. Begin your response with "
        f"'Chapter {chapter_num}: [Title from the Action]'.\n\nTranscript chunk:\n{chunk}"
    )


def build_final_session_summary_prompt() -> str:
    return (
        "You are in transcript archivist mode.\n\n"
        "Now that all parts of the session have been retold as a continuous story, produce a "
        "compact factual continuity block in exactly this format:\n\n"
        "==========START SESSION==========\n"
        "Title:\n"
        "Key Events:\n"
        "NPCs:\n"
        "Items:\n"
        "Unresolved Threads:\n"
        "Player Plans / Next Steps:\n"
        "==========END SESSION============\n\n"
        "Rules:\n"
        "- Keep it compact and factual.\n"
        "- Include only useful continuity information.\n"
        "- Do not add invented details.\n"
        "- If a section has no meaningful content, say None or Unclear.\n"
        "- Stay faithful to the transcript-derived narrative that came before this output."
    )
