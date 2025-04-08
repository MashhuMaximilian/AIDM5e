# bot_commands.py

import discord
from discord import app_commands
from shared_functions import *
from helper_functions import *
import logging
import asyncio
from memory_management import *
from shared_functions import apply_always_on, send_response_in_chunks

    # Set up logging (you can configure this as needed)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_commands(tree, get_assistant_response):


    @tree.command(name="tellme", description="Info about spells, items, NPCs, character status, inventory, or roll checks.")
    @app_commands.choices(
        query_type=[
            app_commands.Choice(name="Spell", value="spell"),
            app_commands.Choice(name="CheckStatus", value="checkstatus"),
            app_commands.Choice(name="Homebrew Item", value="hbw_item"),
            app_commands.Choice(name="NPC", value="npc"),
            app_commands.Choice(name="Inventory", value="inventory"),
            app_commands.Choice(name="RollCheck", value="rollcheck")
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
    @tree.command(name="askdm", description="Inquire about rules, lore, monsters, and more.") 
    @app_commands.choices(
        query_type=[
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



    @tree.command(name="summarize", description="Summarize messages based on different options.")
    @app_commands.describe(
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to summarize.",
        query="Additional requests or context for the recap.",
        last_n="Summarize the last 'n' messages (optional)."
    )
    async def summarize(interaction: discord.Interaction, start: str = None, end: str = None, message_ids: str = None, query: str = None, last_n: int = None, channel: str = None, thread: str = None):
        await interaction.response.defer()  # Defer the response while processing

        # Fetch the channel and thread if specified
        channel_id = int(channel) if channel else interaction.channel.id
        thread_id = int(thread) if thread else None
        category_id = get_category_id(interaction)

        
        # Fetch the assigned memory for the provided channel and thread
        assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id=thread_id)

        # Fetch conversation history based on provided parameters
        conversation_history, options_or_error = await fetch_conversation_history(interaction.channel, start, end, message_ids, last_n)

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


    @tree.command(name="feedback", description="Provide feedback about the AIDM’s performance or game experience.")
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
        assigned_memory = await get_assigned_memory(interaction.channel.id, category_id, thread_id=None)

        # Step 6: Send the conversation to the assistant for summarization, focusing on the last message
        prompt = (f"Make a recap of the following feedback messages regarding the AIDM’s performance. "
                f"Here is the entire message history from the #feedback channel:\n\n{conversation_history}"
                f"Pay special attention to the **last feedback message**, which is:\n\n{last_message}\n\n"
                f"1)Summarize this last message briefly and confirm you understood the feedback. "
                f"2)Also mention that you have reviewed all feedback messages for better implementation. ")

        # Update the assistant response call with the correct memory
        response = await get_assistant_response(prompt, interaction.channel.id, thread_id=None, assigned_memory=assigned_memory)


        await send_response(interaction, response, channel_id=None, thread_id=None, backup_channel_name="feedback")

        # Step 7: Confirm that the feedback was processed
        await interaction.followup.send(f"Feedback has been processed and a recap has been posted in {feedback_channel.mention}.")

    @tree.command(name="send", description="Send specified messages to another channel or thread.")
    @app_commands.describe(
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to send (comma-separated if multiple).",
        last_n="Send the last 'n' messages (optional)."
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
        await interaction.response.defer()  # Defer the response while processing

        # Fetch the channel and thread if specified
        channel_id = int(channel) if channel else interaction.channel.id
        thread_id = int(thread) if thread else None

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

    @tree.command(name="startnew", description="Create a new channel or new thread with options.")
    @app_commands.describe(
        channel="Choose an existing channel or 'NEW CHANNEL' to create a new one.",
        channel_name="Name for the new channel (only if 'NEW CHANNEL' is selected).",
        thread_name="Name for the new thread (only if you choose 'CREATE A NEW THREAD').",
        memory="Choose an existing OpenAI thread or create a new memory.",
        memory_name="Provide a name for the new OpenAI thread (only if 'CREATE NEW MEMORY' is selected).",
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
        await interaction.response.defer()

        # Validate parameters
        if channel == "NEW CHANNEL" and not channel_name:
            await interaction.followup.send("Error: You must provide a name for the new channel.")
            return
        if thread == "NEW THREAD" and not thread_name:
            await interaction.followup.send("Error: You must provide a name for the new thread.")
            return
        if memory == "CREATE NEW MEMORY" and not memory_name:
            await interaction.followup.send("Error: You must provide a name for the new memory.")
            return

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
                await interaction.followup.send(error)
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
        always_on_status = "ON" if always_on.value.lower() == "true" else "OFF"
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
        await interaction.followup.send("\n".join(followup_messages))

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


            

    @tree.command(name="assign_memory", description="Assign a memory to a Discord thread or channel.")
    @app_commands.describe(always_on="Set the assistant always on or off.")
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
        await interaction.response.defer()

        # Handle memory assignment
        target_channel, target_thread = await handle_memory_assignment(
            interaction, memory, channel, thread, memory_name, always_on
        )

        # Handle response based on the results
        if target_thread:
            await interaction.followup.send(
                f"Memory '{memory}' assigned successfully to thread {target_thread.mention} in channel {target_channel.mention}."
            )
        elif target_channel:
            await interaction.followup.send(
                f"Memory '{memory}' assigned successfully to channel {target_channel.mention}."
                
            )
        else:
            await interaction.followup.send(f"Memory '{memory}' assigned, but the specified channel or thread was not found.")

    @assign_memory_command.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @assign_memory_command.autocomplete('memory')
    async def memory_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await memory_autocomplete(interaction, current)

    @assign_memory_command.autocomplete('thread')
    async def thread_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)
    


    @tree.command(name="set_always_on", description="Set the assistant to always be on or off for a channel or thread.")
    @app_commands.describe(always_on="Set the assistant always on or off.")
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
        await interaction.response.defer()

        # Explicitly parse always_on as True (on) or False (off)
        always_on_value = always_on and always_on.value == "on"

        # Fetch channel and thread objects
        target_channel = interaction.guild.get_channel(int(channel)) if channel.isdigit() else None
        target_thread = await interaction.guild.fetch_channel(int(thread)) if thread else None

        if target_thread:
            await set_always_on(target_thread, always_on_value)
            await interaction.followup.send(
                f"Assistant 'always on' set to {'on' if always_on_value else 'off'} for thread {target_thread.mention}."
            )
        elif target_channel:
            await set_always_on(target_channel, always_on_value)
            await interaction.followup.send(
                f"Assistant 'always on' set to {'on' if always_on_value else 'off'} for channel {target_channel.mention}."
            )
        else:
            await interaction.followup.send("Error: Invalid channel or thread specified.")

        # Log the action
        logging.info(f"{'Thread' if target_thread else 'Channel'} {target_thread.id if target_thread else target_channel.id} 'always on' set to: {always_on_value}")

    @set_always_on_command.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @set_always_on_command.autocomplete('thread')
    async def thread_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)
    

    @tree.command(name="delete_memory", description="Deletes a memory from the JSON data.")
    async def delete_memory_command(interaction: discord.Interaction, memory: str):
        await interaction.response.defer()

        # Call the reusable function to delete the memory
        result = delete_memory(memory)

        # After deleting the memory, set the default memory for the category
        if result == "Memory deleted successfully":  # Ensure memory was successfully deleted
            category_id = str(interaction.channel.category.id)  # Get the category ID
            await set_default_memory(category_id)  # Set the default memory for the category

            # Assign the new default memory to the channel or thread
            default_memory_id = category_threads[category_id]["gameplay"]
            channel_id = interaction.channel.id  # Channel ID
            thread_id = interaction.thread.id if interaction.thread else None  # Thread ID, if any

            # Now, assign the default memory to the channel or thread
            memory_assignment_result = await assign_memory(
                interaction,
                default_memory_id,
                channel_id=channel_id,
                thread_id=thread_id
            )

            # Respond with the result of memory assignment
            await interaction.followup.send(memory_assignment_result)

        else:
            # In case memory deletion failed
            await interaction.followup.send(result)

    # Add autocomplete functionality for the memory argument
    @delete_memory_command.autocomplete('memory')
    async def memory_autocomplete_wrapper(interaction: discord.Interaction, current: str):
        return await memory_autocomplete(interaction, current)


    @tree.command(name="invite", description="Initialize threads and channels for this category.")
    async def invite_command(interaction: discord.Interaction):
        """Initialize threads and channels for the category where the command is invoked."""
        category = interaction.channel.category  # Get the category of the current channel
        
        if not category:
            await interaction.response.send_message("This command must be used in a category channel.")
            return
        
        # Acknowledge the interaction immediately
        await interaction.response.defer()  # Defer response to avoid timeout

        # Initialize threads for the category
        await initialize_threads(category)
        
        # Send the final message after the interaction is acknowledged
        await interaction.followup.send(f"Threads and channels have been initialized for the category: {category.name}")


    @tree.command(name="repairthread", description="Repair a thread by removing messages with invalid image URLs")
    async def repair_thread(interaction: discord.Interaction, thread_id: str = None):
        await interaction.response.defer()  # Defer response since this might take time

        # Use the current channel's assigned memory if no thread_id is provided
        if not thread_id:
            channel_id = interaction.channel.id
            category_id = interaction.channel.category.id if interaction.channel.category else None
            thread_id = await get_assigned_memory(channel_id, category_id)
            if not thread_id:
                await interaction.followup.send("Error: No assigned memory found for this channel.")
                return

        logging.info(f"Attempting to repair thread: {thread_id}")

        async with aiohttp.ClientSession() as session:
            # Step 1: List all messages with pagination
            messages = await list_thread_messages(session, thread_id)
            if not messages:
                await interaction.followup.send(f"Error: Could not fetch messages for thread {thread_id}.")
                return

            bad_message_ids = []
            for msg in messages:
                content = msg.get('content', [])
                msg_id = msg['id']
                if isinstance(content, list):
                    for item in content:
                        if item.get('type') == 'text':
                            text = item['text'].get('value', '')
                            if "https://cdn.discordapp.com" in text:
                                bad_message_ids.append(msg_id)
                                logging.info(f"Found problematic URL in text of message ID: {msg_id}, Content: {text}")
                        elif item.get('type') == 'image_url':
                            url = item['image_url'].get('url', '')
                            if "https://cdn.discordapp.com" in url or "image0.jpg" in url:
                                bad_message_ids.append(msg_id)
                                logging.info(f"Found problematic image URL in message ID: {msg_id}, URL: {url}")

            if not bad_message_ids:
                await interaction.followup.send(f"No messages with invalid image URLs found in thread {thread_id}.")
                return

            # Step 2: Delete problematic messages
            for msg_id in bad_message_ids:
                success = await delete_message(session, thread_id, msg_id)
                if not success:
                    await interaction.followup.send(f"Failed to delete message {msg_id} in thread {thread_id}.")
                    return

            # Step 3: Test the thread without sending a message
            test_response = await get_assistant_response("Test message", interaction.channel.id, assigned_memory=thread_id, send_message=False)
            if test_response and "Error: Run failed" not in test_response:
                await interaction.followup.send(f"Thread {thread_id} repaired successfully!")
            else:
                await interaction.followup.send(f"Thread {thread_id} still fails after repair: {test_response or 'No response received'}")

    @tree.command(name="listmemory", description="List memory details for a channel or thread")
    async def listmemory(interaction: discord.Interaction, channel: str = None, thread: str = None):
        await interaction.response.defer()
        
        try:
            channel_id = int(channel) if channel else interaction.channel.id
            thread_id = int(thread) if thread else None
            category_id = get_category_id(interaction)
            
            # Load the complete memory data
            category_threads = load_thread_data()
            category_id_str = str(category_id)
            channel_id_str = str(channel_id)
            
            if category_id_str not in category_threads:
                await interaction.followup.send("No memory data found for this category.")
                return
                
            category_data = category_threads[category_id_str]
            
            # Get the target object for proper mention
            target_channel = interaction.guild.get_channel(channel_id)
            target_thread = await interaction.guild.fetch_channel(thread_id) if thread_id else None
            
            if not target_channel:
                await interaction.followup.send("Channel not found.")
                return
            
            # Prepare response data
            response_data = {
                "target": target_thread.mention if target_thread else target_channel.mention,
                "memory_id": None,
                "memory_name": None,
                "always_on": None
            }
            
            # Check channel data first
            channel_data = category_data['channels'].get(channel_id_str)
            
            if thread_id:
                # Thread-specific memory
                if channel_data and 'threads' in channel_data:
                    thread_data = channel_data['threads'].get(str(thread_id))
                    if thread_data:
                        response_data.update({
                            "memory_id": thread_data.get('assigned_memory', 'None').strip("'\""),
                            "memory_name": thread_data.get('memory_name', 'None'),
                            "always_on": channel_data.get('always_on', False)  # Threads inherit channel's always_on
                        })
            else:
                # Channel memory
                if channel_data:
                    response_data.update({
                        "memory_id": channel_data.get('assigned_memory', 'None').strip("'\""),
                        "memory_name": channel_data.get('memory_name', 'None'),
                        "always_on": channel_data.get('always_on', False)
                    })
            
            # Format the response
            response = (
                f"**Memory details for {response_data['target']}**\n"
                f"• Memory ID: `{response_data['memory_id']}`\n"
                f"• Memory Name: `{response_data['memory_name']}`\n"
                f"• Always On: `{'✅ ON' if response_data['always_on'] else '❌ OFF'}`"
            )
            
            await interaction.followup.send(response)
            
        except ValueError:
            await interaction.followup.send("Error: Invalid channel or thread ID format.")
        except discord.NotFound:
            await interaction.followup.send("Error: Channel or thread not found.")
        except Exception as e:
            logging.error(f"Error in listmemory command: {str(e)}")
            await interaction.followup.send(f"An error occurred: {str(e)}")

    @listmemory.autocomplete('channel')
    async def listmemory_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @listmemory.autocomplete('thread')
    async def listmemory_thread_autocomplete(interaction: discord.Interaction, current: str):
        return await thread_autocomplete(interaction, current)

    
    @tree.command(name="reset_memory", description="Clear memory and Discord messages from a given message onward.")
    @app_commands.describe(
        channel="Target channel ID (optional).",
        thread="Target thread ID (optional).",
        starting_with_message_id="Start deleting from this message ID (inclusive)."
    )
    async def reset_memory_command(interaction: discord.Interaction, channel: str = None, thread: str = None, starting_with_message_id: str = None):
        await interaction.response.defer()

        try:
            channel_id = int(channel) if channel else interaction.channel.id
            thread_id = int(thread) if thread else None
            category_id = get_category_id(interaction)

            assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id=thread_id)
            if not assigned_memory:
                await interaction.followup.send("No memory assigned to this channel/thread.")
                return

            ref_timestamp = None
            if starting_with_message_id:
                try:
                    ref_message = await interaction.channel.fetch_message(int(starting_with_message_id))
                    ref_timestamp = ref_message.created_at
                except discord.NotFound:
                    logging.warning(f"Message ID {starting_with_message_id} not found in this channel.")
                    await interaction.followup.send("Invalid message ID — message not found.")
                    return

            # === DELETE OPENAI MEMORY ===
            async with aiohttp.ClientSession() as session:
                all_memory_messages = await list_thread_messages(session, assigned_memory)
                delete_count = 0
                for msg in all_memory_messages:
                    if not ref_timestamp or int(msg.get("created_at", 0)) >= int(ref_timestamp.timestamp()):
                        success = await delete_message(session, assigned_memory, msg['id'])
                        if success:
                            delete_count += 1
                            await asyncio.sleep(0.25)  # avoid rate limiting OpenAI too

            # === DELETE DISCORD MESSAGES ===
            deleted_discord_msgs = 0
            target = interaction.guild.get_channel(channel_id)
            if thread_id:
                target = await interaction.guild.fetch_channel(thread_id)

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
                f"• OpenAI messages deleted: `{delete_count}`\n"
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
