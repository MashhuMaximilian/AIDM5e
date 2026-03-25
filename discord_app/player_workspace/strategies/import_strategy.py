from __future__ import annotations

import asyncio

from config import GEMINI_CHAT_MODEL

from ..prompting import (
    build_format_pass_prompt,
    build_import_prompt,
    build_import_reference_links_prompt,
    build_import_repair_prompt,
)
from ..schema import PlayerWorkspaceRequest


class ImportStrategy:
    async def generate(self, request: PlayerWorkspaceRequest, gemini) -> str:
        if not request.source.file_paths and not (request.source.source_text or request.source.note):
            raise ValueError("Import mode needs at least one file, note, or source text.")

        prompt = build_import_prompt(request)
        if request.source.file_paths:
            return await asyncio.to_thread(
                gemini.generate_text_from_files,
                list(request.source.file_paths),
                prompt,
                GEMINI_CHAT_MODEL,
            )
        return await asyncio.to_thread(gemini.generate_text, prompt)

    async def repair(
        self,
        request: PlayerWorkspaceRequest,
        gemini,
        *,
        missing_sections: list[str],
        current_markdown: str,
    ) -> str:
        prompt = build_import_repair_prompt(
            request,
            missing_sections=missing_sections,
            current_markdown=current_markdown,
        )
        if request.source.file_paths:
            return await asyncio.to_thread(
                gemini.generate_text_from_files,
                list(request.source.file_paths),
                prompt,
                GEMINI_CHAT_MODEL,
            )
        return await asyncio.to_thread(gemini.generate_text, prompt)

    async def backfill_reference_links(
        self,
        request: PlayerWorkspaceRequest,
        gemini,
        *,
        current_markdown: str,
    ) -> str:
        prompt = build_import_reference_links_prompt(
            request,
            current_markdown=current_markdown,
        )
        if request.source.file_paths:
            return await asyncio.to_thread(
                gemini.generate_text_from_files,
                list(request.source.file_paths),
                prompt,
                GEMINI_CHAT_MODEL,
            )
        return await asyncio.to_thread(gemini.generate_text, prompt)

    async def format_pass(
        self,
        request: PlayerWorkspaceRequest,
        gemini,
        *,
        raw_markdown: str,
    ) -> str:
        prompt = build_format_pass_prompt(raw_markdown)
        if request.source.file_paths:
            return await asyncio.to_thread(
                gemini.generate_text_from_files,
                list(request.source.file_paths),
                prompt,
                GEMINI_CHAT_MODEL,
            )
        return await asyncio.to_thread(gemini.generate_text, prompt)
