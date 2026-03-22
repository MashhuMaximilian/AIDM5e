from __future__ import annotations

import logging
import discord
from discord import app_commands


def register(memory_group, h) -> None:
    @memory_group.command(name="assign", description="Assign an existing or new memory to a channel or thread.")
    @app_commands.describe(
        channel="Channel to update.",
        memory="Existing memory name, or choose CREATE NEW MEMORY.",
        thread="Optional thread to override the channel memory.",
        memory_name="Required only when creating a new memory.",
        always_on="Optionally toggle the assistant on for all messages there."
    )
    @app_commands.choices(always_on=[
        app_commands.Choice(name="On", value="on"),
        app_commands.Choice(name="Off", value="off")
    ])
    async def assign_memory_command(
        interaction,
        channel: str,
        memory: str,
        thread: str = None,
        memory_name: str = None,
        always_on: app_commands.Choice[str] = None
    ):
        await h.send_command_ack(interaction, "Assigning memory...")

        target_channel, target_thread = await h.handle_memory_assignment(
            interaction, memory, channel, thread, memory_name, always_on
        )

        if target_thread:
            await h.send_interaction_message(
                interaction,
                f"Memory '{memory}' assigned successfully to thread {target_thread.mention} in channel {target_channel.mention}."
            )
        elif target_channel:
            await h.send_interaction_message(
                interaction,
                f"Memory '{memory}' assigned successfully to channel {target_channel.mention}."
            )
        else:
            await h.send_interaction_message(interaction, f"Memory '{memory}' assigned, but the specified channel or thread was not found.")

    @assign_memory_command.autocomplete('channel')
    async def assign_memory_channel_autocomplete(interaction, current: str):
        return await h.channel_autocomplete(interaction, current)

    @assign_memory_command.autocomplete('memory')
    async def assign_memory_memory_autocomplete(interaction, current: str):
        return await h.memory_autocomplete(interaction, current)

    @assign_memory_command.autocomplete('thread')
    async def assign_memory_thread_autocomplete(interaction, current: str):
        return await h.thread_autocomplete(interaction, current)

    @memory_group.command(name="delete", description="Delete a non-default memory from this campaign.")
    async def delete_memory_command(interaction, memory: str):
        await h.send_command_ack(interaction, "Deleting memory...")

        result = h.delete_memory(memory, interaction.channel.category.id)
        if "deleted successfully" in result.lower():
            await h.set_default_memory(str(interaction.channel.category.id))
            result = (
                f"{result}\n"
                "Any channels or threads that used this memory no longer have a direct assignment. "
                "They may now resolve to their channel or campaign default memory. Use `/memory assign` "
                "to set a replacement explicitly, or delete/rework the affected thread or channel if needed."
            )
        await h.send_interaction_message(interaction, result)

    @delete_memory_command.autocomplete('memory')
    async def delete_memory_autocomplete(interaction, current: str):
        return await h.memory_autocomplete(interaction, current)

    @memory_group.command(name="list", description="Show one target, or list the whole category when no target is given.")
    @app_commands.describe(
        channel="Optional channel to inspect. Leave blank to list the whole category.",
        thread="Optional thread to inspect."
    )
    async def listmemory(interaction, channel: str = None, thread: str = None):
        try:
            category_id = h.get_category_id(interaction)
            if not channel and not thread:
                snapshot = await h.asyncio.to_thread(h.build_thread_data_snapshot)
                category_data = snapshot.get(str(category_id))
                if not category_data:
                    await h.send_interaction_message(interaction, "No memory data found for this category.")
                    return

                lines = [
                    f"**Memory map for {interaction.channel.category.mention}**",
                    f"• Default memory: `{category_data.get('default_memory') or 'None'}`",
                    "",
                ]
                grouped_channels: dict[str, list[tuple[str, dict]]] = {}
                for channel_discord_id, channel_data in category_data["channels"].items():
                    memory_name = channel_data.get("memory_name") or "None"
                    grouped_channels.setdefault(memory_name, []).append((channel_discord_id, channel_data))

                for memory_name in sorted(grouped_channels, key=str.lower):
                    lines.append(f"**{memory_name}**")
                    channels = sorted(grouped_channels[memory_name], key=lambda item: item[1].get("name", "").lower())
                    for channel_discord_id, channel_data in channels:
                        channel_ref = interaction.guild.get_channel(int(channel_discord_id))
                        channel_label = channel_ref.mention if channel_ref else f"<#{channel_discord_id}>"
                        always_on_label = "✅ ON" if channel_data.get("always_on") else "❌ OFF"
                        lines.append(f"• {channel_label} ({always_on_label})")

                        threads = sorted(channel_data.get("threads", {}).items(), key=lambda item: item[1].get("name", "").lower())
                        for thread_discord_id, thread_data in threads:
                            thread_ref = interaction.guild.get_channel(int(thread_discord_id))
                            thread_label = thread_ref.mention if thread_ref else f"<#{thread_discord_id}>"
                            thread_memory_name = thread_data.get("memory_name") or memory_name
                            thread_always_on = "✅ ON" if thread_data.get("always_on") else "❌ OFF"
                            relation = "thread override" if thread_memory_name != memory_name else "thread inherits"
                            lines.append(f"  • {relation}: {thread_label} -> `{thread_memory_name}` ({thread_always_on})")
                    lines.append("")

                assigned_memory_names = {memory_name for memory_name in grouped_channels if memory_name and memory_name != "None"}
                for channel_data in category_data["channels"].values():
                    for thread_data in channel_data.get("threads", {}).values():
                        thread_memory_name = thread_data.get("memory_name")
                        if thread_memory_name:
                            assigned_memory_names.add(thread_memory_name)

                unassigned_memories = sorted(
                    memory_name
                    for memory_name in category_data.get("memory_threads", {}).keys()
                    if memory_name not in assigned_memory_names
                )
                if unassigned_memories:
                    lines.append("**Unassigned memories**")
                    for memory_name in unassigned_memories:
                        default_marker = " (default)" if memory_name == category_data.get("default_memory") else ""
                        lines.append(f"• `{memory_name}`{default_marker}")
                    lines.append("")

                response = "\n".join(lines)
                await h.send_interaction_message(interaction, response[:2000])
                for chunk_start in range(2000, len(response), 2000):
                    await interaction.followup.send(response[chunk_start:chunk_start + 2000])
                return

            channel_id = int(channel) if channel else interaction.channel.id
            thread_id = int(thread) if thread else None

            target_channel = interaction.guild.get_channel(channel_id)
            target_thread = await interaction.guild.fetch_channel(thread_id) if thread_id else None
            if not target_channel:
                await h.send_interaction_message(interaction, "Channel not found.")
                return

            response_data = await h.asyncio.to_thread(h.fetch_memory_details, int(category_id), int(channel_id), int(thread_id) if thread_id else None)
            if not response_data:
                await h.send_interaction_message(interaction, "No memory data found for that target.")
                return

            response = (
                f"**Memory details for {target_thread.mention if target_thread else target_channel.mention}**\n"
                f"• Memory ID: `{response_data['memory_id']}`\n"
                f"• Memory Name: `{response_data['memory_name']}`\n"
                f"• Always On: `{'✅ ON' if response_data['always_on'] else '❌ OFF'}`"
            )

            if not thread_id:
                snapshot = await h.asyncio.to_thread(h.build_thread_data_snapshot)
                category_data = snapshot.get(str(category_id), {})
                channel_data = category_data.get("channels", {}).get(str(channel_id), {})
                threads = sorted(channel_data.get("threads", {}).items(), key=lambda item: item[1].get("name", "").lower())
                if threads:
                    thread_lines = ["", "**Threads in this channel**"]
                    for thread_discord_id, thread_data in threads:
                        thread_ref = interaction.guild.get_channel(int(thread_discord_id))
                        thread_label = thread_ref.mention if thread_ref else f"<#{thread_discord_id}>"
                        thread_memory_name = thread_data.get("memory_name") or response_data["memory_name"] or "None"
                        relation = "override" if thread_memory_name != response_data["memory_name"] else "inherits"
                        thread_lines.append(f"• {thread_label} -> `{thread_memory_name}` ({relation})")
                    response += "\n" + "\n".join(thread_lines)

            await h.send_interaction_message(interaction, response[:2000])
            for chunk_start in range(2000, len(response), 2000):
                await interaction.followup.send(response[chunk_start:chunk_start + 2000])

        except ValueError:
            await h.send_interaction_message(interaction, "Error: Invalid channel or thread ID format.")
        except discord.NotFound:
            await h.send_interaction_message(interaction, "Error: Channel or thread not found.")
        except Exception as e:
            logging.error(f"Error in listmemory command: {str(e)}")
            await h.send_interaction_message(interaction, f"An error occurred: {str(e)}")

    @listmemory.autocomplete('channel')
    async def listmemory_channel_autocomplete(interaction, current: str):
        return await h.channel_autocomplete(interaction, current)

    @listmemory.autocomplete('thread')
    async def listmemory_thread_autocomplete(interaction, current: str):
        return await h.thread_autocomplete(interaction, current)

    @memory_group.command(name="reset", description="Clear a target memory and delete AIDM replies from there.")
    @app_commands.describe(
        channel="Target channel. Defaults to the current channel.",
        thread="Optional target thread.",
        starting_with_message_id="Delete AIDM replies starting with this message ID (inclusive)."
    )
    async def reset_memory_command(interaction, channel: str = None, thread: str = None, starting_with_message_id: str = None):
        await h.send_command_ack(interaction, "Resetting memory...")

        try:
            channel_id = int(channel) if channel else interaction.channel.id
            thread_id = int(thread) if thread else None
            category_id = h.get_category_id(interaction)

            target = interaction.guild.get_channel(channel_id)
            if thread_id:
                target = await interaction.guild.fetch_channel(thread_id)

            assigned_memory = await h.get_assigned_memory(channel_id, category_id, thread_id=thread_id)
            if not assigned_memory:
                await interaction.followup.send("No memory assigned to this channel/thread.")
                return

            if starting_with_message_id:
                try:
                    await target.fetch_message(int(starting_with_message_id))
                except discord.NotFound:
                    logging.warning(f"Message ID {starting_with_message_id} not found in this channel.")
                    await interaction.followup.send("Invalid message ID — message not found.")
                    return

            await h.reset_memory_history(assigned_memory)

            deleted_discord_msgs = 0
            async for message in target.history(limit=500):
                if message.author.id == interaction.client.user.id:
                    if not starting_with_message_id or int(message.id) >= int(starting_with_message_id):
                        try:
                            await message.delete()
                            deleted_discord_msgs += 1
                            await h.asyncio.sleep(0.35)
                        except (discord.Forbidden, discord.HTTPException) as e:
                            logging.warning(f"Could not delete message {message.id}: {e}")

            await interaction.followup.send(
                f"🧹 **Reset complete!**\n"
                "• Stored memory rows deleted: `0` (chat transcript storage is disabled)\n"
                f"• Discord messages deleted: `{deleted_discord_msgs}`"
            )

        except Exception as e:
            logging.error(f"Error during memory reset: {e}")
            try:
                await interaction.followup.send(f"❌ Unexpected error: {e}")
            except discord.NotFound:
                logging.error("Couldn't send followup message – maybe the interaction expired.")

    @reset_memory_command.autocomplete('channel')
    async def reset_memory_channel_autocomplete(interaction, current: str):
        return await h.channel_autocomplete(interaction, current)

    @reset_memory_command.autocomplete('thread')
    async def reset_memory_thread_autocomplete(interaction, current: str):
        return await h.thread_autocomplete(interaction, current)
