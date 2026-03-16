def build_summary_prompt(history: str, query: str | None) -> str:
    return (
        "Summarize the following conversation history or messages. Only focus on essential "
        "information.\n\n"
        f"Conversation history:\n{history}\n\n"
        f"Additional summary requests:\n{query or 'None.'}"
    )


def build_feedback_prompt(conversation_history: str, last_message: str) -> str:
    return (
        "Make a recap of the following feedback messages regarding the AIDM's performance.\n\n"
        f"Entire message history from the #feedback channel:\n{conversation_history}\n\n"
        f"Pay special attention to the last feedback message:\n{last_message}\n\n"
        "1. Summarize this last message briefly and confirm you understood the feedback.\n"
        "2. Mention that you reviewed all feedback messages for better implementation."
    )

