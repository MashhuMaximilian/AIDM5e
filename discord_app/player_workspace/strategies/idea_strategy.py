from __future__ import annotations

import asyncio

from config import GEMINI_CHAT_MODEL

from ..prompting import build_idea_prompt
from ..schema import PlayerWorkspaceRequest


class IdeaStrategy:
    async def generate(self, request: PlayerWorkspaceRequest, gemini) -> str:
        prompt = build_idea_prompt(request)
        if request.source.file_paths:
            return await asyncio.to_thread(
                gemini.generate_text_from_files,
                list(request.source.file_paths),
                prompt,
                GEMINI_CHAT_MODEL,
            )
        return await asyncio.to_thread(gemini.generate_text, prompt)

