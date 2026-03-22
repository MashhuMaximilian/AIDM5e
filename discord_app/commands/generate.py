from __future__ import annotations

import discord


def register(generate_group, h) -> None:
    @generate_group.command(name="image", description="Generate images from the latest summary, selected messages, or a custom prompt.")
    @discord.app_commands.describe(
        source_mode="Where the image instructions should come from.",
        prompt="Required for custom prompt mode. Optional extra source text for message-based modes.",
        directives="Optional extra instructions layered on top of the source material.",
        quality="Image generation quality policy.",
        aspect_ratio="Optional override. Leave on Auto to let the scene decide.",
        include_dm_context="Whether DM-private context can be included for this generation run.",
        message_ids="Comma-separated message IDs for message-based generation.",
        last_n="Use the last N messages from the chosen source target.",
        channel="Optional source channel for message-based generation.",
        thread="Optional source thread for message-based generation.",
    )
    @discord.app_commands.choices(
        source_mode=h.IMAGE_SOURCE_MODE_CHOICES,
        quality=h.IMAGE_QUALITY_CHOICES,
        aspect_ratio=h.IMAGE_ASPECT_RATIO_CHOICES,
    )
    async def generate_image(
        interaction: discord.Interaction,
        source_mode: discord.app_commands.Choice[str],
        prompt: str = None,
        directives: str = None,
        quality: discord.app_commands.Choice[str] | None = None,
        aspect_ratio: discord.app_commands.Choice[str] | None = None,
        include_dm_context: bool | None = None,
        message_ids: str = None,
        last_n: int | None = None,
        channel: str = None,
        thread: str = None,
    ):
        await h.send_command_ack(interaction, "Generating images...")

        category = getattr(interaction.channel, "category", None)
        if category is None and isinstance(interaction.channel, discord.Thread):
            category = getattr(interaction.channel.parent, "category", None)
        if category is None:
            await h.send_interaction_message(interaction, "This command must be used inside a campaign category.", ephemeral=True)
            return

        settings = await h.asyncio.to_thread(h.get_campaign_image_settings, category.id)
        selected_quality = quality.value if quality else settings.session_image_quality
        allow_dm_context = include_dm_context if include_dm_context is not None else settings.session_image_include_dm_context
        aspect_ratio_override = h._normalize_image_aspect_ratio(aspect_ratio.value if aspect_ratio else None)
        context_packet = await h.compile_context_packet_from_category(category, include_dm_context=allow_dm_context)

        target_channel = interaction.channel
        source_value = source_mode.value
        if source_value == "latest_summary":
            objective_summary, narrative_summary = await h._collect_latest_session_summaries(category)
            if not objective_summary and not narrative_summary:
                await h.send_interaction_message(interaction, "Could not find a recent objective or narrative summary in #session-summary.", ephemeral=True)
                return

            candidates = await h.scene_pipeline.extract_scene_candidates(
                objective_summary=objective_summary or "",
                narrative_summary=narrative_summary or "",
                context_packet=context_packet,
                max_scenes_cap=settings.session_image_max_scenes,
            )
            selected_scenes, rationale = await h.scene_pipeline.select_final_scenes(
                candidates,
                context_packet=context_packet,
                max_scenes_cap=settings.session_image_max_scenes,
            )
            if rationale:
                await h.send_response_in_chunks(target_channel, f"**Image scene selection**\n{rationale}")
            for index, scene in enumerate(selected_scenes, start=1):
                request = h.scene_pipeline.prepare_scene_image_request(
                    scene,
                    context_packet=context_packet,
                    quality_mode=selected_quality,
                    directives=directives,
                    aspect_ratio_override=aspect_ratio_override,
                )
                images = h.gemini_client.generate_image(
                    request.prompt,
                    model_name=request.model_name,
                    aspect_ratio=request.aspect_ratio,
                    reference_images=request.reference_assets,
                )
                if not images:
                    await target_channel.send(f"Skipping `{scene.title}` because Gemini returned no image.")
                    continue
                await h._send_generated_image_message(
                    target_channel,
                    title=scene.title,
                    subtitle_lines=[
                        f"• Focus: {scene.subject_focus or 'mixed'}",
                        f"• Aspect ratio: `{request.aspect_ratio}`",
                        f"• Model: `{request.model_name}`",
                    ],
                    image_bytes=images[0]["image_bytes"],
                    mime_type=images[0]["mime_type"],
                    index=index,
                )
            await h.send_interaction_message(interaction, "Generated image set in this channel.", ephemeral=True)
            return

        selected_messages: list[discord.Message] = []
        raw_assets: list[dict] = []
        source_parts: list[str] = []
        if source_value in {"message_ids", "last_n"}:
            source_target = await h._resolve_context_source_target(interaction, channel=channel, thread=thread)
            if source_target is None:
                await h.send_interaction_message(interaction, "Could not resolve the source channel or thread.", ephemeral=True)
                return
            selected_messages, options_or_error = await h.select_messages(
                source_target,
                None,
                None,
                message_ids if source_value == "message_ids" else None,
                last_n if source_value == "last_n" else None,
            )
            if isinstance(options_or_error, str):
                await h.send_interaction_message(interaction, options_or_error, ephemeral=True)
                return
            if not selected_messages:
                await h.send_interaction_message(interaction, "No source messages were selected.", ephemeral=True)
                return
            source_material = await h._build_context_material_from_messages(selected_messages)
            source_parts.append("\n\n".join(source_material))
            raw_assets = h._extract_context_assets(selected_messages)

        if source_value == "custom_prompt":
            if not prompt:
                await h.send_interaction_message(interaction, "Custom prompt mode requires `prompt`.", ephemeral=True)
                return
            source_parts.append(prompt.strip())
        elif prompt:
            source_parts.append(prompt.strip())

        if not source_parts:
            await h.send_interaction_message(interaction, "Provide source messages or a prompt for image generation.", ephemeral=True)
            return

        brief = await h.scene_pipeline.build_direct_image_brief(
            source_material="\n\n".join(part for part in source_parts if part).strip(),
            directives=directives,
            context_packet=context_packet,
        )
        selected_asset_objects = [h._context_asset_from_raw(asset) for asset in raw_assets if asset.get("is_image")]
        request = h.scene_pipeline.prepare_direct_image_request(
            brief,
            context_packet=context_packet,
            quality_mode=selected_quality,
            directives=directives,
            aspect_ratio_override=aspect_ratio_override,
        )
        combined_reference_assets: list = []
        seen_refs: set[tuple[str, int | None]] = set()
        for asset in [*request.reference_assets, *selected_asset_objects]:
            key = (asset.url, asset.source_message_id)
            if key in seen_refs:
                continue
            seen_refs.add(key)
            combined_reference_assets.append(asset)

        images = h.gemini_client.generate_image(
            request.prompt,
            model_name=request.model_name,
            aspect_ratio=request.aspect_ratio,
            reference_images=combined_reference_assets,
        )
        if not images:
            await h.send_interaction_message(interaction, "Gemini returned no image for this request.", ephemeral=True)
            return

        await h._send_generated_image_message(
            target_channel,
            title=brief.title,
            subtitle_lines=[
                f"• Focus: {brief.subject_focus or 'mixed'}",
                f"• Aspect ratio: `{request.aspect_ratio}`",
                f"• Model: `{request.model_name}`",
            ],
            image_bytes=images[0]["image_bytes"],
            mime_type=images[0]["mime_type"],
            index=1,
        )
        await h.send_interaction_message(interaction, "Generated image in this channel.", ephemeral=True)

    @generate_image.autocomplete("channel")
    async def generate_image_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await h.channel_autocomplete(interaction, current)

    @generate_image.autocomplete("thread")
    async def generate_image_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await h.thread_autocomplete(interaction, current)
