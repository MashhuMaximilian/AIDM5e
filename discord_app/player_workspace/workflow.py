import re
from typing import Any

import discord

from .constants import CARD_TITLES, EMBED_PLACEHOLDER, PLAYER_CARD_HISTORY_LIMIT
from .embeds import build_character_card_embed, build_player_card_embed
from .parsing import _skills_card_is_sparse, parse_core_stat_updates
from .rendering import (
    apply_sheet_stat_updates,
    apply_workspace_updates,
    build_character_card_body,
    build_items_card_body,
    build_player_card_messages,
    build_skills_card_body,
)
from .text import (
    _is_missing_placeholder,
    _section_map,
    _strip_markdown,
    slugify_entity_key,
    split_player_card_body,
)


def parse_player_card_fragment(message: discord.Message) -> dict[str, Any] | None:
    if message.embeds:
        embed = message.embeds[0]
        matched_card_key = None
        for card_key, title in CARD_TITLES.items():
            if embed.title == title:
                matched_card_key = card_key
                break
        if matched_card_key is None and getattr(embed.author, "name", "") == "Character Workspace":
            matched_card_key = "character_card"
        if matched_card_key:
            part_index = 1
            part_count = 1
            footer_text = getattr(embed.footer, "text", "") or ""
            match = re.search(r"(\d+)\s*/\s*(\d+)", footer_text)
            if match:
                part_index = int(match.group(1))
                part_count = int(match.group(2))
            return {
                "metadata": {
                    "card_key": matched_card_key,
                    "part_index": part_index,
                    "part_count": part_count,
                },
                "body": embed.description or "",
                "message": message,
            }

    content = message.content or ""
    sections = [section.strip() for section in content.split("\n\n") if section.strip()]
    if not sections:
        return None

    title_line = sections[0]
    matched_card_key = None
    for card_key, title in CARD_TITLES.items():
        if title_line == f"**{title}**":
            matched_card_key = card_key
            break
    if not matched_card_key:
        return None

    part_index = 1
    part_count = 1
    body_sections = sections[1:]
    if body_sections and body_sections[0].startswith("• Part:"):
        marker = body_sections[0]
        match = re.search(r"(\d+)\s*/\s*(\d+)", marker)
        if match:
            part_index = int(match.group(1))
            part_count = int(match.group(2))
        body_sections = body_sections[1:]

    body = "\n\n".join(body_sections).strip() if body_sections else ""
    return {
        "metadata": {
            "card_key": matched_card_key,
            "part_index": part_index,
            "part_count": part_count,
        },
        "body": body,
        "message": message,
    }


def collect_player_card_body(messages: list[discord.Message]) -> str:
    parts: list[str] = []
    for message in messages:
        fragment = parse_player_card_fragment(message)
        if not fragment:
            continue
        body = str(fragment.get("body") or "").strip()
        if body:
            parts.append(body)
    return "\n\n".join(parts).strip()


def _display_name_from_thread(thread: discord.Thread) -> str:
    prefix = "Character - "
    if thread.name.startswith(prefix):
        candidate = thread.name[len(prefix):].strip()
        if candidate:
            return candidate
    return thread.name


class PlayerCardEditModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        entity_key: str,
        display_name: str,
        card_key: str,
        initial_body: str,
    ) -> None:
        super().__init__(title=f"Edit {CARD_TITLES.get(card_key, card_key)}")
        self.entity_key = entity_key
        self.display_name = display_name
        self.card_key = card_key

        cleaned = (initial_body or "").strip()
        default_value = cleaned if len(cleaned) <= 4000 else None
        placeholder = "Replace this card content. Markdown is fine."
        if cleaned and default_value is None:
            placeholder = "Current card is long. Paste the full replacement text here."

        self.card_body = discord.ui.TextInput(
            label="Card content",
            style=discord.TextStyle.paragraph,
            required=True,
            default=default_value,
            placeholder=placeholder,
            max_length=4000,
        )
        self.add_item(self.card_body)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            await interaction.response.send_message("This button only works inside a character thread.", ephemeral=True)
            return

        existing = await load_player_card_messages(thread, self.entity_key)
        existing[self.card_key] = await upsert_player_card(
            thread,
            entity_key=self.entity_key,
            display_name=self.display_name,
            card_key=self.card_key,
            body=str(self.card_body.value),
            existing_messages=existing.get(self.card_key),
            render_mode="text",
        )
        await sync_player_workspace_cards(
            thread,
            entity_key=self.entity_key,
            display_name=self.display_name,
            existing_cards=existing,
        )
        await interaction.response.send_message(
            f"Updated {CARD_TITLES.get(self.card_key, self.card_key)} in this thread.",
            ephemeral=True,
        )


class PlayerWorkspaceCardView(discord.ui.View):
    def __init__(
        self,
        *,
        card_links: dict[str, str] | None = None,
        source_link: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        for label, key in (
            ("Sheet", "sheet_card"),
            ("Skills", "skills_card"),
            ("Profile", "profile_card"),
            ("Rules", "rules_card"),
            ("Items", "items_card"),
        ):
            url = (card_links or {}).get(key)
            if url:
                self.add_item(discord.ui.Button(label=label, url=url, row=0))
        workspace_url = (card_links or {}).get("workspace_card")
        if workspace_url:
            self.add_item(discord.ui.Button(label="Workspace", url=workspace_url, row=1))
        if source_link:
            self.add_item(discord.ui.Button(label="Source", url=source_link, row=1))

    async def _open_edit_modal(self, interaction: discord.Interaction, card_key: str) -> None:
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            await interaction.response.send_message("This button only works inside a character thread.", ephemeral=True)
            return

        display_name = _display_name_from_thread(thread)
        entity_key = slugify_entity_key(display_name)
        existing = await load_player_card_messages(thread, entity_key)
        initial_body = collect_player_card_body(existing.get(card_key, []))
        await interaction.response.send_modal(
            PlayerCardEditModal(
                entity_key=entity_key,
                display_name=display_name,
                card_key=card_key,
                initial_body=initial_body,
            )
        )

    @discord.ui.button(label="Edit Status", style=discord.ButtonStyle.secondary, custom_id="player_workspace:edit:workspace_card", row=1)
    async def edit_workspace_status(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._open_edit_modal(interaction, "workspace_card")

    @discord.ui.button(label="Edit Profile", style=discord.ButtonStyle.secondary, custom_id="player_workspace:edit:profile_card", row=1)
    async def edit_profile(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._open_edit_modal(interaction, "profile_card")

    @discord.ui.button(label="Edit Sheet", style=discord.ButtonStyle.secondary, custom_id="player_workspace:edit:sheet_card", row=1)
    async def edit_sheet(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._open_edit_modal(interaction, "sheet_card")

    @discord.ui.button(label="Edit Skills", style=discord.ButtonStyle.secondary, custom_id="player_workspace:edit:skills_card", row=2)
    async def edit_skills(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._open_edit_modal(interaction, "skills_card")

    @discord.ui.button(label="Edit Rules", style=discord.ButtonStyle.secondary, custom_id="player_workspace:edit:rules_card", row=2)
    async def edit_rules(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._open_edit_modal(interaction, "rules_card")

    @discord.ui.button(label="Edit Items", style=discord.ButtonStyle.secondary, custom_id="player_workspace:edit:items_card", row=2)
    async def edit_items(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._open_edit_modal(interaction, "items_card")

    @discord.ui.button(label="Refresh Draft", style=discord.ButtonStyle.primary, custom_id="player_workspace:refresh", row=3)
    async def refresh_workspace(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(
            "For now, rerun `/create player` with updated notes, messages, or files to refresh these maintained cards.",
            ephemeral=True,
        )

    @discord.ui.button(label="Publish Summary", style=discord.ButtonStyle.success, custom_id="player_workspace:publish", row=3)
    async def publish_workspace(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(
            "Publish actions are the next step. This will later send a curated summary to `#context` and optionally DM-only notes to `#dm-planning`.",
            ephemeral=True,
        )


def build_player_workspace_view(
    *,
    card_links: dict[str, str],
    source_link: str | None = None,
) -> discord.ui.View:
    return PlayerWorkspaceCardView(card_links=card_links, source_link=source_link)


_PLAYER_WORKSPACE_VIEW_REGISTERED = False


def register_player_workspace_views(client: discord.Client) -> None:
    global _PLAYER_WORKSPACE_VIEW_REGISTERED
    if _PLAYER_WORKSPACE_VIEW_REGISTERED:
        return
    client.add_view(PlayerWorkspaceCardView())
    _PLAYER_WORKSPACE_VIEW_REGISTERED = True


def _character_card_state_from_messages(messages: list[discord.Message], display_name: str) -> dict[str, str | None]:
    state: dict[str, str | None] = {
        "display_name": display_name,
        "player_name": None,
        "build_line": None,
        "concept": None,
    }
    if not messages:
        return state

    message = messages[0]
    body = collect_player_card_body(messages)
    if not message.embeds:
        heading_match = re.search(r"(?m)^##\s+(.+)$", body)
        if heading_match:
            state["display_name"] = heading_match.group(1).strip()
        concept_match = re.search(r"(?m)^>\s+(.+)$", body)
        if concept_match:
            state["concept"] = concept_match.group(1).strip()
        player_match = re.search(r"(?m)^\*\*Player:\*\*\s+(.+)$", body)
        if player_match and not _is_missing_placeholder(player_match.group(1)):
            state["player_name"] = player_match.group(1).strip()
        build_match = re.search(r"(?ms)^\*\*Build\*\*\s+```(?:\w+)?\n(.*?)```", body)
        if build_match:
            state["build_line"] = build_match.group(1).strip()
        return state

    embed = message.embeds[0]
    state["display_name"] = embed.title or display_name
    state["concept"] = embed.description or None
    for field in embed.fields:
        key = field.name.lower()
        if key == "player":
            state["player_name"] = field.value if not _is_missing_placeholder(field.value) else None
        elif key == "build":
            state["build_line"] = field.value.replace("```", "").replace("text\n", "").strip()
    return state


async def sync_player_workspace_cards(
    thread: discord.Thread,
    *,
    entity_key: str,
    display_name: str,
    existing_cards: dict[str, list[discord.Message]] | None = None,
    source_link: str | None = None,
) -> dict[str, list[discord.Message]]:
    cards = existing_cards or await load_player_card_messages(thread, entity_key)
    state = _character_card_state_from_messages(cards.get("character_card", []), display_name)
    profile_body = collect_player_card_body(cards.get("profile_card", []))
    sheet_body = collect_player_card_body(cards.get("sheet_card", []))
    skills_body = collect_player_card_body(cards.get("skills_card", []))
    rules_body = collect_player_card_body(cards.get("rules_card", []))
    items_body = collect_player_card_body(cards.get("items_card", []))
    workspace_body = collect_player_card_body(cards.get("workspace_card", []))
    workspace_sections = _section_map(workspace_body)

    if not skills_body and sheet_body:
        skills_body = build_skills_card_body(sheet_body)
        cards["skills_card"] = await upsert_player_card(
            thread,
            entity_key=entity_key,
            display_name=display_name,
            card_key="skills_card",
            body=skills_body,
            existing_messages=cards.get("skills_card"),
            render_mode="text",
        )

    if not items_body:
        items_body = build_items_card_body("")
        cards["items_card"] = await upsert_player_card(
            thread,
            entity_key=entity_key,
            display_name=display_name,
            card_key="items_card",
            body=items_body,
            existing_messages=cards.get("items_card"),
            render_mode="text",
        )

    character_body = build_character_card_body(
        display_name=state.get("display_name") or display_name,
        player_name=state.get("player_name"),
        mode=_strip_markdown(workspace_sections.get("mode", "draft")),
        status=_strip_markdown(workspace_sections.get("status", "draft")),
        build_line=state.get("build_line"),
        concept=state.get("concept"),
        source_summary=workspace_sections.get("source summary") or workspace_sections.get("source"),
        missing_info=[
            line.lstrip("• ").strip()
            for line in (workspace_sections.get("needs review") or "").splitlines()
            if line.strip()
        ],
        card_links={},
        public_publish_state=_strip_markdown(workspace_sections.get("public context", "not published")),
        dm_publish_state=_strip_markdown(workspace_sections.get("dm notes", "not published")),
        sheet_body=sheet_body,
        skills_body=skills_body,
        profile_body=profile_body,
    )
    cards["character_card"] = await upsert_player_card(
        thread,
        entity_key=entity_key,
        display_name=display_name,
        card_key="character_card",
        body=character_body,
        existing_messages=cards.get("character_card"),
        embed=build_character_card_embed(
            display_name=state.get("display_name") or display_name,
            player_name=state.get("player_name"),
            mode=_strip_markdown(workspace_sections.get("mode", "draft")),
            status=_strip_markdown(workspace_sections.get("status", "draft")),
            build_line=state.get("build_line"),
            concept=state.get("concept"),
            source_summary=workspace_sections.get("source summary") or workspace_sections.get("source"),
            missing_info=[
                line.lstrip("• ").strip()
                for line in (workspace_sections.get("needs review") or "").splitlines()
                if line.strip()
            ],
            card_links={},
            public_publish_state=_strip_markdown(workspace_sections.get("public context", "not published")),
            dm_publish_state=_strip_markdown(workspace_sections.get("dm notes", "not published")),
            sheet_body=sheet_body,
            skills_body=skills_body,
            profile_body=profile_body,
            rules_body=rules_body,
            items_body=items_body,
        ),
        render_mode="embed",
        view=build_player_workspace_view(
            card_links={
                "workspace_card": cards.get("workspace_card", [None])[0].jump_url if cards.get("workspace_card") else "",
                "sheet_card": cards.get("sheet_card", [None])[0].jump_url if cards.get("sheet_card") else "",
                "skills_card": cards.get("skills_card", [None])[0].jump_url if cards.get("skills_card") else "",
                "profile_card": cards.get("profile_card", [None])[0].jump_url if cards.get("profile_card") else "",
                "rules_card": cards.get("rules_card", [None])[0].jump_url if cards.get("rules_card") else "",
                "items_card": cards.get("items_card", [None])[0].jump_url if cards.get("items_card") else "",
            },
            source_link=source_link or workspace_sections.get("latest source post"),
        ),
    )
    return cards


async def maybe_handle_player_workspace_message(message: discord.Message) -> bool:
    thread = message.channel
    if not isinstance(thread, discord.Thread):
        return False
    parent = getattr(thread, "parent", None)
    if not isinstance(parent, discord.TextChannel) or parent.name != "character-sheets":
        return False
    if not thread.name.startswith("Character - "):
        return False

    updates = parse_core_stat_updates(message.content or "")
    if not updates:
        return False

    display_name = _display_name_from_thread(thread)
    entity_key = slugify_entity_key(display_name)

    async with thread.typing():
        cards = await load_player_card_messages(thread, entity_key)
        sheet_body = collect_player_card_body(cards.get("sheet_card", []))
        if not sheet_body:
            return False

        existing_skills_body = collect_player_card_body(cards.get("skills_card", []))
        updated_sheet_body = apply_sheet_stat_updates(sheet_body, updates)
        cards["sheet_card"] = await upsert_player_card(
            thread,
            entity_key=entity_key,
            display_name=display_name,
            card_key="sheet_card",
            body=updated_sheet_body,
            existing_messages=cards.get("sheet_card"),
            render_mode="text",
        )

        rebuilt_skills_body = build_skills_card_body(updated_sheet_body)
        skills_body = existing_skills_body if existing_skills_body and not _skills_card_is_sparse(existing_skills_body) else rebuilt_skills_body
        cards["skills_card"] = await upsert_player_card(
            thread,
            entity_key=entity_key,
            display_name=display_name,
            card_key="skills_card",
            body=skills_body,
            existing_messages=cards.get("skills_card"),
            render_mode="text",
        )

        workspace_body = collect_player_card_body(cards.get("workspace_card", []))
        if workspace_body:
            updated_workspace_body = apply_workspace_updates(workspace_body, updates)
            cards["workspace_card"] = await upsert_player_card(
                thread,
                entity_key=entity_key,
                display_name=display_name,
                card_key="workspace_card",
                body=updated_workspace_body,
                existing_messages=cards.get("workspace_card"),
                render_mode="text",
            )

        cards = await sync_player_workspace_cards(
            thread,
            entity_key=entity_key,
            display_name=display_name,
            existing_cards=cards,
        )

    summary_bits: list[str] = []
    if updates.get("ac"):
        summary_bits.append(f"AC {updates['ac']}")
    if updates.get("max_hp"):
        summary_bits.append(f"Max HP {updates['max_hp']}")
    if updates.get("current_hp"):
        summary_bits.append(f"Current HP {updates['current_hp']}")
    if updates.get("pb"):
        summary_bits.append(f"PB +{updates['pb']}")
    if updates.get("speed"):
        summary_bits.append(f"Speed {updates['speed']} ft")
    if updates.get("hit_dice"):
        summary_bits.append(f"Hit Dice {updates['hit_dice']}")

    await thread.send(f"Updated {display_name}'s maintained sheet: " + ", ".join(summary_bits))
    return True


async def load_player_card_messages(thread: discord.Thread, entity_key: str) -> dict[str, list[discord.Message]]:
    del entity_key
    grouped: dict[str, dict[int, discord.Message]] = {}
    bot_user_id = getattr(getattr(thread.guild, "me", None), "id", None)
    async for message in thread.history(limit=PLAYER_CARD_HISTORY_LIMIT, oldest_first=True):
        if bot_user_id is not None and message.author.id != bot_user_id:
            continue
        fragment = parse_player_card_fragment(message)
        if not fragment:
            continue
        metadata = fragment["metadata"]
        card_key = str(metadata.get("card_key") or "")
        part_index = int(metadata.get("part_index", 1))
        if card_key:
            grouped.setdefault(card_key, {})[part_index] = fragment["message"]

    return {card_key: [message for _, message in sorted(parts.items())] for card_key, parts in grouped.items()}


async def upsert_player_card(
    thread: discord.Thread,
    *,
    entity_key: str,
    display_name: str,
    card_key: str,
    body: str,
    existing_messages: list[discord.Message] | None = None,
    embed: discord.Embed | None = None,
    render_mode: str = "text",
    view: discord.ui.View | None = None,
) -> list[discord.Message]:
    if render_mode == "embed" and embed is not None:
        body_parts = [body]
        desired_messages = [EMBED_PLACEHOLDER]
    else:
        rendered_messages = build_player_card_messages(
            entity_key=entity_key,
            display_name=display_name,
            card_key=card_key,
            body=body,
        )
        body_parts = split_player_card_body(
            body=body,
            card_title=CARD_TITLES.get(card_key, card_key.replace("_", " ").title()),
        )
        desired_messages = rendered_messages

    current_messages = list(existing_messages or [])
    updated: list[discord.Message] = []

    for index, content in enumerate(desired_messages):
        part_body = body_parts[index] if index < len(body_parts) else body
        is_first = index == 0
        current_view = view if is_first else None
        current_embed = None
        if render_mode == "embed":
            current_embed = embed if is_first and embed is not None else build_player_card_embed(
                card_key=card_key,
                display_name=display_name,
                body=part_body,
                part_index=index + 1,
                part_count=len(desired_messages),
            )

        if index < len(current_messages):
            message = current_messages[index]
            if render_mode == "embed":
                await message.edit(content=EMBED_PLACEHOLDER, embed=current_embed, view=current_view)
            else:
                await message.edit(content=content, embed=None, view=current_view)
            updated.append(message)
        else:
            if render_mode == "embed":
                updated.append(await thread.send(content=EMBED_PLACEHOLDER, embed=current_embed, view=current_view))
            else:
                updated.append(await thread.send(content, view=current_view))

    for extra in current_messages[len(desired_messages):]:
        await extra.delete()

    return updated
