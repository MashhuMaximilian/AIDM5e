from __future__ import annotations

from textwrap import dedent

from ai_services.gemini_client import gemini_client

from .card_splitter import split_markdown_into_cards
from .prompting import build_thread_welcome_text
from .schema import PlayerWorkspaceBundle, PlayerWorkspaceCardBundle, PlayerWorkspaceRequest
from .strategies import IdeaStrategy, ImportStrategy


def _build_player_template_skeleton_cards(character_name: str) -> PlayerWorkspaceCardBundle:
    empty_bar = "░" * 45
    return PlayerWorkspaceCardBundle(
        character_card=dedent(
            f"""
            > **BUILD**: `Needs review.`
            > **Spellcasting Ability**: `Needs review.`

            🛡️ **AC: `Needs review.`**  |  🎯 **DC: `Needs review.`** | 💎 **PB: `Needs review.`**  | 🏃 **SPD: `Needs review.`**

            🎲 **Hit Dice:** `Needs review.`

            **💟 HP: [ Needs review. / Needs review. ]**
            `{empty_bar}`

            **🔋 RESOURCE TRACKING**
            * **Primary Resource:** `Needs review.`
            * **Secondary Resource:** `Needs review.`

            **✨ Spell Slots**
            * **Cantrips:** `Needs review.`
            * **Lvl 1:** `Needs review.`
            """
        ).strip(),
        profile_card=dedent(
            f"""
            > ***"Needs review."***

            ```
            [ CHARACTER LEVEL, RACE, & CLASS ]
            ----------------------------------------
            LEVEL.....: Needs review.
            RACE......: Needs review.
            CLASS.....: Needs review.
            SUBCLASS..: Needs review.
            XP........: Needs review.
            PLAYER....: Needs review.
            BACKGROUND: Needs review.
            ALIGNMENT.: Needs review.
            DEITY.....: Needs review.
            ----------------------------------------
            ```

            **Identity**
            * **Name:** {character_name or 'Needs review.'}
            * **Alias / Nickname:** Needs review.
            * **Concept:** Needs review.

            **Appearance & Status**
            * **Appearance:** Needs review.
            * **Current vibe / demeanor:** Needs review.
            * **Assumptions to confirm:** Needs review.
            """
        ).strip(),
        skills_actions_card=dedent(
            """
            ```
            ABILITY SCORES & SAVING THROWS
            +---------+-------+-----+------+
            | ABILITY | SCORE | MOD | SAVE |
            +---------+-------+-----+------+
            | [ ] STR |  ?    |  ?  |  ?   |
            | [ ] DEX |  ?    |  ?  |  ?   |
            | [ ] CON |  ?    |  ?  |  ?   |
            | [ ] INT |  ?    |  ?  |  ?   |
            | [ ] WIS |  ?    |  ?  |  ?   |
            | [ ] CHA |  ?    |  ?  |  ?   |
            +---------+-------+-----+------+
            ```

            ```
            SKILLS & SENSES
            -------------------------
            Acrobatics .... Needs review.
            Animal Hand ... Needs review.
            Arcana ........ Needs review.
            Athletics ..... Needs review.
            Deception ..... Needs review.
            History ....... Needs review.
            Insight ....... Needs review.
            Intimidation .. Needs review.
            Investigation . Needs review.
            Medicine ...... Needs review.
            Nature ........ Needs review.
            Perception .... Needs review.
            Performance ... Needs review.
            Persuasion .... Needs review.
            Religion ...... Needs review.
            Sleight Hand .. Needs review.
            Stealth ....... Needs review.
            Survival ...... Needs review.
            PASSIVE PERCEPTION: Needs review.
            PASSIVE INSIGHT: Needs review.
            ```

            **Actions**
            * Needs review.

            **Actions & Magic**
            * Needs review.
            """
        ).strip(),
        rules_card=dedent(
            """
            **🌌 Racial Traits**
            * Needs review.

            **🥋 Class Features**
            * Needs review.

            **👊 Subclass Features**
            * Needs review.

            **📜 Feats / ASIs**
            * Needs review.

            **🛠️ Proficiencies**
            * **Tools:** Needs review.
            * **Languages:** Needs review.

            **✨ Spellbook / Known Spells**
            * **Cantrips:** Needs review.
            * **Lvl 1+:** Needs review.
            """
        ).strip(),
        items_card=dedent(
            """
            **💎 Attuned Items `[0 / 3]`**
            * Needs review.

            **⚔️ Notable Gear**
            * Needs review.

            ```
            [🎒 ENCUMBRANCE ]
            -----------------------------------------
            WEIGHT CARRIED: Needs review.
            CARRY CAPACITY: Needs review.
            PUSH/DRAG/LIFT: Needs review.
            -----------------------------------------
            ```

            ```
            [💰 CURRENCY ]
            --------------------------------
            COPPER............: Needs review.
            SILVER............: Needs review.
            GOLD..............: Needs review.
            PLATINUM..........: Needs review.
            ELECTRUM..........: Needs review.
            --------------------------------
            ```
            """
        ).strip(),
        links_card=dedent(
            """
            **Race / Class / Subclass**
            * Needs review.

            **Feats**
            * Needs review.

            **Spells**
            * Needs review.

            **Items**
            * Needs review.

            **Other**
            * Needs review.
            """
        ).strip(),
        welcome_text="",
    )


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

    cards = _build_player_template_skeleton_cards(request.character_name or "Needs review.")
    cards.welcome_text = build_thread_welcome_text(request)
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
