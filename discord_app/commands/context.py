from __future__ import annotations

import logging

from discord import app_commands


def register(context_group, h) -> None:
    @context_group.command(name="add", description="Add or replace public, session, or DM context for future transcript/summary runs.")
    @app_commands.describe(
        scope="Which context bucket to update.",
        action="Whether to replace or append to that bucket.",
        note="Optional manual text to store as context.",
        tags="Optional comma-separated tags such as roster, npc, location, scene, style.",
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to include.",
        last_n="Use the last 'n' messages from the source target.",
        channel="Optional source channel. Defaults to this channel.",
        thread="Optional source thread. Overrides the source channel when set.",
    )
    @app_commands.choices(
        scope=h.CONTEXT_SCOPE_CHOICES,
        action=h.CONTEXT_WRITE_ACTION_CHOICES,
    )
    async def context_add(
        interaction,
        scope: app_commands.Choice[str],
        action: app_commands.Choice[str],
        note: str = None,
        tags: str = None,
        start: str = None,
        end: str = None,
        message_ids: str = None,
        last_n: int = None,
        channel: str = None,
        thread: str = None,
    ):
        await h.send_command_ack(interaction, "Updating context...")

        try:
            response_text = await h._update_context_scope(
                interaction,
                scope_value=scope.value,
                action_value=action.value,
                note=note,
                tags=tags,
                start=start,
                end=end,
                message_ids=message_ids,
                last_n=last_n,
                channel=channel,
                thread=thread,
            )
            await h.send_interaction_message(interaction, response_text, ephemeral=True)
        except PermissionError as exc:
            await h.send_interaction_message(interaction, str(exc), ephemeral=True)
        except Exception as exc:
            logging.exception("Error updating context: %s", exc)
            await h.send_interaction_message(interaction, f"Could not update context: {exc}", ephemeral=True)

    @context_add.autocomplete('channel')
    async def context_channel_autocomplete(interaction, current: str):
        return await h.channel_autocomplete(interaction, current)

    @context_add.autocomplete('thread')
    async def context_thread_autocomplete(interaction, current: str):
        return await h.thread_autocomplete(interaction, current)

    @context_group.command(name="clear", description="Clear one public, session, or DM context scope.")
    @app_commands.describe(scope="Which context bucket to clear.")
    @app_commands.choices(scope=h.CONTEXT_SCOPE_CHOICES)
    async def context_clear(
        interaction,
        scope: app_commands.Choice[str],
    ):
        await h.send_command_ack(interaction, "Clearing context...")
        try:
            response_text = await h._update_context_scope(
                interaction,
                scope_value=scope.value,
                action_value="clear",
                note=None,
                tags=None,
                start=None,
                end=None,
                message_ids=None,
                last_n=None,
                channel=None,
                thread=None,
            )
            await h.send_interaction_message(interaction, response_text, ephemeral=True)
        except PermissionError as exc:
            await h.send_interaction_message(interaction, str(exc), ephemeral=True)
        except Exception as exc:
            logging.exception("Error clearing context: %s", exc)
            await h.send_interaction_message(interaction, f"Could not clear context: {exc}", ephemeral=True)

    @context_group.command(name="list", description="Show the current runtime state of public, session, and DM context.")
    async def context_list(interaction):
        category = interaction.channel.category
        packet = await h.compile_context_packet_from_category(
            category,
            include_dm_context=h._member_is_dm(interaction),
        )
        blocks = [
            f"**Context status for {category.mention if category else interaction.guild.name}**",
            "",
            h._compiled_context_status(category, "public", packet.public_text, packet.public_source, len(packet.public_assets)),
            "",
            h._compiled_context_status(category, "session", packet.session_text, packet.session_source, len(packet.session_assets)),
        ]
        if h._member_is_dm(interaction):
            blocks.extend(
                [
                    "",
                    h._compiled_context_status(category, "dm", packet.dm_text, packet.dm_source, len(packet.dm_assets)),
                ]
            )
        else:
            blocks.extend(
                [
                    "",
                    "**DM Private**\n"
                    f"• Runtime state: hidden\n"
                    f"• Discord surface: {h._context_surface_label(category, 'dm')}\n"
                    f"• Edit access requires the `{h.DM_ROLE_NAME}` role",
                ]
            )
        blocks.extend(
            [
                "",
                "This reflects the effective compiled context used by the runtime. Discord-managed context entries are the source of truth. `Session Only` stays active until you replace it or clear it.",
            ]
        )
        await h.send_interaction_message(interaction, "\n".join(blocks), ephemeral=True)
