from __future__ import annotations

import discord
from discord import app_commands


def register(tree, h) -> None:
    @tree.command(name="help", description="Show command help and campaign onboarding guidance.")
    @app_commands.describe(topic="Optional topic to explain in more detail.")
    @app_commands.choices(
        topic=[app_commands.Choice(name=label, value=value) for value, label in h.HELP_TOPICS]
    )
    async def help_command(
        interaction: discord.Interaction,
        topic: app_commands.Choice[str] | None = None,
    ):
        help_topic = topic.value if topic else "overview"
        await h.send_interaction_message(interaction, h._build_help_text(help_topic), ephemeral=True)

    @tree.command(name="reference", description="Read messages, files, or a URL and answer from them.")
    @app_commands.describe(
        query="What you want AIDM to extract, explain, or answer from the references.",
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to read.",
        last_n="Read the last 'n' messages (optional).",
        url="Optional public URL to read as additional context.",
        channel="Optional target channel and memory for the answer. Defaults to this channel.",
        thread="Optional target thread and memory for the answer.",
        use_context="Whether to include campaign context from #context."
    )
    @app_commands.choices(use_context=h.USE_CONTEXT_CHOICES)
    async def reference(
        interaction: discord.Interaction,
        query: str,
        start: str = None,
        end: str = None,
        message_ids: str = None,
        last_n: int = None,
        url: str = None,
        channel: str = None,
        thread: str = None,
        use_context: app_commands.Choice[str] | None = None,
    ):
        await interaction.response.defer()

        channel_id = int(channel) if channel else interaction.channel.id
        thread_id = int(thread) if thread else None
        category_id = h.get_category_id(interaction)
        assigned_memory = await h.get_assigned_memory(channel_id, category_id, thread_id=thread_id)
        if not assigned_memory:
            await interaction.followup.send("No memory found for the specified parameters.")
            return

        context_block = await h.load_command_context_block(
            interaction,
            use_context=use_context.value if use_context else None,
            default_when_auto=False,
        )

        reference_chunks: list[str] = []
        if any(value is not None for value in (start, end, message_ids, last_n)):
            reference_material, options_or_error = await h.fetch_reference_material(
                interaction.channel,
                start,
                end,
                message_ids,
                last_n,
            )
            if isinstance(options_or_error, str):
                await interaction.followup.send(options_or_error)
                return
            reference_chunks.extend(reference_material)

        has_message_refs = any(value is not None for value in (start, end, message_ids, last_n))

        if not reference_chunks and not url:
            await interaction.followup.send("You must provide message selectors and/or a public URL.")
            return

        if url and not has_message_refs:
            try:
                response = await h.answer_from_public_url(
                    query=query,
                    url=url,
                    channel_id=channel_id,
                    thread_id=thread_id,
                    assigned_memory=assigned_memory,
                    context_block=context_block,
                )
            except Exception as exc:
                await interaction.followup.send(f"Could not read the URL: {exc}")
                return
        else:
            if url:
                try:
                    reference_chunks.append(f"[Public URL: {url}]\n{await h.extract_public_url_text(url)}")
                except Exception as exc:
                    reference_chunks.append(
                        f"[Public URL could not be fetched directly: {url}. Reason: {exc}. "
                        "Use the other provided material and note that the URL may require a different retrieval path.]"
                    )

            response = await h.answer_from_references(
                query=query,
                reference_material=reference_chunks,
                channel_id=channel_id,
                assigned_memory=assigned_memory,
                thread_id=thread_id,
                url=url,
                context_block=context_block,
            )
        await h.send_response(
            interaction,
            response,
            channel_id=channel_id,
            thread_id=thread_id,
            backup_channel_name="telldm",
        )

    @reference.autocomplete('channel')
    async def reference_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await h.channel_autocomplete(interaction, current)

    @reference.autocomplete('thread')
    async def reference_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await h.thread_autocomplete(interaction, current)

    @tree.command(name="feedback", description="Send feedback to #feedback and generate a recap there.")
    async def feedback(interaction: discord.Interaction, suggestions: str):
        await interaction.response.defer()

        feedback_channel = discord.utils.get(interaction.channel.category.channels, name="feedback")
        if feedback_channel is None:
            guild = interaction.guild
            feedback_channel = await guild.create_text_channel(name="feedback", category=interaction.channel.category)
            await interaction.followup.send(f"The #feedback channel was not found, so I created it in the same category.")

        await feedback_channel.send(f"Feedback from {interaction.user.name}: {suggestions}")
        await interaction.followup.send(f"Your feedback has been sent to {feedback_channel.mention}.")

        messages = []
        async for message in feedback_channel.history(limit=300):
            messages.append(f"{message.author.name}: {message.content}")

        if not messages:
            await interaction.followup.send(f"No messages found in {feedback_channel.mention}.")
            return

        last_message = messages[0]
        conversation_history = "\n".join(reversed(messages))
        category_id = h.get_category_id(interaction)
        assigned_memory = await h.get_assigned_memory(feedback_channel.id, category_id, thread_id=None)
        prompt = h.build_feedback_prompt(conversation_history, last_message)
        response = await h.get_assistant_response(prompt, feedback_channel.id, thread_id=None, assigned_memory=assigned_memory)

        await h.send_response(interaction, response, channel_id=None, thread_id=None, backup_channel_name="feedback")
        await interaction.followup.send(f"Feedback has been processed and a recap has been posted in {feedback_channel.mention}.")

    @tree.command(name="invite", description="Initialize the default AIDM channel layout for this category.")
    async def invite_command(interaction: discord.Interaction):
        category = interaction.channel.category
        created_category = False
        if not category:
            base_name = getattr(interaction.channel, "name", None) or interaction.guild.name
            category = await interaction.guild.create_category(base_name.replace("-", " ").title())
            created_category = True

        await h.send_command_ack(interaction, "Initializing campaign...")

        try:
            invite_result = await h.initialize_threads(category)
        except ValueError as exc:
            await interaction.followup.send(str(exc))
            return

        created = ", ".join(invite_result["created"]) if invite_result["created"] else "none"
        reused = ", ".join(invite_result["reused"]) if invite_result["reused"] else "none"
        created_voice = ", ".join(invite_result["created_voice"]) if invite_result["created_voice"] else "none"
        reused_voice = ", ".join(invite_result["reused_voice"]) if invite_result["reused_voice"] else "none"
        await interaction.followup.send(
            f"Campaign initialized for **{category.name}**.\n"
            f"Created category: {'yes' if created_category else 'no'}\n"
            f"Created channels: {created}\n"
            f"Reused channels: {reused}\n"
            f"Created voice channels: {created_voice}\n"
            f"Reused voice channels: {reused_voice}"
        )
        if hasattr(interaction.channel, "send"):
            await h.send_response_in_chunks(interaction.channel, h._build_invite_onboarding_message(category))

        help_channel = discord.utils.get(category.text_channels, name="help")
        if help_channel is not None:
            for section in h._build_help_guide_sections():
                await h.send_response_in_chunks(help_channel, section)

            assigned_memory = await h.get_assigned_memory(help_channel.id, category.id, thread_id=None)
            if assigned_memory:
                greeting_prompt = h._build_help_greeting_prompt(category)
                greeting = await h.get_assistant_response(
                    greeting_prompt,
                    help_channel.id,
                    category.id,
                    None,
                    assigned_memory,
                )
                if greeting:
                    await h.send_response_in_chunks(help_channel, greeting)
