from __future__ import annotations

from ai_services.gemini_client import gemini_client as default_gemini_client

from .schema import PlayerWorkspaceRequest
from .strategies import IdeaStrategy, ImportStrategy


def _strategy_for_mode(mode: str):
    return ImportStrategy() if mode == "import" else IdeaStrategy()


async def draft_player_workspace_text(
    request: PlayerWorkspaceRequest,
    *,
    gemini=default_gemini_client,
) -> str:
    return await _strategy_for_mode(request.mode).generate(request, gemini)
