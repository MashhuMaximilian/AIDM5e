DEFAULT_AUDIO_PROMPT = (
    "Transcribe this D&D session audio. Identify speakers if possible. Mix of Romanian and English."
)


def build_transcript_chunk_prompt(chunk: str, chapter_num: int, is_first: bool, is_last: bool) -> str:
    if is_first:
        return (
            "Great! We'll start a fresh session story retelling. The transcript you see is from "
            "another D&D session. Disregard any output you produced earlier for chapter numbering. "
            "Base your response solely on the transcript chunk and the following instructions. "
            "This is the first prompt only. Do not include any session recap. Do not think of "
            "previous sessions. Treat this chunk as a fresh continuation. Retell this D&D "
            "session's start in a vivid third-person story, staying 100% true to the transcript. "
            "Use in-game names and classes only, marking unclear names as [unknown, possibly "
            "character name]. Weave dialogue into the narration naturally and do not include "
            "direct quotes. Begin your response with "
            f"'Chapter 1: [Title from the Action]'.\n\nTranscript chunk:\n{chunk}"
        )

    if is_last:
        return (
            f"This is the final chunk of the transcript. Continue the story from where you left "
            f"off in Chapter {chapter_num - 1}. Retell the concluding part of the D&D session in "
            "a vivid third-person story, accurately and exactly following the transcript. Do not "
            "provide a session recap in this response. Use in-game names and mark unclear names "
            "as [unknown, possibly character name]. Begin your response with "
            f"'Chapter {chapter_num}: [Ending Title]'.\n\nTranscript chunk:\n{chunk}"
        )

    return (
        f"Continue the story from where you left off in Chapter {chapter_num - 1}. Do not "
        "consider any earlier retellings or chapter numbers beyond continuing the next chapter. "
        "Retell this next chunk of the D&D session in a vivid third-person narrative, sticking "
        "solely to the transcript events. Do not include a session recap yet. Use in-game names "
        "and mark unclear names as [unknown, possibly character name]. Begin your response with "
        f"'Chapter {chapter_num}: [Title from the Action]'.\n\nTranscript chunk:\n{chunk}"
    )


def build_final_session_summary_prompt() -> str:
    return (
        "Now that all parts of the session have been retold as a continuous story, provide a "
        "full session recap covering the entire session, including:\n"
        "- Key NPCs Met: list names and brief descriptions\n"
        "- Major Events: bullet points of key plot developments\n"
        "- Important Items: notable loot or artifacts\n"
        "- Unresolved Threads: outstanding questions or mysteries\n\n"
        "Provide a final summary of the entire D&D session."
    )

