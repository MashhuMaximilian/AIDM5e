from __future__ import annotations

from ai_services.gemini_client import gemini_client

from .schema import PlayerWorkspaceBundle, PlayerWorkspaceRequest
from .service import CreatePlayerService


MANAGED_CARD_TITLES = (
    "Character Card",
    "Profile Card",
    "Rules Card",
    "Items Card",
)


async def build_player_workspace(
    request: PlayerWorkspaceRequest,
    *,
    gemini=gemini_client,
) -> PlayerWorkspaceBundle:
    service = CreatePlayerService(gemini=gemini)
    return await service.create(request)


def managed_card_titles() -> tuple[str, ...]:
    return MANAGED_CARD_TITLES
