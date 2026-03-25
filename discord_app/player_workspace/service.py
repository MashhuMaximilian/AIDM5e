from __future__ import annotations

from ai_services.gemini_client import gemini_client

from .card_splitter import split_markdown_into_cards
from .schema import PlayerWorkspaceBundle, PlayerWorkspaceRequest
from .strategies import IdeaStrategy, ImportStrategy


class CreatePlayerService:
    def __init__(self, *, gemini=gemini_client) -> None:
        self.gemini = gemini
        self._strategies = {
            "idea": IdeaStrategy(),
            "import": ImportStrategy(),
        }

    async def create(
        self,
        request: PlayerWorkspaceRequest,
    ) -> PlayerWorkspaceBundle:
        strategy = self._strategies[request.mode]

        raw_markdown = await strategy.generate(request, self.gemini)

        if request.mode == "import" and hasattr(strategy, "format_pass"):
            raw_markdown = await strategy.format_pass(
                request,
                self.gemini,
                raw_markdown=raw_markdown,
            )

        cards = split_markdown_into_cards(raw_markdown, request)

        return PlayerWorkspaceBundle(
            request=request,
            cards=cards,
            draft=None,
            validation=None,
        )
