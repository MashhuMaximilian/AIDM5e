# bot_commands.py

import asyncio
import logging

import discord
from discord import app_commands
from psycopg import errors as pg_errors

from config import DM_ROLE_NAME
from data_store.db_repository import append_memory_message, build_thread_data_snapshot, fetch_memory_details
from data_store.memory_management import *
from prompts.summary_prompts import build_feedback_prompt
from voice.context_support import clear_context_text, write_context_text

from .helper_functions import *
from .shared_functions import *
from .shared_functions import apply_always_on, send_response_in_chunks

    # Set up logging (you can configure this as needed)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _describe_context_source(source_target: discord.abc.GuildChannel | discord.Thread | None) -> str:
    if source_target is None:
        return "manual note"
    if isinstance(source_target, discord.Thread):
        return f"{source_target.mention} in {source_target.parent.mention}" if source_target.parent else source_target.mention
    if hasattr(source_target, "mention"):
        return source_target.mention
    return getattr(source_target, "name", "manual note")


async def _mirror_context_update(
    interaction: discord.Interaction,
    *,
    scope_value: str,
    action_value: str,
    stored_text: str | None,
    source_target: discord.abc.GuildChannel | discord.Thread | None,
) -> None:
    category = interaction.channel.category
    if not category:
        return

    context_channel = discord.utils.get(category.text_channels, name="context")
    dm_planning_channel = discord.utils.get(category.text_channels, name="dm-planning")
    source_label = _describe_context_source(source_target)
    actor = getattr(interaction.user, "mention", interaction.user.display_name)

    if scope_value == "dm":
        if context_channel:
            await context_channel.send(
                f"**DM private context updated**\n"
                f"• Action: `{action_value}`\n"
                f"• By: {actor}\n"
                f"• Source: {source_label}\n"
                f"• Full content was not mirrored here."
            )
        if dm_planning_channel and stored_text:
            await send_response_in_chunks(
                dm_planning_channel,
                f"**DM private context update**\n"
                f"• Action: `{action_value}`\n"
                f"• By: {actor}\n"
                f"• Source: {source_label}\n\n"
                f"{stored_text}",
            )
        return

    if context_channel and stored_text:
        await send_response_in_chunks(
            context_channel,
            f"**{scope_value.title()} context update**\n"
            f"• Action: `{action_value}`\n"
            f"• By: {actor}\n"
            f"• Source: {source_label}\n\n"
            f"{stored_text}",
        )

def setup_commands(tree, get_assistant_response):
    ask_group = app_commands.Group(name="ask", description="Rules and lore commands.")
    channel_group = app_commands.Group(name="channel", description="Channel and thread commands.")
    memory_group = app_commands.Group(name="memory", description="Memory management commands.")
    context_group = app_commands.Group(name="context", description="Context helpers for summaries and transcripts.")


    @ask_group.command(name="campaign", description="Campaign info lookup. Defaults to #telldm if no target is set.")
    @app_commands.describe(
        query="What you want to know.",
        channel="Optional target channel. Defaults to #telldm in this category.",
        thread="Optional target thread. Overrides the channel target when set."
    )
    @app_commands.choices(
        query_type=[
            app_commands.Choice(name="Check Status", value="checkstatus"),
            app_commands.Choice(name="Homebrew", value="homebrew"),
            app_commands.Choice(name="NPC", value="npc"),
            app_commands.Choice(name="Inventory", value="inventory"),
            app_commands.Choice(name="Roll Check", value="rollcheck")
        ]
    )
   
    async def tellme(interaction: discord.Interaction, query_type: app_commands.Choice[str], query: str, channel: str = None, thread: str = None):
        await process_query_command(interaction, query_type, query, backup_channel_name="telldm", channel=channel, thread=thread)

    # Autocomplete for channels
    @tellme.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        # Call the existing channel autocomplete function
        choices = await channel_autocomplete(interaction, current)
        return choices[:25]  # Limit to 25 suggestions
    ## Autocomplete for threads in tellme
    @tellme.autocomplete('thread')
    async def tellme_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)


    # Main logic for the askdm command (same for tellme command)
    @ask_group.command(name="dm", description="Rules and lore lookup. Defaults to #telldm if no target is set.")
    @app_commands.describe(
        query="Your rules, lore, or adjudication question.",
        channel="Optional target channel. Defaults to #telldm in this category.",
        thread="Optional target thread. Overrides the channel target when set."
    )
    @app_commands.choices(
        query_type=[
            app_commands.Choice(name="Spell", value="spell"),
            app_commands.Choice(name="Game Mechanics", value="game_mechanics"),
            app_commands.Choice(name="Monsters & Creatures", value="monsters_creatures"),
            app_commands.Choice(name="World Lore & History", value="world_lore_history"),
            app_commands.Choice(name="Item", value="item"),
            app_commands.Choice(name="Conditions & Effects", value="conditions_effects"),
            app_commands.Choice(name="Rules Clarifications", value="rules_clarifications"),
            app_commands.Choice(name="Race or Class", value="race_class")
        ]
    )
    async def askdm(interaction: discord.Interaction, query_type: app_commands.Choice[str], query: str, channel: str = None, thread: str = None):
        await process_query_command(interaction, query_type, query, backup_channel_name="telldm", channel=channel, thread=thread)

    # Autocomplete for channels
    @askdm.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        choices = await channel_autocomplete(interaction, current)
        return choices[:25]  # Limit to 25 suggestions
    # Autocomplete for threads
    @askdm.autocomplete('thread')
    async def askdm_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)



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
        await interaction.response.defer()  # Defer the response while processing

        # Fetch the channel and thread if specified
        channel_id = int(channel) if channel else interaction.channel.id
        thread_id = int(thread) if thread else None
        category_id = get_category_id(interaction)

        
        # Fetch the assigned memory for the provided channel and thread
        assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id=thread_id)

        # Fetch conversation history based on provided parameters, including readable attachment content
        conversation_history, options_or_error = await fetch_reference_material(interaction.channel, start, end, message_ids, last_n)

        # Check if the response is an error message
        if isinstance(options_or_error, str):
            await interaction.followup.send(options_or_error)  # Send error message
            return

        options = options_or_error  # Assign the options for summarization

        # Summarize the conversation, passing assigned_memory to the summarization function
        response = await summarize_conversation(interaction, conversation_history, options, query, channel_id, thread_id, assigned_memory)

        # Send the summarized response in chunks
        if response:  # Ensure response is not empty
            await send_response(interaction, response, channel_id=channel_id, thread_id=thread_id)
        else:
            await interaction.followup.send("No content to summarize.")  # Optional: handle empty response

            # Autocomplete functions for channel and thread parameters
    @summarize.autocomplete('channel')  # Note that the parameter name is 'channel', not 'channel_id'
    async def target_channel_autocomplete(interaction: discord.Interaction, current: str):
                return await channel_autocomplete(interaction, current)

    @summarize.autocomplete('thread')  # Note that the parameter name is 'thread', not 'thread_id'
    async def send_thread_autocomplete(interaction: discord.Interaction, current: str):
                return await thread_autocomplete(interaction, current)

    @tree.command(name="reference", description="Read messages, files, or a URL and answer from them.")
    @app_commands.describe(
        query="What you want AIDM to extract, explain, or answer from the references.",
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to read.",
        last_n="Read the last 'n' messages (optional).",
        url="Optional public URL to read as additional context.",
        channel="Optional target channel and memory for the answer. Defaults to this channel.",
        thread="Optional target thread and memory for the answer."
    )
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
    ):
        await interaction.response.defer()

        channel_id = int(channel) if channel else interaction.channel.id
        thread_id = int(thread) if thread else None
        category_id = get_category_id(interaction)
        assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id=thread_id)
        if not assigned_memory:
            await interaction.followup.send("No memory found for the specified parameters.")
            return

        reference_chunks: list[str] = []
        if any(value is not None for value in (start, end, message_ids, last_n)):
            reference_material, options_or_error = await fetch_reference_material(
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
                response = await answer_from_public_url(
                    query=query,
                    url=url,
                    channel_id=channel_id,
                    assigned_memory=assigned_memory,
                    thread_id=thread_id,
                )
            except Exception as exc:
                await interaction.followup.send(f"Could not read the URL: {exc}")
                return
        else:
            if url:
                try:
                    reference_chunks.append(f"[Public URL: {url}]\n{await extract_public_url_text(url)}")
                except Exception as exc:
                    reference_chunks.append(
                        f"[Public URL could not be fetched directly: {url}. Reason: {exc}. "
                        "Use the other provided material and note that the URL may require a different retrieval path.]"
                    )

            response = await answer_from_references(
                query=query,
                reference_material=reference_chunks,
                channel_id=channel_id,
                assigned_memory=assigned_memory,
                thread_id=thread_id,
                url=url,
            )
        await send_response(
            interaction,
            response,
            channel_id=channel_id,
            thread_id=thread_id,
            backup_channel_name="telldm",
        )

    @reference.autocomplete('channel')
    async def reference_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @reference.autocomplete('thread')
    async def reference_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)


    @tree.command(name="feedback", description="Send feedback to #feedback and generate a recap there.")
    async def feedback(interaction: discord.Interaction, suggestions: str):
        await interaction.response.defer()  # Defer the response while processing the feedback

        # Step 1: Check if 'feedback' channel exists in the same category
        feedback_channel = discord.utils.get(interaction.channel.category.channels, name="feedback")

        # If the channel doesn't exist, create it
        if feedback_channel is None:
            guild = interaction.guild
            feedback_channel = await guild.create_text_channel(name="feedback", category=interaction.channel.category)
            await interaction.followup.send(f"The #feedback channel was not found, so I created it in the same category.")

        # Step 2: Send the feedback message to #feedback
        feedback_message = await feedback_channel.send(f"Feedback from {interaction.user.name}: {suggestions}")
        await interaction.followup.send(f"Your feedback has been sent to {feedback_channel.mention}.")

        # Step 3: Fetch all messages from the #feedback channel
        messages = []
        async for message in feedback_channel.history(limit=300):
            messages.append(f"{message.author.name}: {message.content}")

        if not messages:
            await interaction.followup.send(f"No messages found in {feedback_channel.mention}.")
            return

        # Step 4: Get the last message for focus in summarization
        last_message = messages[0]  # The most recent message is at the start of the list

        # Create a conversation history from all the messages
        conversation_history = "\n".join(reversed(messages))  # Reversed so that it reads from oldest to newest

        # Step 5: Get the assigned memory for the feedback channel
        category_id = get_category_id(interaction)
        assigned_memory = await get_assigned_memory(feedback_channel.id, category_id, thread_id=None)

        # Step 6: Send the conversation to the assistant for summarization, focusing on the last message
        prompt = build_feedback_prompt(conversation_history, last_message)

        # Update the assistant response call with the correct memory
        response = await get_assistant_response(prompt, feedback_channel.id, thread_id=None, assigned_memory=assigned_memory)


        await send_response(interaction, response, channel_id=None, thread_id=None, backup_channel_name="feedback")

        # Step 7: Confirm that the feedback was processed
        await interaction.followup.send(f"Feedback has been processed and a recap has been posted in {feedback_channel.mention}.")

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
        await send_command_ack(interaction, "Sending messages...")

        # Fetch the channel and thread if specified
        channel_id = int(channel) if channel else interaction.channel.id
        thread_id = int(thread) if thread else None
        category_id = get_category_id(interaction)

        # Fetch conversation history based on the provided parameters
        conversation_history, options_or_error = await fetch_conversation_history(interaction.channel, start, end, message_ids, last_n)

        # Handle errors if conversation history is empty or invalid
        if isinstance(options_or_error, str):
            await interaction.followup.send(options_or_error)  # Send error message
            return

        # Assign the fetched options (for message selection)
        options = options_or_error

        # Fetch the target channel object
        target_channel_obj = interaction.guild.get_channel(channel_id)

        if not target_channel_obj:
            await interaction.followup.send("Target channel not found.")
            return

        # Check if the target channel is in the same category
        if target_channel_obj.category_id != interaction.channel.category_id:
            await interaction.followup.send(f"Cannot send messages to {target_channel_obj.name}. Must be in the same category.")
            return

        # If a thread is specified, fetch the thread
        target = target_channel_obj
        if thread:
            target = await interaction.guild.fetch_channel(thread_id)  # Fetch the thread object

        # Send all messages in the conversation history to the target (either thread or channel)
        for message in conversation_history:
            await send_response_in_chunks(target, message)

        assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id=thread_id)
        if assigned_memory:
            for message in conversation_history:
                await asyncio.to_thread(
                    append_memory_message,
                    assigned_memory,
                    "user",
                    message,
                    channel_id,
                    thread_id,
                    interaction.user.id,
                    interaction.user.display_name,
                )

            imported_content = "\n\n".join(conversation_history)
            acknowledgment_prompt = (
                "A user transferred the following Discord content into this channel or thread. "
                "Acknowledge briefly what was added and mention the most important fact or takeaway "
                "AIDM should now keep in mind for this memory. Keep the answer to at most 3 short bullets.\n\n"
                f"Transferred content:\n{imported_content}"
            )
            acknowledgment = await get_assistant_response(
                acknowledgment_prompt,
                channel_id,
                category_id,
                thread_id,
                assigned_memory=assigned_memory,
                send_message=False,
            )
            if acknowledgment:
                await send_response_in_chunks(target, acknowledgment)

        # Notify the user about the success after all messages are sent
        await interaction.followup.send(f"Messages sent successfully to {'thread' if thread else 'channel'} <#{target.id}>.")

    # Autocomplete for the target_channel field
    @send.autocomplete('channel')
    async def target_channel_autocomplete(interaction: discord.Interaction, current: str):
        # Use the existing channel autocomplete function
        choices = await channel_autocomplete(interaction, current)
        return choices[:25]  # Limit to 25 suggestions
    # Autocomplete for the thread field
    @send.autocomplete('thread')
    async def send_thread_autocomplete(interaction: discord.Interaction, current: str):
        # Use the thread autocomplete function
        return await thread_autocomplete(interaction, current)

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
        # Validate parameters
        if channel == "NEW CHANNEL" and not channel_name:
            await send_interaction_message(interaction, "Error: You must provide a name for the new channel.")
            return
        if thread == "NEW THREAD" and not thread_name:
            await send_interaction_message(interaction, "Error: You must provide a name for the new thread.")
            return
        if memory == "CREATE NEW MEMORY" and not memory_name:
            await send_interaction_message(interaction, "Error: You must provide a name for the new memory.")
            return

        await send_command_ack(interaction, "Creating channel or thread...")

        # Retrieve guild and category
        guild = interaction.guild
        category = interaction.channel.category

        # Create or get the target channel
        target_channel = await handle_channel_creation(channel, channel_name, guild, category, interaction)
        if target_channel is None:
            return

        logging.info(f"Target channel ID: {target_channel.id}, Name: {target_channel.name}")

        # Handle thread creation if "NEW THREAD" is selected
        thread_obj = None
        if thread == "NEW THREAD":
            thread_obj, error = await handle_thread_creation(interaction, target_channel, thread_name, category.id, memory_name)
            if error:
                await send_interaction_message(interaction, error)
                return
        elif thread:  # Fetch existing thread if provided
            thread_obj = await interaction.guild.fetch_channel(int(thread))

        # Assign memory to the channel
        target_channel, _ = await handle_memory_assignment(
            interaction,
            memory,
            str(target_channel.id),
            None,  # No thread involved here
            memory_name,
            always_on
        )

        # Assign memory to the thread if applicable
        if thread_obj:
            _, target_thread = await handle_memory_assignment(
                interaction,
                memory,
                str(target_channel.id),
                str(thread_obj.id),
                memory_name,
                always_on
            )

        # Prepare follow-up messages based on the scenario
        always_on_status = "ON" if always_on.value.lower() == "on" else "OFF"
        followup_messages = []

        # Channel follow-up
        followup_messages.append(
            f"Created channel '<#{target_channel.id}>' with assigned memory: '{memory_name or memory}' "
            f"and Always_on set to: [{always_on_status}]."
        )

        # Thread follow-up
        if thread_obj:
            followup_messages.append(
                f"Created thread '<#{thread_obj.id}>' in channel '<#{target_channel.id}>' with assigned memory: "
                f"'{memory_name or memory}' and Always_on set to: [{always_on_status}]."
            )

        # Send the combined follow-up messages
        await send_interaction_message(interaction, "\n".join(followup_messages))

    @startnew_command.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        # Call the existing channel autocomplete function
        choices = await channel_autocomplete(interaction, current)

        # Add the option to create a new channel
        choices.append(discord.app_commands.Choice(name="CREATE A NEW CHANNEL", value="NEW CHANNEL"))

        return choices[:50]  # Limit to 50 suggestions

    @startnew_command.autocomplete('thread')
    async def thread_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        # Call the existing thread autocomplete function
        choices = await thread_autocomplete(interaction, current)

        # Add the option to create a new thread
        choices.append(discord.app_commands.Choice(name="CREATE A NEW THREAD", value="NEW THREAD"))

        return choices[:50]  # Limit to 50 suggestions

    @startnew_command.autocomplete('memory')
    async def memory_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await memory_autocomplete(interaction, current)


            

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
        interaction: discord.Interaction,
        channel: str,
        memory: str,
        thread: str = None,
        memory_name: str = None,
        always_on: app_commands.Choice[str] = None  # Optional
    ):
        await send_command_ack(interaction, "Assigning memory...")

        # Handle memory assignment
        target_channel, target_thread = await handle_memory_assignment(
            interaction, memory, channel, thread, memory_name, always_on
        )

        # Handle response based on the results
        if target_thread:
            await send_interaction_message(
                interaction,
                f"Memory '{memory}' assigned successfully to thread {target_thread.mention} in channel {target_channel.mention}."
            )
        elif target_channel:
            await send_interaction_message(
                interaction,
                f"Memory '{memory}' assigned successfully to channel {target_channel.mention}."
                
            )
        else:
            await send_interaction_message(interaction, f"Memory '{memory}' assigned, but the specified channel or thread was not found.")

    @assign_memory_command.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @assign_memory_command.autocomplete('memory')
    async def memory_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await memory_autocomplete(interaction, current)

    @assign_memory_command.autocomplete('thread')
    async def thread_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)
    


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
        always_on: app_commands.Choice[str] = None  # Optional; defaults to "off" if not specified
    ):
        await send_command_ack(interaction, "Updating always-on setting...")

        # Explicitly parse always_on as True (on) or False (off)
        always_on_value = always_on and always_on.value == "on"

        # Fetch channel and thread objects
        target_channel = interaction.guild.get_channel(int(channel)) if channel.isdigit() else None
        target_thread = await interaction.guild.fetch_channel(int(thread)) if thread else None

        if target_thread:
            await set_always_on(target_thread, always_on_value)
            await send_interaction_message(
                interaction,
                f"Assistant 'always on' set to {'on' if always_on_value else 'off'} for thread {target_thread.mention}."
            )
        elif target_channel:
            await set_always_on(target_channel, always_on_value)
            await send_interaction_message(
                interaction,
                f"Assistant 'always on' set to {'on' if always_on_value else 'off'} for channel {target_channel.mention}."
            )
        else:
            await send_interaction_message(interaction, "Error: Invalid channel or thread specified.")

        # Log the action
        logging.info(f"{'Thread' if target_thread else 'Channel'} {target_thread.id if target_thread else target_channel.id} 'always on' set to: {always_on_value}")

    @set_always_on_command.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @set_always_on_command.autocomplete('thread')
    async def thread_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)
    

    @memory_group.command(name="delete", description="Delete a non-default memory from this campaign.")
    async def delete_memory_command(interaction: discord.Interaction, memory: str):
        await send_command_ack(interaction, "Deleting memory...")

        result = delete_memory(memory, interaction.channel.category.id)
        if "deleted successfully" in result.lower():
            await set_default_memory(str(interaction.channel.category.id))
            result = (
                f"{result}\n"
                "Any channels or threads that used this memory no longer have a direct assignment. "
                "They may now resolve to their channel or campaign default memory. Use `/memory assign` "
                "to set a replacement explicitly, or delete/rework the affected thread or channel if needed."
            )
        await send_interaction_message(interaction, result)

    # Add autocomplete functionality for the memory argument
    @delete_memory_command.autocomplete('memory')
    async def memory_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await memory_autocomplete(interaction, current)


    @tree.command(name="invite", description="Initialize the default AIDM channel layout for this category.")
    async def invite_command(interaction: discord.Interaction):
        """Initialize threads and channels for the category where the command is invoked."""
        category = interaction.channel.category  # Get the category of the current channel
        
        if not category:
            await interaction.response.send_message("This command must be used in a category channel.")
            return
        
        # Acknowledge the interaction immediately
        await send_command_ack(interaction, "Initializing campaign...")

        try:
            invite_result = await initialize_threads(category)
        except ValueError as exc:
            await interaction.followup.send(str(exc))
            return

        created = ", ".join(invite_result["created"]) if invite_result["created"] else "none"
        reused = ", ".join(invite_result["reused"]) if invite_result["reused"] else "none"
        created_voice = ", ".join(invite_result["created_voice"]) if invite_result["created_voice"] else "none"
        reused_voice = ", ".join(invite_result["reused_voice"]) if invite_result["reused_voice"] else "none"
        await interaction.followup.send(
            f"Campaign initialized for **{category.name}**.\n"
            f"Created channels: {created}\n"
            f"Reused channels: {reused}\n"
            f"Created voice channels: {created_voice}\n"
            f"Reused voice channels: {reused_voice}"
        )

    @context_group.command(name="summary", description="Store public, session, or DM context for future transcript/summary runs.")
    @app_commands.describe(
        scope="Which context bucket to update.",
        action="Whether to replace, append, or clear that bucket.",
        note="Optional manual text to store as context.",
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to include.",
        last_n="Use the last 'n' messages from the source target.",
        channel="Optional source channel. Defaults to this channel.",
        thread="Optional source thread. Overrides the source channel when set.",
    )
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="Public Evergreen", value="public"),
            app_commands.Choice(name="Session Only", value="session"),
            app_commands.Choice(name="DM Private", value="dm"),
        ],
        action=[
            app_commands.Choice(name="Replace", value="replace"),
            app_commands.Choice(name="Append", value="append"),
            app_commands.Choice(name="Clear", value="clear"),
        ],
    )
    async def context_summary(
        interaction: discord.Interaction,
        scope: app_commands.Choice[str],
        action: app_commands.Choice[str],
        note: str = None,
        start: str = None,
        end: str = None,
        message_ids: str = None,
        last_n: int = None,
        channel: str = None,
        thread: str = None,
    ):
        await send_command_ack(interaction, "Updating summary context...")

        try:
            if scope.value == "dm":
                member_roles = getattr(interaction.user, "roles", [])
                is_dm = any(getattr(role, "name", None) == DM_ROLE_NAME for role in member_roles)
                if not is_dm:
                    await send_interaction_message(
                        interaction,
                        f"Only members with the `{DM_ROLE_NAME}` role can change DM-private summary context.",
                        ephemeral=True,
                    )
                    return

            if action.value == "clear":
                path = clear_context_text(scope.value)
                await _mirror_context_update(
                    interaction,
                    scope_value=scope.value,
                    action_value=action.value,
                    stored_text=None,
                    source_target=interaction.channel,
                )
                await send_interaction_message(
                    interaction,
                    f"Cleared `{scope.value}` summary context at `{path}`.",
                    ephemeral=True,
                )
                return

            source_target = interaction.channel
            if channel:
                source_target = interaction.guild.get_channel(int(channel))
            if thread:
                source_target = await interaction.guild.fetch_channel(int(thread))

            if source_target is None:
                await send_interaction_message(interaction, "Source channel or thread not found.", ephemeral=True)
                return

            parts: list[str] = []
            if any(value is not None for value in (start, end, message_ids, last_n)):
                material, options_or_error = await fetch_reference_material(
                    source_target,
                    start,
                    end,
                    message_ids,
                    last_n,
                )
                if isinstance(options_or_error, str):
                    await send_interaction_message(interaction, options_or_error, ephemeral=True)
                    return
                parts.append("\n\n".join(material))

            if note:
                parts.append(note.strip())

            if not parts:
                await send_interaction_message(
                    interaction,
                    "Provide message selectors and/or a manual note, or use action `Clear`.",
                    ephemeral=True,
                )
                return

            stored_text = "\n\n".join(part for part in parts if part).strip()
            path = write_context_text(scope.value, stored_text, action.value)
            extra = ""
            if scope.value == "dm":
                extra = (
                    "\nDM context is stored separately. It is only included when DM context is explicitly enabled for a run."
                )
            await _mirror_context_update(
                interaction,
                scope_value=scope.value,
                action_value=action.value,
                stored_text=stored_text,
                source_target=source_target,
            )
            await send_interaction_message(
                interaction,
                f"Saved `{scope.value}` summary context to `{path}` using `{action.value}`.{extra}",
                ephemeral=True,
            )
        except Exception as exc:
            logger.exception("Error updating summary context: %s", exc)
            await send_interaction_message(interaction, f"Could not update context: {exc}", ephemeral=True)

    @context_summary.autocomplete('channel')
    async def context_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @context_summary.autocomplete('thread')
    async def context_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)


    @memory_group.command(name="list", description="Show one target, or list the whole category when no target is given.")
    @app_commands.describe(
        channel="Optional channel to inspect. Leave blank to list the whole category.",
        thread="Optional thread to inspect."
    )
    async def listmemory(interaction: discord.Interaction, channel: str = None, thread: str = None):
        try:
            category_id = get_category_id(interaction)
            if not channel and not thread:
                snapshot = await asyncio.to_thread(build_thread_data_snapshot)
                category_data = snapshot.get(str(category_id))
                if not category_data:
                    await send_interaction_message(interaction, "No memory data found for this category.")
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
                    channels = sorted(
                        grouped_channels[memory_name],
                        key=lambda item: item[1].get("name", "").lower(),
                    )
                    for channel_discord_id, channel_data in channels:
                        channel_ref = interaction.guild.get_channel(int(channel_discord_id))
                        channel_label = channel_ref.mention if channel_ref else f"<#{channel_discord_id}>"
                        always_on_label = "✅ ON" if channel_data.get("always_on") else "❌ OFF"
                        lines.append(f"• {channel_label} ({always_on_label})")

                        threads = sorted(
                            channel_data.get("threads", {}).items(),
                            key=lambda item: item[1].get("name", "").lower(),
                        )
                        for thread_discord_id, thread_data in threads:
                            thread_ref = interaction.guild.get_channel(int(thread_discord_id))
                            thread_label = thread_ref.mention if thread_ref else f"<#{thread_discord_id}>"
                            thread_memory_name = thread_data.get("memory_name") or memory_name
                            thread_always_on = "✅ ON" if thread_data.get("always_on") else "❌ OFF"
                            relation = "thread override" if thread_memory_name != memory_name else "thread inherits"
                            lines.append(
                                f"  • {relation}: {thread_label} -> `{thread_memory_name}` ({thread_always_on})"
                            )
                    lines.append("")

                assigned_memory_names = {
                    memory_name
                    for memory_name in grouped_channels
                    if memory_name and memory_name != "None"
                }
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
                await send_interaction_message(interaction, response[:2000])
                for chunk_start in range(2000, len(response), 2000):
                    await interaction.followup.send(response[chunk_start:chunk_start + 2000])
                return

            channel_id = int(channel) if channel else interaction.channel.id
            thread_id = int(thread) if thread else None

            target_channel = interaction.guild.get_channel(channel_id)
            target_thread = await interaction.guild.fetch_channel(thread_id) if thread_id else None
            
            if not target_channel:
                await send_interaction_message(interaction, "Channel not found.")
                return

            response_data = await asyncio.to_thread(fetch_memory_details, int(category_id), int(channel_id), int(thread_id) if thread_id else None)
            if not response_data:
                await send_interaction_message(interaction, "No memory data found for that target.")
                return
            
            # Format the response
            response = (
                f"**Memory details for {target_thread.mention if target_thread else target_channel.mention}**\n"
                f"• Memory ID: `{response_data['memory_id']}`\n"
                f"• Memory Name: `{response_data['memory_name']}`\n"
                f"• Always On: `{'✅ ON' if response_data['always_on'] else '❌ OFF'}`"
            )

            if not thread_id:
                snapshot = await asyncio.to_thread(build_thread_data_snapshot)
                category_data = snapshot.get(str(category_id), {})
                channel_data = category_data.get("channels", {}).get(str(channel_id), {})
                threads = sorted(
                    channel_data.get("threads", {}).items(),
                    key=lambda item: item[1].get("name", "").lower(),
                )
                if threads:
                    thread_lines = ["", "**Threads in this channel**"]
                    for thread_discord_id, thread_data in threads:
                        thread_ref = interaction.guild.get_channel(int(thread_discord_id))
                        thread_label = thread_ref.mention if thread_ref else f"<#{thread_discord_id}>"
                        thread_memory_name = thread_data.get("memory_name") or response_data["memory_name"] or "None"
                        relation = "override" if thread_memory_name != response_data["memory_name"] else "inherits"
                        thread_lines.append(f"• {thread_label} -> `{thread_memory_name}` ({relation})")
                    response += "\n" + "\n".join(thread_lines)
            
            await send_interaction_message(interaction, response[:2000])
            for chunk_start in range(2000, len(response), 2000):
                await interaction.followup.send(response[chunk_start:chunk_start + 2000])
            
        except ValueError:
            await send_interaction_message(interaction, "Error: Invalid channel or thread ID format.")
        except discord.NotFound:
            await send_interaction_message(interaction, "Error: Channel or thread not found.")
        except Exception as e:
            logging.error(f"Error in listmemory command: {str(e)}")
            await send_interaction_message(interaction, f"An error occurred: {str(e)}")

    @listmemory.autocomplete('channel')
    async def listmemory_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @listmemory.autocomplete('thread')
    async def listmemory_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)

    
    @memory_group.command(name="reset", description="Clear a target memory and delete AIDM replies from there.")
    @app_commands.describe(
        channel="Target channel. Defaults to the current channel.",
        thread="Optional target thread.",
        starting_with_message_id="Delete AIDM replies starting with this message ID (inclusive)."
    )
    async def reset_memory_command(interaction: discord.Interaction, channel: str = None, thread: str = None, starting_with_message_id: str = None):
        await send_command_ack(interaction, "Resetting memory...")

        try:
            channel_id = int(channel) if channel else interaction.channel.id
            thread_id = int(thread) if thread else None
            category_id = get_category_id(interaction)

            target = interaction.guild.get_channel(channel_id)
            if thread_id:
                target = await interaction.guild.fetch_channel(thread_id)

            assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id=thread_id)
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

            delete_count = await reset_memory_history(assigned_memory)

            # === DELETE DISCORD MESSAGES ===
            deleted_discord_msgs = 0

            async for message in target.history(limit=500):
                if message.author.id == interaction.client.user.id:
                    if not starting_with_message_id or int(message.id) >= int(starting_with_message_id):
                        try:
                            await message.delete()
                            deleted_discord_msgs += 1
                            await asyncio.sleep(0.35)  # avoid rate limiting Discord (429s)
                        except (discord.Forbidden, discord.HTTPException) as e:
                            logging.warning(f"Could not delete message {message.id}: {e}")

            await interaction.followup.send(
                f"🧹 **Reset complete!**\n"
                f"• Memory messages deleted: `{delete_count}`\n"
                f"• Discord messages deleted: `{deleted_discord_msgs}`"
            )

        except Exception as e:
            logging.error(f"Error during memory reset: {e}")
            try:
                await interaction.followup.send(f"❌ Unexpected error: {e}")
            except discord.NotFound:
                logging.error("Couldn't send followup message – maybe the interaction expired.")

    @reset_memory_command.autocomplete('channel')
    async def reset_memory_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @reset_memory_command.autocomplete('thread')
    async def reset_memory_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)

    @tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        original = error.original if isinstance(error, app_commands.CommandInvokeError) else error
        logger.exception("Application command error: %s", original)

        if isinstance(original, pg_errors.UniqueViolation):
            message = (
                "Cannot complete that command because an item with the same unique value already exists "
                "in this campaign. If you were creating a channel or thread, choose a different name "
                "or reuse the existing one."
            )
        elif isinstance(original, ValueError):
            message = str(original)
        elif isinstance(original, discord.Forbidden):
            message = "I do not have permission to complete that command in Discord."
        else:
            command_name = interaction.command.qualified_name if interaction.command else "that command"
            message = f"Could not complete `{command_name}` because of an internal error."

        try:
            await send_interaction_message(interaction, message, ephemeral=True)
        except Exception:
            logger.exception("Failed to send app command error message.")

    tree.add_command(ask_group)
    tree.add_command(channel_group)
    tree.add_command(context_group)
    tree.add_command(memory_group)
