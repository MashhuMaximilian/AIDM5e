from __future__ import annotations

import logging

import discord
from discord import app_commands


def register(channel_group, h) -> None:
    @channel_group.command(name="summarize", description="Summarize selected messages. Defaults to this channel.")
    @app_commands.describe(
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to summarize.",
        query="Additional requests or context for the recap.",
        last_n="Summarize the last 'n' messages (optional).",
        channel="Optional target channel and memory for the answer. Defaults to this channel.",
        thread="Optional target thread and memory for the answer."
    )
    async def summarize(interaction: discord.Interaction, start: str = None, end: str = None, message_ids: str = None, query: str = None, last_n: int = None, channel: str = None, thread: str = None):
        await interaction.response.defer()

        channel_id = int(channel) if channel else interaction.channel.id
        thread_id = int(thread) if thread else None
        category_id = h.get_category_id(interaction)

        assigned_memory = await h.get_assigned_memory(channel_id, category_id, thread_id=thread_id)
        conversation_history, options_or_error = await h.fetch_reference_material(interaction.channel, start, end, message_ids, last_n)
        if isinstance(options_or_error, str):
            await interaction.followup.send(options_or_error)
            return

        options = options_or_error
        response = await h.summarize_conversation(interaction, conversation_history, options, query, channel_id, thread_id, assigned_memory)
        if response:
            await h.send_response(interaction, response, channel_id=channel_id, thread_id=thread_id)
        else:
            await interaction.followup.send("No content to summarize.")

    @summarize.autocomplete('channel')
    async def summarize_channel_autocomplete(interaction, current: str):
        return await h.channel_autocomplete(interaction, current)

    @summarize.autocomplete('thread')
    async def summarize_thread_autocomplete(interaction, current: str):
        return await h.thread_autocomplete(interaction, current)

    @channel_group.command(name="send", description="Copy selected messages to another channel or thread.")
    @app_commands.describe(
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to send (comma-separated if multiple).",
        last_n="Send the last 'n' messages (optional).",
        channel="Target channel in this category. Defaults to the current channel.",
        thread="Optional target thread inside the chosen channel."
    )
    async def send(
        interaction: discord.Interaction,
        start: str = None,
        end: str = None,
        message_ids: str = None,
        last_n: int = None,
        channel: str = None,
        thread: str = None
    ):
        await h.send_command_ack(interaction, "Sending messages...")

        channel_id = int(channel) if channel else interaction.channel.id
        thread_id = int(thread) if thread else None
        category_id = h.get_category_id(interaction)

        conversation_history, options_or_error = await h.fetch_conversation_history(interaction.channel, start, end, message_ids, last_n)
        if isinstance(options_or_error, str):
            await interaction.followup.send(options_or_error)
            return

        target_channel_obj = interaction.guild.get_channel(channel_id)
        if not target_channel_obj:
            await interaction.followup.send("Target channel not found.")
            return
        if target_channel_obj.category_id != interaction.channel.category_id:
            await interaction.followup.send(f"Cannot send messages to {target_channel_obj.name}. Must be in the same category.")
            return

        target = target_channel_obj
        if thread:
            target = await interaction.guild.fetch_channel(thread_id)

        for message in conversation_history:
            await h.send_response_in_chunks(target, message)

        assigned_memory = await h.get_assigned_memory(channel_id, category_id, thread_id=thread_id)
        if assigned_memory:
            imported_content = "\n\n".join(conversation_history)
            acknowledgment_prompt = (
                "A user transferred the following Discord content into this channel or thread. "
                "Acknowledge briefly what was added and mention the most important fact or takeaway "
                "AIDM should now keep in mind for this memory. Keep the answer to at most 3 short bullets.\n\n"
                f"Transferred content:\n{imported_content}"
            )
            acknowledgment = await h.get_assistant_response(
                acknowledgment_prompt,
                channel_id,
                category_id,
                thread_id,
                assigned_memory=assigned_memory,
                send_message=False,
            )
            if acknowledgment:
                await h.send_response_in_chunks(target, acknowledgment)

        await interaction.followup.send(f"Messages sent successfully to {'thread' if thread else 'channel'} <#{target.id}>.")

    @send.autocomplete('channel')
    async def send_channel_autocomplete(interaction, current: str):
        choices = await h.channel_autocomplete(interaction, current)
        return choices[:25]

    @send.autocomplete('thread')
    async def send_thread_autocomplete(interaction, current: str):
        return await h.thread_autocomplete(interaction, current)

    @channel_group.command(name="start", description="Create a channel/thread in this category and assign its memory.")
    @app_commands.describe(
        channel="Choose an existing channel or 'NEW CHANNEL' to create a new one.",
        channel_name="Name for the new channel (only if 'NEW CHANNEL' is selected).",
        thread_name="Name for the new thread (only if you choose 'CREATE A NEW THREAD').",
        memory="Choose an existing memory or create a new one.",
        memory_name="Provide a name for the new memory (only if 'CREATE NEW MEMORY' is selected).",
        always_on="Set the assistant always on or off."
    )
    @app_commands.choices(always_on=[
        app_commands.Choice(name="On", value="on"),
        app_commands.Choice(name="Off", value="off")
    ])
    async def startnew_command(
        interaction: discord.Interaction,
        channel: str,
        always_on: app_commands.Choice[str],
        memory: str,
        memory_name: str = None,
        channel_name: str = None,
        thread_name: str = None,
        thread: str = None
    ):
        if channel == "NEW CHANNEL" and not channel_name:
            await h.send_interaction_message(interaction, "Error: You must provide a name for the new channel.")
            return
        if thread == "NEW THREAD" and not thread_name:
            await h.send_interaction_message(interaction, "Error: You must provide a name for the new thread.")
            return
        if memory == "CREATE NEW MEMORY" and not memory_name:
            await h.send_interaction_message(interaction, "Error: You must provide a name for the new memory.")
            return

        await h.send_command_ack(interaction, "Creating channel or thread...")

        guild = interaction.guild
        category = interaction.channel.category
        target_channel = await h.handle_channel_creation(channel, channel_name, guild, category, interaction)
        if target_channel is None:
            return

        logging.info(f"Target channel ID: {target_channel.id}, Name: {target_channel.name}")

        thread_obj = None
        if thread == "NEW THREAD":
            thread_obj, error = await h.handle_thread_creation(interaction, target_channel, thread_name, category.id, memory_name)
            if error:
                await h.send_interaction_message(interaction, error)
                return
        elif thread:
            thread_obj = await interaction.guild.fetch_channel(int(thread))

        target_channel, _ = await h.handle_memory_assignment(
            interaction,
            memory,
            str(target_channel.id),
            None,
            memory_name,
            always_on
        )

        if thread_obj:
            _, target_thread = await h.handle_memory_assignment(
                interaction,
                memory,
                str(target_channel.id),
                str(thread_obj.id),
                memory_name,
                always_on
            )

        always_on_status = "ON" if always_on.value.lower() == "on" else "OFF"
        followup_messages = [
            f"Created channel '<#{target_channel.id}>' with assigned memory: '{memory_name or memory}' "
            f"and Always_on set to: [{always_on_status}]."
        ]
        if thread_obj:
            followup_messages.append(
                f"Created thread '<#{thread_obj.id}>' in channel '<#{target_channel.id}>' with assigned memory: "
                f"'{memory_name or memory}' and Always_on set to: [{always_on_status}]."
            )
        await h.send_interaction_message(interaction, "\n".join(followup_messages))

    @startnew_command.autocomplete('channel')
    async def start_channel_autocomplete(interaction, current: str):
        choices = await h.channel_autocomplete(interaction, current)
        choices.append(discord.app_commands.Choice(name="CREATE A NEW CHANNEL", value="NEW CHANNEL"))
        return choices[:50]

    @startnew_command.autocomplete('thread')
    async def start_thread_autocomplete(interaction, current: str):
        choices = await h.thread_autocomplete(interaction, current)
        choices.append(discord.app_commands.Choice(name="CREATE A NEW THREAD", value="NEW THREAD"))
        return choices[:50]

    @startnew_command.autocomplete('memory')
    async def start_memory_autocomplete(interaction, current: str):
        return await h.memory_autocomplete(interaction, current)

    @channel_group.command(name="set_always_on", description="Toggle whether AIDM listens without needing a mention.")
    @app_commands.describe(
        channel="Channel to update.",
        thread="Optional thread to update instead of the whole channel.",
        always_on="Choose whether AIDM should listen to every message there."
    )
    @app_commands.choices(always_on=[
        app_commands.Choice(name="On", value="on"),
        app_commands.Choice(name="Off", value="off")
    ])
    async def set_always_on_command(
        interaction: discord.Interaction,
        channel: str,
        thread: str = None,
        always_on: app_commands.Choice[str] = None
    ):
        await h.send_command_ack(interaction, "Updating always-on setting...")

        always_on_value = always_on and always_on.value == "on"
        target_channel = interaction.guild.get_channel(int(channel)) if channel.isdigit() else None
        target_thread = await interaction.guild.fetch_channel(int(thread)) if thread else None

        if target_thread:
            await h.set_always_on(target_thread, always_on_value)
            await h.send_interaction_message(
                interaction,
                f"Assistant 'always on' set to {'on' if always_on_value else 'off'} for thread {target_thread.mention}."
            )
        elif target_channel:
            await h.set_always_on(target_channel, always_on_value)
            await h.send_interaction_message(
                interaction,
                f"Assistant 'always on' set to {'on' if always_on_value else 'off'} for channel {target_channel.mention}."
            )
        else:
            await h.send_interaction_message(interaction, "Error: Invalid channel or thread specified.")

        logging.info(f"{'Thread' if target_thread else 'Channel'} {target_thread.id if target_thread else target_channel.id} 'always on' set to: {always_on_value}")

    @set_always_on_command.autocomplete('channel')
    async def set_always_on_channel_autocomplete(interaction, current: str):
        return await h.channel_autocomplete(interaction, current)

    @set_always_on_command.autocomplete('thread')
    async def set_always_on_thread_autocomplete(interaction, current: str):
        return await h.thread_autocomplete(interaction, current)
