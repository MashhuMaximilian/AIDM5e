from __future__ import annotations

import discord


def _member_can_manage_global_settings(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False
    if interaction.user.id == interaction.guild.owner_id:
        return True
    guild_permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(guild_permissions and guild_permissions.administrator)


def register(set_group, h) -> None:
    tools_group = discord.app_commands.Group(name="tools", description="Toggle AI tool access for this server.")
    set_group.add_command(tools_group)

    @tools_group.command(name="on", description="Enable AI tool access (function calling, card editing, etc.).")
    async def set_tools_on(interaction: discord.Interaction):
        if not _member_can_manage_global_settings(interaction):
            await h.send_interaction_message(
                interaction,
                "Only the server owner or an administrator can manage tool settings.",
                ephemeral=True,
            )
            return

        await h.asyncio.to_thread(
            h.set_guild_tools_mode,
            interaction.guild.id,
            "on",
        )
        await h.send_interaction_message(interaction, "Tools enabled.", ephemeral=True)

    @tools_group.command(name="off", description="Disable AI tool access — chat-only mode.")
    async def set_tools_off(interaction: discord.Interaction):
        if not _member_can_manage_global_settings(interaction):
            await h.send_interaction_message(
                interaction,
                "Only the server owner or an administrator can manage tool settings.",
                ephemeral=True,
            )
            return

        await h.asyncio.to_thread(
            h.set_guild_tools_mode,
            interaction.guild.id,
            "off",
        )
        await h.send_interaction_message(interaction, "Tools disabled.", ephemeral=True)