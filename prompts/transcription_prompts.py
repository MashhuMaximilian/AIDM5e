DEFAULT_AUDIO_PROMPT = (
    "Transcribe this D&D session audio. The speakers may switch between Romanian and English, "
    "sometimes in the same exchange. Identify speakers if possible. Pay attention to whether the "
    "speech appears to be in-game, out-of-game, mechanical discussion, joking, planning, or meta "
    "commentary. If speaker identity or mode is unclear, mark it as uncertain instead of guessing."
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
