# bot_commands.py

import discord
from discord import app_commands
from shared_functions import *
from helper_functions import *
import logging
from memory_management import create_memory, get_assigned_memory

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

        # Step 1: Check if 'telldm' channel exists in the same category
        feedback_channel = discord.utils.get(interaction.channel.category.channels, name="feedback")

        # If the channel doesn't exist, create it
        if feedback_channel is None:
            guild = interaction.guild
            feedback_channel = await guild.create_text_channel(name="feedback", category=interaction.channel.category)
            await interaction.followup.send(f"The #telldm channel was not found, so I created it in the same category.")

        # Step 2: Send the feedback message to #telldm
        feedback_message = await feedback_channel.send(f"Feedback from {interaction.user.name}: {suggestions}")
        await interaction.followup.send(f"Your feedback has been sent to {feedback_channel.mention}.")

        # Step 3: Fetch all messages from the #telldm channel
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

        # Step 5: Send the conversation to the assistant for summarization, focusing on the last message
        prompt = (f"Make a recap the following feedback messages regarding the AIDM’s performance. "
                f"Here is the entire message history from the #telldm channel:\n\n{conversation_history}"
                f"Pay special attention to the **last feedback message**, which is:\n\n{last_message}\n\n"
                f"Summarize this last message briefly and confirm you understood the feedback. "
                f"Also mention that you have reviewed all feedback messages for better implementation. ")

        response = await get_assistant_response(prompt, interaction.channel.id)

        await send_response_in_chunks(response)


        # Step 7: Confirm that the feedback was processed
        await interaction.followup.send(f"Feedback has been processed and a recap has been posted in {feedback_channel.mention}.")


    @tree.command(name="send", description="Send specified messages to another channel.")
    @app_commands.describe(
        target_channel="Channel(s) to send messages to (select from the same category).",
        thread="Select a thread in the target channel (optional).",
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to send (comma-separated if multiple).",
        summarize_options="Options for summarization: yes, no, only recap.",
        query="Additional requests or context for the messages."
    )
    @app_commands.choices(summarize_options=[
        app_commands.Choice(name="Yes", value="yes"),
        app_commands.Choice(name="No", value="no"),
        app_commands.Choice(name="Only Recap", value="only summary")
    ])
    async def send(
        interaction: discord.Interaction,
        target_channel: str, 
        thread: str = None, 
        start: str = None,
        end: str = None,
        message_ids: str = None,
        summarize_options: str = "no",
        query: str = None  # New query parameter
    ):
        await interaction.response.defer()  # Defer the response while processing

        # Fetch the current channel
        channel = interaction.channel

        # Fetch conversation history based on provided parameters
        conversation_history, options_or_error = await fetch_conversation_history(channel, start, end, message_ids)

        # Check if the response is an error message
        if isinstance(options_or_error, str):
            await interaction.followup.send(options_or_error)  # Send error message
            return

        # Check if the selected target_channel is in the same category
        target_channel_obj = interaction.guild.get_channel(int(target_channel))  # Convert to channel ID
        if target_channel_obj.category == channel.category:
            # Fetch threads for the selected target_channel
            discord_threads = await fetch_discord_threads(target_channel_obj)

            # If there are threads, send them as options to the user
            if discord_threads:
                thread_names = ", ".join(thread.name for thread in discord_threads)
            else:
                await interaction.followup.send(f"No threads available in {target_channel_obj.name}.")

            # Use the target thread if specified, otherwise use the target channel directly
            target = interaction.guild.get_thread(int(thread)) if thread else target_channel_obj

            # Flag to track if messages were sent
            messages_sent = False

            # Handle summarization based on the summarize_options
            if summarize_options == "yes" or summarize_options == "no":
                # Send messages first
                for message in conversation_history:
                    await send_response_in_chunks(target, message)
                    messages_sent = True

            # Handle summary
            if summarize_options == "yes":
                summary = await summarize_conversation(interaction, conversation_history, options_or_error, query)  # Pass query to summary
                if summary:
                    await send_response_in_chunks(target, summary)
                await interaction.followup.send(f"Messages and recap sent successfully to {'thread' if thread else 'channel'} <#{target_channel_obj.id}>.")

            elif summarize_options == "no":
                if messages_sent:
                    await interaction.followup.send(f"Messages sent successfully to {'thread' if thread else 'channel'} <#{target_channel_obj.id}>.")

            elif summarize_options == "only summary":
                summary = await summarize_conversation(interaction, conversation_history, options_or_error, query)  # Pass query to summary
                if summary:
                    await send_response_in_chunks(target, summary)
                await interaction.followup.send(f"Recap sent successfully to {'thread' if thread else 'channel'} <#{target_channel_obj.id}>.")

        else:
            await interaction.followup.send(f"Cannot send messages to {target_channel_obj.name}. Must be in the same category.")

    @send.autocomplete('target_channel')
    async def target_channel_autocomplete(interaction: discord.Interaction, current: str):
        return await channel_autocomplete(interaction, current)

    @send.autocomplete('thread')
    async def send_thread_autocomplete(interaction: discord.Interaction, current: str):
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
        app_commands.Choice(name="ON", value="true"),   # String choice
        app_commands.Choice(name="OFF", value="false")   # String choice
    ])

    async def startnew(
        interaction: discord.Interaction,
        channel: str,
        always_on: app_commands.Choice[str],  # Keep it as string
        memory: str,
        memory_name: str = None,
        channel_name: str = None,
        thread_name: str = None,
        thread: str = None
    ):
        await interaction.response.defer()

        # Convert string choice to boolean
        always_on_value = always_on.value == "true"

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

        # Use the target channel's ID for memory assignment
        channel_id = target_channel.id  
        logging.info(f"Assigning memory to Channel ID: {channel_id}, Memory: {memory_name or memory}")

        # Use assign_memory to assign memory
        memory_assignment_result = await assign_memory(
            interaction,
            memory_name or memory,
            channel_id=channel_id,
            thread_id=str(thread_obj.id) if thread_obj else None
        )
        assigned_memory_name = memory_name or memory
        assigned_memory_id = memory_assignment_result.split()[-1].strip("'.")

        if "Error" in assigned_memory_id:
            await interaction.followup.send(assigned_memory_id)
            return

        # Update the JSON data with assigned_memory and memory_name
        category_id_str = str(interaction.channel.category.id)
        category_threads = load_thread_data()  # Load your JSON data

        # Update the channel entry in the JSON
        channel_data = category_threads[category_id_str]['channels'].setdefault(str(target_channel.id), {
            "name": target_channel.name,
            "assigned_memory": None,  # Set initially to None, will be updated
            "memory_name": None,      # Set initially to None, will be updated
            "always_on": False, 
            "threads": {}
        })

        # Store the assigned memory ID in the channel entry
        channel_data['assigned_memory'] = assigned_memory_id  # Get the memory ID from the result
        channel_data['memory_name'] = assigned_memory_name  # Ensure memory_name is set
        channel_data['always_on'] = always_on_value  # Use converted boolean value

        if thread_obj:
            # Add or update the thread in the JSON with the correct assigned memory
            channel_data['threads'][str(thread_obj.id)] = {
                "name": thread_obj.name,
                "assigned_memory": assigned_memory_id,  # Correctly assign memory ID here
                "memory_name": assigned_memory_name  # Ensure memory_name is set
            }

        # Save the updated JSON data
        save_thread_data(category_threads)
        
                # Set the always_on setting for the channel or thread
        if thread_obj:  
            await set_always_on(thread_obj, always_on_value)  # Apply always_on to the new thread
            logging.info(f"Thread {thread_obj.id} set to always on: {always_on_value}.")
        else:  
            await set_always_on(target_channel, always_on_value)  # Apply always_on to the channel
            logging.info(f"Channel {target_channel.id} set to always on: {always_on_value}.")

        # Prepare success message
        if thread == "NEW THREAD":
            success_message = f"Thread '<#{thread_obj.id}>' created and assigned memory '{assigned_memory_name}'."
        else:
            success_message = f"Memory '{assigned_memory_name}' assigned to {'thread' if thread_obj else 'channel'} <#{thread_obj.id if thread_obj else target_channel.id}>."

        await interaction.followup.send(success_message)


    @startnew.autocomplete('channel')
    async def channel_autocomplete_wrapper(interaction: discord.Interaction, current: str):
            # Call the existing channel autocomplete function
            choices = await channel_autocomplete(interaction, current)

            # Add the option to create a new channel
            choices.append(discord.app_commands.Choice(name="CREATE A NEW CHANNEL", value="NEW CHANNEL"))

            return choices[:50]  # Limit to 50 suggestions

    @startnew.autocomplete('thread')
    async def thread_autocomplete_wrapper(interaction: discord.Interaction, current: str):
            # Call the existing thread autocomplete function
            choices = await thread_autocomplete(interaction, current)

            # Add the option to create a new thread
            choices.append(discord.app_commands.Choice(name="CREATE A NEW THREAD", value="NEW THREAD"))

            return choices[:50]  # Limit to 50 suggestions

    @startnew.autocomplete('memory')
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

        category_id_str = str(interaction.channel.category.id)

        # Handle creating a new memory if requested
        if memory == "CREATE NEW MEMORY":
            if not memory_name:
                await interaction.followup.send("Error: You must provide a name for the new memory.")
                return

            # Create the new memory
            memory_thread_id = await create_memory(interaction, memory_name, category_id_str)

            # Now proceed to assign the newly created memory to the channel or thread
            memory_assignment_result = await assign_memory(
                interaction,
                memory_name,
                channel_id=channel,
                thread_id=thread,
                memory_name=memory_name
            )

            # Fetch channel and thread objects
            target_channel = interaction.guild.get_channel(int(channel)) if channel.isdigit() else None
            target_thread = await interaction.guild.fetch_channel(int(thread)) if thread else None

            # Apply always_on setting if specified
            if always_on:
                if target_thread:
                    await set_always_on(target_thread, always_on.value == "on")
                elif target_channel:
                    await set_always_on(target_channel, always_on.value == "on")

            # Send response
            if target_thread:
                await interaction.followup.send(
                    f"Memory '{memory_name}' created and assigned successfully to thread {target_thread.mention} in channel {target_channel.mention}."
                )
            elif target_channel:
                await interaction.followup.send(
                    f"Memory '{memory_name}' created and assigned successfully to channel {target_channel.mention}."
                )
            else:
                await interaction.followup.send(f"Memory '{memory_name}' created but the specified channel or thread was not found.")
            return

        # If not creating a new memory, just proceed to assign it
        memory_assignment_result = await assign_memory(
            interaction,
            memory,
            channel_id=channel,
            thread_id=thread,
            memory_name=memory_name
        )

        # Fetch the channel and thread objects for the non-creation case
        target_channel = interaction.guild.get_channel(int(channel)) if channel.isdigit() else None
        target_thread = await interaction.guild.fetch_channel(int(thread)) if thread else None

        # Apply always_on setting if specified
        if always_on:
            if target_thread:
                await set_always_on(target_thread, always_on.value == "on")
            elif target_channel:
                await set_always_on(target_channel, always_on.value == "on")

        # Send response
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
    