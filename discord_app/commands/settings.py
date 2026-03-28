from __future__ import annotations

import discord

from ai_services.gemini_client import is_gemini_auth_error
from ai_services.guild_api_keys import GEMINI_PROVIDER


def _member_can_manage_global_settings(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False
    if interaction.user.id == interaction.guild.owner_id:
        return True
    guild_permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(guild_permissions and guild_permissions.administrator)


def register(settings_group, h) -> None:
    global_group = discord.app_commands.Group(name="global", description="Guild-wide API key settings.")
    settings_group.add_command(global_group)

    async def _validate_and_store_guild_key(
        interaction: discord.Interaction,
        *,
        api_key: str,
        action_label: str,
    ) -> None:
        if not _member_can_manage_global_settings(interaction):
            await h.send_interaction_message(
                interaction,
                "Only the server owner or an administrator can manage global API keys.",
                ephemeral=True,
            )
            return

        normalized_key = (api_key or "").strip()
        if not normalized_key:
            await h.send_interaction_message(interaction, "API key cannot be empty.", ephemeral=True)
            return

        await h.send_command_ack(interaction, f"{action_label} the guild Gemini API key...")
        try:
            await h.asyncio.to_thread(
                h.gemini_client.generate_text,
                "Reply with exactly OK.",
                "Return exactly OK.",
                None,
                api_key=normalized_key,
            )
        except Exception as exc:
            if is_gemini_auth_error(exc):
                await h.send_interaction_message(
                    interaction,
                    "Gemini rejected that API key. Please check it and try again.",
                    ephemeral=True,
                )
                return
            raise

        status = await h.asyncio.to_thread(
            h.set_guild_api_key,
            interaction.guild.id,
            interaction.guild.name,
            GEMINI_PROVIDER,
            normalized_key,
            actor_discord_user_id=interaction.user.id,
            dm_role_name=h.DM_ROLE_NAME,
        )
        await h.send_interaction_message(
            interaction,
            (
                f"Guild Gemini API key saved successfully.\n"
                f"• provider: `{status.provider}`\n"
                f"• last4: `****{status.key_last4}`\n"
                f"• active: `{status.is_active}`"
            ),
            ephemeral=True,
        )

    @global_group.command(name="set-api-key", description="Set the Gemini API key for this server.")
    @discord.app_commands.describe(api_key="The Gemini API key to store for this server.")
    async def settings_global_set_api_key(interaction: discord.Interaction, api_key: str):
        await _validate_and_store_guild_key(interaction, api_key=api_key, action_label="Validating and saving")

    @global_group.command(name="rotate-api-key", description="Replace the current Gemini API key for this server.")
    @discord.app_commands.describe(api_key="The replacement Gemini API key for this server.")
    async def settings_global_rotate_api_key(interaction: discord.Interaction, api_key: str):
        await _validate_and_store_guild_key(interaction, api_key=api_key, action_label="Validating and rotating")

    @global_group.command(name="api-key-status", description="Show whether a Gemini API key is configured for this server.")
    async def settings_global_api_key_status(interaction: discord.Interaction):
        if not _member_can_manage_global_settings(interaction):
            await h.send_interaction_message(
                interaction,
                "Only the server owner or an administrator can inspect global API key status.",
                ephemeral=True,
            )
            return

        status = await h.asyncio.to_thread(
            h.get_guild_api_key_status,
            interaction.guild.id,
            provider=GEMINI_PROVIDER,
        )
        if not status.has_key:
            await h.send_interaction_message(
                interaction,
                (
                    "No Gemini API key is configured for this server yet.\n"
                    "Use `/settings global set-api-key` to add one."
                ),
                ephemeral=True,
            )
            return

        last_validated = status.last_validated_at.isoformat() if status.last_validated_at else "never"
        last_error = status.last_error_at.isoformat() if status.last_error_at else "none"
        error_message = status.last_error_message or "none"
        await h.send_interaction_message(
            interaction,
            (
                f"**Guild Gemini API key status**\n"
                f"• provider: `{status.provider}`\n"
                f"• last4: `****{status.key_last4}`\n"
                f"• active: `{status.is_active}`\n"
                f"• last_validated_at: `{last_validated}`\n"
                f"• last_error_at: `{last_error}`\n"
                f"• last_error_message: `{error_message}`"
            ),
            ephemeral=True,
        )

    @global_group.command(name="remove-api-key", description="Remove the stored Gemini API key for this server.")
    @discord.app_commands.describe(confirm="Set to true to confirm deleting the current stored key.")
    async def settings_global_remove_api_key(interaction: discord.Interaction, confirm: bool = False):
        if not _member_can_manage_global_settings(interaction):
            await h.send_interaction_message(
                interaction,
                "Only the server owner or an administrator can remove global API keys.",
                ephemeral=True,
            )
            return
        if not confirm:
            await h.send_interaction_message(
                interaction,
                "Re-run this with `confirm:true` to remove the stored Gemini API key for this server.",
                ephemeral=True,
            )
            return

        deleted = await h.asyncio.to_thread(
            h.delete_guild_api_key,
            interaction.guild.id,
            provider=GEMINI_PROVIDER,
        )
        await h.send_interaction_message(
            interaction,
            "Removed the stored Gemini API key for this server." if deleted else "No stored Gemini API key was found for this server.",
            ephemeral=True,
        )

    @settings_group.command(name="images", description="Configure automatic post-session image generation for this campaign.")
    @discord.app_commands.describe(
        mode="Whether images are generated automatically after summaries.",
        quality="Default quality policy for automatic session images.",
        max_scenes="Optional cap for how many scenes can be generated automatically. Use 0 to clear the cap.",
        include_dm_context="Whether automatic images can consume DM-private context.",
        post_channel="Optional post target. Defaults to #session-summary when unset.",
    )
    @discord.app_commands.choices(mode=h.IMAGE_MODE_CHOICES, quality=h.IMAGE_QUALITY_CHOICES)
    async def settings_images(
        interaction: discord.Interaction,
        mode: discord.app_commands.Choice[str] | None = None,
        quality: discord.app_commands.Choice[str] | None = None,
        max_scenes: int | None = None,
        include_dm_context: bool | None = None,
        post_channel: str | None = None,
    ):
        if not h._member_is_dm(interaction):
            await h.send_interaction_message(
                interaction,
                f"Only members with the `{h.DM_ROLE_NAME}` role can update campaign image settings.",
                ephemeral=True,
            )
            return

        category = interaction.channel.category
        if category is None:
            await h.send_interaction_message(interaction, "This command must be used inside a campaign category.", ephemeral=True)
            return

        current = await h.asyncio.to_thread(h.get_campaign_image_settings, category.id)
        new_max_scenes = current.session_image_max_scenes
        if max_scenes is not None:
            new_max_scenes = None if max_scenes <= 0 else max_scenes

        new_post_channel_id = current.session_image_post_channel_id
        if post_channel is not None:
            resolved_channel = interaction.guild.get_channel(int(post_channel))
            if not isinstance(resolved_channel, discord.TextChannel) or resolved_channel.category_id != category.id:
                await h.send_interaction_message(
                    interaction,
                    "The post channel must be a text channel inside this campaign category.",
                    ephemeral=True,
                )
                return
            new_post_channel_id = int(post_channel)

        updated = await h.asyncio.to_thread(
            h.update_campaign_image_settings,
            category.id,
            session_image_mode=mode.value if mode else current.session_image_mode,
            session_image_quality=quality.value if quality else current.session_image_quality,
            session_image_max_scenes=new_max_scenes,
            session_image_include_dm_context=include_dm_context if include_dm_context is not None else current.session_image_include_dm_context,
            session_image_post_channel_id=new_post_channel_id,
        )

        post_target = interaction.guild.get_channel(updated.session_image_post_channel_id) if updated.session_image_post_channel_id else discord.utils.get(category.text_channels, name="session-summary")
        post_label = post_target.mention if isinstance(post_target, discord.TextChannel) else "#session-summary"
        max_scenes_label = updated.session_image_max_scenes if updated.session_image_max_scenes is not None else "no cap"
        await h.send_interaction_message(
            interaction,
            (
                f"**Image settings for {category.mention}**\n"
                f"• mode: `{updated.session_image_mode}`\n"
                f"• quality: `{updated.session_image_quality}`\n"
                f"• max_scenes: `{max_scenes_label}`\n"
                f"• include_dm_context: `{updated.session_image_include_dm_context}`\n"
                f"• post_channel: {post_label}"
            ),
            ephemeral=True,
        )

    @settings_images.autocomplete("post_channel")
    async def settings_images_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await h.channel_autocomplete(interaction, current)
