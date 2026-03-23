from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

import discord


logger = logging.getLogger(__name__)

WorkspaceKind = Literal["player", "npc", "other"]

WORKSPACE_THREAD_PREFIXES: tuple[tuple[str, WorkspaceKind], ...] = (
    ("Character - ", "player"),
    ("NPC - ", "npc"),
    ("Other - ", "other"),
)

NPC_DEFAULT_CARD_TITLES: tuple[str, ...] = (
    "Summary Card",
    "Profile Card",
    "Personality & Hooks",
    "Stat Block",
    "Relationships",
)

WORKSPACE_META_START = "[AIDM WORKSPACE META]"
WORKSPACE_META_END = "[/AIDM WORKSPACE META]"
CARD_SECTION_RE = re.compile(r"^###\s+CARD:\s*(.+?)\s*$", re.MULTILINE)


@dataclass(slots=True)
class WorkspaceDefinition:
    kind: WorkspaceKind
    entity_name: str
    user_note: str = ""
    card_inventory_text: str = ""
    cascade_rules_text: str = ""
    card_titles: list[str] = field(default_factory=list)


def parse_workspace_thread(thread_name: str | None) -> tuple[WorkspaceKind | None, str | None]:
    for prefix, kind in WORKSPACE_THREAD_PREFIXES:
        if (thread_name or "").startswith(prefix):
            return kind, (thread_name or "")[len(prefix) :].strip() or None
    return None, None


def build_workspace_metadata_block(
    *,
    kind: WorkspaceKind,
    entity_name: str,
    user_note: str,
    card_inventory_text: str,
    cascade_rules_text: str,
) -> str:
    return (
        f"{WORKSPACE_META_START}\n"
        f"type: {kind}\n"
        f"entity: {entity_name}\n"
        "user_note:\n"
        f"{(user_note or '').strip()}\n"
        "---\n"
        "card_inventory:\n"
        f"{(card_inventory_text or '').strip()}\n"
        "---\n"
        "cascade_rules:\n"
        f"{(cascade_rules_text or '').strip()}\n"
        f"{WORKSPACE_META_END}"
    ).strip()


def parse_workspace_metadata(text: str | None) -> WorkspaceDefinition | None:
    body = (text or "").strip()
    if WORKSPACE_META_START not in body or WORKSPACE_META_END not in body:
        return None
    start = body.index(WORKSPACE_META_START) + len(WORKSPACE_META_START)
    end = body.index(WORKSPACE_META_END)
    payload = body[start:end].strip()

    kind_match = re.search(r"^type:\s*(player|npc|other)\s*$", payload, re.MULTILINE)
    entity_match = re.search(r"^entity:\s*(.+?)\s*$", payload, re.MULTILINE)
    if not kind_match or not entity_match:
        return None

    user_note = _extract_meta_block(payload, "user_note")
    card_inventory_text = _extract_meta_block(payload, "card_inventory")
    cascade_rules_text = _extract_meta_block(payload, "cascade_rules")
    titles = parse_card_inventory_titles(card_inventory_text)
    return WorkspaceDefinition(
        kind=kind_match.group(1),  # type: ignore[arg-type]
        entity_name=entity_match.group(1).strip(),
        user_note=user_note,
        card_inventory_text=card_inventory_text,
        cascade_rules_text=cascade_rules_text,
        card_titles=titles,
    )


def _extract_meta_block(payload: str, label: str) -> str:
    pattern = rf"{label}:\n(.*?)(?:\n---\n|\Z)"
    match = re.search(pattern, payload, re.DOTALL)
    return match.group(1).strip() if match else ""


def parse_other_prepass_output(raw_text: str) -> tuple[list[str], str, str]:
    text = (raw_text or "").strip()
    inventory_match = re.search(r"###\s+CARD INVENTORY\s*(.*?)(?=\n###\s+CASCADE RULES|\Z)", text, re.DOTALL | re.IGNORECASE)
    cascade_match = re.search(r"###\s+CASCADE RULES\s*(.*)$", text, re.DOTALL | re.IGNORECASE)
    inventory_text = inventory_match.group(1).strip() if inventory_match else ""
    cascade_text = cascade_match.group(1).strip() if cascade_match else ""
    titles = parse_card_inventory_titles(inventory_text)
    if not titles:
        titles = ["Summary Card", "Profile Card", "Details Card"]
        inventory_text = "\n".join(f"- {title}: Needs review." for title in titles)
    if not any(title.lower() == "summary card" for title in titles):
        titles.insert(0, "Summary Card")
        inventory_text = f"- Summary Card: High-level overview.\n{inventory_text}".strip()
    return titles, inventory_text, cascade_text


def parse_card_inventory_titles(card_inventory_text: str) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()
    for raw_line in (card_inventory_text or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("-"):
            continue
        content = line.lstrip("-").strip()
        title = content.split(":", 1)[0].strip() or content
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        titles.append(title)
    return titles


def build_npc_blank_cards(npc_name: str) -> dict[str, str]:
    return {
        "Summary Card": dedent_block(
            f"""
            ### 👤 NPC SUMMARY — {npc_name}

            **Role:** Needs review.
            **Faction:** Needs review.
            **CR:** Needs review.
            **Alignment:** Needs review.
            **Status:** Needs review.
            **Last Seen:** Needs review.
            """
        ),
        "Profile Card": dedent_block(
            f"""
            ### 👤 NPC PROFILE — {npc_name}

            **Full Name / Aliases:** Needs review.
            **Race / Type:** Needs review.
            **Age:** Needs review.
            **Appearance:** Needs review.
            **Distinctive Features:** Needs review.
            > ***"Needs review."***
            """
        ),
        "Personality & Hooks": dedent_block(
            """
            ### 🎭 PERSONALITY & HOOKS

            **Traits:** Needs review.
            **Ideals:** Needs review.
            **Flaws:** Needs review.
            **Bonds:** Needs review.
            **Secrets (DM-only):** Needs review.
            **Hooks for the Party:** Needs review.
            """
        ),
        "Stat Block": dedent_block(
            """
            ### ⚔️ STAT BLOCK

            **AC:** `Needs review.`
            **HP:** `Needs review.`
            **Speed:** `Needs review.`
            **CR:** `Needs review.`
            **PB:** `Needs review.`

            **Ability Scores:** Needs review.
            **Actions in Combat:** Needs review.
            **Traits & Features:** Needs review.
            """
        ),
        "Relationships": dedent_block(
            """
            ### 🤝 RELATIONSHIPS

            **Party Relationships:** Needs review.
            **Key NPC Connections:** Needs review.
            **Faction Standing:** Needs review.
            """
        ),
    }


def build_other_blank_cards(entity_name: str, card_titles: list[str]) -> dict[str, str]:
    cards: dict[str, str] = {}
    for title in card_titles:
        section_title = title.upper()
        heading = "### 🧩 " + section_title
        if title.lower() == "summary card":
            heading = f"### 🧩 SUMMARY — {entity_name}"
        cards[title] = dedent_block(
            f"""
            {heading}

            **Needs review.**
            """
        )
    return cards


def dedent_block(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(lines).strip()


def build_workspace_welcome_text(definition: WorkspaceDefinition) -> str:
    human = {
        "npc": f"NPC workspace ready for {definition.entity_name}. Use this thread as the draft workspace. If not pinned already, I strongly advise you to pin all the relevant cards/messages for the best experience.",
        "other": f"Custom workspace ready for {definition.entity_name}. Use this thread as the draft workspace. If not pinned already, I strongly advise you to pin all the relevant cards/messages for the best experience.",
        "player": f"Character workspace ready for {definition.entity_name}. Use this thread as the draft workspace. If not pinned already, I strongly advise you to pin all the relevant cards/messages for the best experience.",
    }[definition.kind]
    return f"{human}\nPost new notes and source material here as it evolves."


def build_workspace_embed(title: str, body: str, *, summary: bool = False) -> discord.Embed:
    color = discord.Color.orange() if summary else discord.Color.dark_grey()
    embed = discord.Embed(title=title, description=(body or "Needs review.").strip(), color=color)
    return embed


class WorkspaceCardEditModal(discord.ui.Modal):
    def __init__(self, *, title: str, initial_body: str) -> None:
        super().__init__(title=f"Edit {title}")
        self.card_title = title
        self.content_input = discord.ui.TextInput(
            label="Card Content",
            style=discord.TextStyle.paragraph,
            default=(initial_body or "Needs review.")[:4000],
            max_length=4000,
            required=True,
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        embed = build_workspace_embed(self.card_title, str(self.content_input.value), summary=False)
        await interaction.response.edit_message(content="", embed=embed, view=WorkspaceCardDetailView(self.card_title))


class WorkspaceCardDetailView(discord.ui.View):
    def __init__(self, card_title: str) -> None:
        super().__init__(timeout=None)
        self.card_title = card_title

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.secondary, custom_id="aidm:workspace-card-edit")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        initial_body = interaction.message.embeds[0].description if interaction.message.embeds else ""
        await interaction.response.send_modal(WorkspaceCardEditModal(title=self.card_title, initial_body=initial_body))


def build_workspace_summary_view(messages: dict[str, discord.Message]) -> discord.ui.View | None:
    view = discord.ui.View(timeout=None)
    for title, message in messages.items():
        if title == "Summary Card":
            continue
        label = title.replace(" Card", "").strip()
        view.add_item(discord.ui.Button(label=label, url=message.jump_url, style=discord.ButtonStyle.link))
    return view if view.children else None


async def discover_workspace_card_messages(thread: discord.Thread) -> dict[str, discord.Message]:
    bot_user = thread.guild.me or thread.guild.get_member(thread._state.user.id)
    bot_id = bot_user.id if bot_user else None
    history_messages = [message async for message in thread.history(limit=100, oldest_first=True)]
    expected_titles: set[str] = set()
    for message in history_messages:
        metadata = parse_workspace_metadata(message.content)
        if metadata is not None:
            expected_titles = set(metadata.card_titles)
            break

    messages: dict[str, discord.Message] = {}
    for message in await thread.pins():
        if bot_id is not None and message.author.id != bot_id:
            continue
        title = message.embeds[0].title if message.embeds else ""
        if title:
            messages[title] = message

    if not expected_titles or not expected_titles.issubset(messages.keys()):
        for message in history_messages:
            if bot_id is not None and message.author.id != bot_id:
                continue
            title = message.embeds[0].title if message.embeds else ""
            if not title:
                continue
            if expected_titles and title not in expected_titles:
                continue
            messages.setdefault(title, message)
    return messages


async def sync_workspace_cards(thread: discord.Thread, cards: dict[str, str]) -> dict[str, discord.Message]:
    existing = await discover_workspace_card_messages(thread)
    resolved: dict[str, discord.Message] = {}

    for index, title in enumerate(cards.keys()):
        body = cards[title]
        summary = index == 0
        embed = build_workspace_embed(title, body, summary=summary)
        view = None if summary else WorkspaceCardDetailView(title)
        message = existing.get(title)
        if message is None:
            message = await thread.send(content="", embed=embed, view=view)
            try:
                await message.pin(reason="AIDM workspace slot")
            except discord.HTTPException as exc:
                logger.warning("Failed to pin workspace slot %s in thread %s: %s", title, thread.id, exc)
        else:
            current_title = message.embeds[0].title if message.embeds else ""
            current_description = message.embeds[0].description if message.embeds else ""
            if current_title != embed.title or current_description != embed.description:
                message = await message.edit(content="", embed=embed, view=view)
            else:
                await message.edit(view=view)
        resolved[title] = message

    summary_message = resolved.get(next(iter(cards)))
    if summary_message is not None:
        final_view = build_workspace_summary_view(resolved)
        await summary_message.edit(view=final_view)

    for title, message in resolved.items():
        try:
            await message.pin(reason="AIDM workspace slot")
        except discord.HTTPException as exc:
            logger.warning("Failed to pin workspace slot %s in thread %s: %s", title, thread.id, exc)
    return resolved


def build_card_update_prompt(
    *,
    request_text: str,
    card_bodies: dict[str, str],
    target_titles: list[str],
) -> str:
    cards_block = "\n\n".join(
        f"### CURRENT CARD: {title}\n{body.strip() or 'Needs review.'}"
        for title, body in card_bodies.items()
    )
    target_block = "\n".join(f"- {title}" for title in target_titles) if target_titles else "- No existing card was explicitly named."
    return (
        "The user asked you to update workspace cards.\n\n"
        f"Target cards:\n{target_block}\n\n"
        f"User request:\n{request_text.strip()}\n\n"
        f"Current card contents:\n{cards_block}\n\n"
        "Do not create new cards unless the user explicitly asked for a new separate card.\n"
        "Do not return explanations, chat, or analysis.\n"
        "Return only the full updated card bodies using exactly this format:\n"
        "### CARD: Card Title\n"
        "Full card body\n\n"
        "Do not include commentary before or after the card bodies."
    )


def build_card_creation_prompt(
    *,
    request_text: str,
    card_bodies: dict[str, str],
) -> str:
    cards_block = "\n\n".join(
        f"### CURRENT CARD: {title}\n{body.strip() or 'Needs review.'}"
        for title, body in card_bodies.items()
    )
    return (
        "The user asked you to create a brand-new separate workspace card.\n\n"
        f"User request:\n{request_text.strip()}\n\n"
        f"Current card contents:\n{cards_block}\n\n"
        "Rules:\n"
        "- Create exactly one new polished card.\n"
        "- Do not modify or rewrite any existing card.\n"
        "- Choose a clear card title.\n"
        "- The new card should be a proper UI card body, not a chat reply.\n"
        "- Return only the new card using exactly this format:\n"
        "### CARD: Card Title\n"
        "Full card body\n\n"
        "Do not include commentary before or after the card body."
    )


def parse_card_update_response(response_text: str) -> dict[str, str]:
    matches = list(CARD_SECTION_RE.finditer(response_text or ""))
    updates: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(response_text)
        body = (response_text[start:end] or "").strip()
        if title and body:
            updates[title] = body
    return updates
