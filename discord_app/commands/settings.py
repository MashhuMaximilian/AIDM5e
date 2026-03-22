from __future__ import annotations

import discord


def register(settings_group, h) -> None:
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
