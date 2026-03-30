from __future__ import annotations

from ai_services.gemini_client import gemini_client

from .card_splitter import split_markdown_into_cards
from .prompting import build_thread_welcome_text
from .schema import PlayerWorkspaceBundle, PlayerWorkspaceCardBundle, PlayerWorkspaceRequest
from .strategies import IdeaStrategy, ImportStrategy


def _note_requests_seeded_idea_cards(note: str | None) -> bool:
    content = (note or "").strip().lower()
    if not content:
        return False
    explicit_seed_phrases = (
        "fill the cards",
        "populate the cards",
        "draft the cards",
        "seed the cards",
        "build the sheet",
        "make the sheet",
        "full draft",
        "fully flesh",
    )
    if any(phrase in content for phrase in explicit_seed_phrases):
        return True

    detail_markers = (
        "class",
        "subclass",
        "race",
        "background",
        "level",
        "spells",
        "feat",
        "stats",
        "inventory",
        "ac",
        "hp",
    )
    detail_hits = sum(1 for marker in detail_markers if marker in content)
    return len(content) >= 250 and detail_hits >= 3


def _build_empty_idea_bundle(request: PlayerWorkspaceRequest) -> PlayerWorkspaceBundle:
    note = (request.source.note or "").strip()
    prompt_lines = [
        f"**Idea workspace started for {request.character_name or 'this character'}.**",
        "The cards are intentionally blank right now so we do not lock in canon too early.",
    ]
    if note:
        prompt_lines.extend(
            [
                "",
                f"**Starting note:** {note}",
                "",
                "Tell me what you want to establish first, and I will only update cards when you explicitly ask me to.",
                "A good next step is usually: concept, class fantasy, tone, fighting style, or how close to the inspiration you want to stay.",
            ]
        )

    cards = PlayerWorkspaceCardBundle(
        character_card="Needs review.",
        profile_card="Needs review.",
        skills_actions_card="Needs review.",
        rules_card="Needs review.",
        items_card="Needs review.",
        links_card="Needs review.",
        welcome_text=build_thread_welcome_text(request),
    )
    return PlayerWorkspaceBundle(
        request=request,
        cards=cards,
        draft="\n".join(prompt_lines).strip(),
        validation=None,
    )


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
        if request.mode == "idea" and not _note_requests_seeded_idea_cards(request.source.note):
            return _build_empty_idea_bundle(request)

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
