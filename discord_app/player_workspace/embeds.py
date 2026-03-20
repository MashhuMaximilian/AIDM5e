import discord

from .constants import CARD_COLORS, CARD_TITLES, MISSING_PLACEHOLDER
from .rendering import (
    _build_core_status_resources_block,
    _build_highlight_block,
    _build_quick_skills_summary,
    _extract_item_names,
    _extract_rule_labels,
    _format_ability_grid,
)
from .text import (
    _display_mode_label,
    _display_status_label,
    _format_single_line_code_block,
    _is_missing_placeholder,
    _split_field_blocks,
    _truncate_embed_value,
    _truncate_text_block,
    _wrap_tags,
)


def _build_generic_card_embed(
    *,
    title: str,
    card_key: str,
    body: str,
    display_name: str,
    part_index: int,
    part_count: int,
) -> discord.Embed:
    embed = discord.Embed(title=title, color=CARD_COLORS.get(card_key, discord.Color.light_grey()))
    embed.set_author(name=display_name)
    blocks = _split_field_blocks(body)
    field_count = 0
    description_parts: list[str] = []
    for label, value in blocks:
        if label and value and field_count < 8:
            embed.add_field(name=label, value=_truncate_embed_value(value), inline=False)
            field_count += 1
            continue
        if label and not value:
            description_parts.append(f"**{label}**")
            continue
        if label and value:
            description_parts.append(f"**{label}:** {value}")
            continue
        if value:
            description_parts.append(value)
    if description_parts and not embed.description:
        embed.description = _truncate_embed_value("\n\n".join(description_parts), limit=4096)
    if part_count > 1:
        embed.set_footer(text=f"Part {part_index}/{part_count}")
    return embed


def build_character_card_embed(
    *,
    display_name: str,
    player_name: str | None,
    mode: str,
    status: str,
    build_line: str | None,
    concept: str | None,
    source_summary: str | None,
    missing_info: list[str],
    card_links: dict[str, str],
    public_publish_state: str = "not published",
    dm_publish_state: str = "not published",
    sheet_body: str | None = None,
    skills_body: str | None = None,
    profile_body: str | None = None,
    rules_body: str | None = None,
    items_body: str | None = None,
) -> discord.Embed:
    del missing_info, card_links
    status_color = {
        "draft": discord.Color.blurple(),
        "needs_review": discord.Color.orange(),
        "approved": discord.Color.green(),
        "published_public": discord.Color.green(),
        "published_dm": discord.Color.dark_teal(),
    }.get(status, CARD_COLORS["character_card"])
    embed = discord.Embed(
        title=display_name,
        description=concept or "Draft character workspace.",
        color=status_color,
    )
    embed.set_author(name="Character Workspace")
    embed.add_field(name="Player", value=player_name or MISSING_PLACEHOLDER, inline=True)
    embed.add_field(name="Status", value=f"`{_display_status_label(status)}`", inline=True)
    embed.add_field(name="Mode", value=f"`{_display_mode_label(mode)}`", inline=True)
    embed.add_field(name="Build", value=_truncate_embed_value(_format_single_line_code_block(build_line or MISSING_PLACEHOLDER), 300), inline=False)
    embed.add_field(name="Core Status & Resources", value=_truncate_embed_value(_build_core_status_resources_block(sheet_body or "", skills_body or ""), 1024), inline=False)
    ability_grid = _format_ability_grid(sheet_body or "")
    if ability_grid:
        embed.add_field(name="Ability Scores", value=_truncate_embed_value(ability_grid, 700), inline=False)
    quick_skills = _build_quick_skills_summary(skills_body or "")
    if quick_skills:
        embed.add_field(name="Quick Skills", value=_truncate_embed_value(quick_skills, 1024), inline=False)
    rule_tags = _wrap_tags(_extract_rule_labels(rules_body or ""), max_items=6)
    item_tags = _wrap_tags(_extract_item_names(items_body or ""), max_items=6)
    if rule_tags and not _is_missing_placeholder(rule_tags):
        embed.add_field(name="Rules Snapshot", value=_truncate_embed_value(rule_tags, 1024), inline=False)
    if item_tags and not _is_missing_placeholder(item_tags):
        embed.add_field(name="Gear Snapshot", value=_truncate_embed_value(item_tags, 1024), inline=False)
    embed.add_field(name="Signature / Highlights", value=_truncate_embed_value(_build_highlight_block(profile_body or "", concept), 1024), inline=False)
    footer_bits = [
        _display_mode_label(mode),
        _display_status_label(status),
        f"Public: {public_publish_state}",
        f"DM: {dm_publish_state}",
    ]
    if source_summary:
        footer_bits.append(_truncate_text_block(source_summary, 80))
    embed.set_footer(text=" • ".join(bit for bit in footer_bits if bit))
    return embed


def build_player_card_embed(
    *,
    card_key: str,
    display_name: str,
    body: str,
    part_index: int,
    part_count: int,
) -> discord.Embed:
    return _build_generic_card_embed(
        title=CARD_TITLES.get(card_key, card_key.replace("_", " ").title()),
        card_key=card_key,
        body=body,
        display_name=display_name,
        part_index=part_index,
        part_count=part_count,
    )
