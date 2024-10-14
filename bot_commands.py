# bot_commands.py

import discord
from discord import app_commands
from message_handlers import send_response_in_chunks
from assistant_interactions import create_or_get_thread, get_assistant_response
from config import HEADERS

from helper_functions import *

import logging

    # Set up logging (you can configure this as needed)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_commands(tree, get_assistant_response):

    @tree.command(name="tellme", description="Info about spells, items, NPCs, character status, inventory, or roll checks.")
    @app_commands.choices(
        query_type=[
            app_commands.Choice(name="Spell", value="spell"),
            app_commands.Choice(name="CheckStatus", value="checkstatus"),
            app_commands.Choice(name="Item", value="item"),
            app_commands.Choice(name="NPC", value="npc"),
            app_commands.Choice(name="Inventory", value="inventory"),
            app_commands.Choice(name="RollCheck", value="rollcheck")
        ]
    )
    async def tellme(interaction: discord.Interaction, query_type: app_commands.Choice[str], query: str):
        await interaction.response.defer()  # Defer response while we process

        # Detailed prompt for each query type
        if query_type.value == "spell":
            prompt = f"I have a question about the spell. Besides your answer, be sure to also send the description of the spell mentioned, that you can find in the Player's Handbook, with its parameters: casting time, level, components, description, range, duration, attack/save, damage/effect, and a link to where somebody could find that spell on one of these websites: http://dnd5e.wikidot.com/, https://www.dndbeyond.com/, https://roll20.net/compendium/dnd5e, or https://www.aidedd.org/dnd. {query}"
        
        elif query_type.value == "checkstatus":
            prompt = f"I would like to know the current status of a character, including HP, spell slots, conditions, and any other relevant information. {query}"
        
        elif query_type.value == "item":
            prompt = f"I have a question about an item. Besides your answer, include the item’s full description, properties, and usage, as detailed in the Player’s Handbook or Dungeon Master’s Guide. Also, provide a link to where someone can find more information about the item on these websites: http://dnd5e.wikidot.com/, https://www.dndbeyond.com/, https://roll20.net/compendium/dnd5e, or https://www.aidedd.org/dnd. {query}"
        
        elif query_type.value == "npc":
            prompt = f"I have a question about an NPC. Provide all known information about this NPC, including their background, motivations, recent interactions with the party. {query}"
        
        elif query_type.value == "inventory":
            prompt = f"I have a question about the inventory of a character. Please provide a detailed list of items currently in the specified character’s inventory, including any magical properties or special features. If asking about a specific item, confirm its presence and provide details. {query}"
        
        elif query_type.value == "rollcheck":
            prompt = f"I want to test the feasibility of an action or a skill check before deciding to do it in the game. Please provide guidance on what I would need to roll, including the appropriate skill and any potential outcomes or modifiers to consider. {query}"

        # Get response from the assistant
        response = await get_assistant_response(prompt, interaction.channel.id)
        # Call the send_to_tellme function
        await send_to_telldm(interaction, response)


    @tree.command(name="askdm", description="Inquire about rules, lore, monsters, and more.")
    @app_commands.choices(
        query_type=[
            app_commands.Choice(name="Game Mechanics", value="game_mechanics"),
            app_commands.Choice(name="Monsters & Creatures", value="monsters_creatures"),
            app_commands.Choice(name="World Lore & History", value="world_lore_history"),
            app_commands.Choice(name="Conditions & Effects", value="conditions_effects"),
            app_commands.Choice(name="Rules Clarifications", value="rules_clarifications"),
            app_commands.Choice(name="Race or Class", value="race_class")
        ]
    )
    async def askdm(interaction: discord.Interaction, query_type: app_commands.Choice[str], query: str):
        await interaction.response.defer()  # Defer response while we process

        # Construct the prompt based on query type
        prompt = ""
        if query_type.value == "game_mechanics":
            prompt = f"This is a query about game mechanics and gameplay elements based on official sources like the Player’s Handbook (PHB) or Dungeon Master’s Guide (DMG). Please provide a detailed explanation with rules, examples, and references to relevant sources as well as links from https://www.dndbeyond.com/, https://rpgbot.net/dnd5, or https://roll20.net/. Here is the question: {query}"

        elif query_type.value == "monsters_creatures":
            prompt = f"This is a question about monsters or creatures, including those from the Monster Manual or homebrew. Please include their abilities, weaknesses, lore, and strategies for handling them in combat. Provide references to the source and links to reliable websites like a link to where somebody could find that spell on one of these websites: http://dnd5e.wikidot.com/, https://www.dndbeyond.com/, https://roll20.net/compendium/dnd5e, https://forgottenrealms.fandom.com/wiki, or https://www.aidedd.org/dnd. Question: {query}"

        elif query_type.value == "world_lore_history":
            prompt = f"This is an inquiry about the lore, history, and cosmology of the game world. Provide a detailed explanation with relevant background information, official sources, and any notable events or characters. Include links to 3 reliable links to relevant websites. Question: {query}"

        elif query_type.value == "conditions_effects":
            prompt = f"This is a question about conditions and their effects, such as stunned, poisoned, grappled, etc. Please explain their rules, implications in combat and exploration, and provide any interactions with spells or abilities. Reference official sources like the PHB or DMG or links from https://www.dndbeyond.com/, https://rpgbot.net/dnd5, or https://roll20.net/. Question: {query}"

        elif query_type.value == "rules_clarifications":
            prompt = f"This is a query about specific rule clarifications. Please provide a clear and detailed explanation based on official sources, and include any applicable errata or optional rules. Reference the PHB, DMG, or other official sourcebooks or links from https://www.dndbeyond.com/, https://rpgbot.net/dnd5, or https://roll20.net/. Question: {query}"
        
        elif query_type.value == "race_class":
            prompt = f"This is a question about a D&D race, class, or subclass, including official content or homebrew. Please provide details on abilities, traits, key features, and how to optimize gameplay. Include lore, background, and roleplaying suggest for the race or class. If possible, compare it with similar races or classes. Provide references to the source material and links to reliable websites like https://forgottenrealms.fandom.com/wiki, https://www.dndbeyond.com/, https://rpgbot.net/dnd5, or https://roll20.net/. Question: {query}"

        # Get response from the assistant
        response = await get_assistant_response(prompt, interaction.channel.id)

        # Check if the response is longer than 2000 characters and split it
        await send_to_telldm(interaction, response)
    
   
    @tree.command(name="summarize", description="Summarize messages based on different options.")
    @app_commands.describe(
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to summarize.",
        query="Additional requests or context for the summary."
    )
    async def summarize(interaction: discord.Interaction, start: str = None, end: str = None, message_ids: str = None, query: str = None):
        await interaction.response.defer()  # Defer the response while processing

        # Fetch the channel
        channel = interaction.channel
        
        # Fetch conversation history based on provided parameters
        conversation_history, options_or_error = await fetch_conversation_history(channel, start, end, message_ids)

        # Check if the response is an error message
        if isinstance(options_or_error, str):
            await interaction.followup.send(options_or_error)  # Send error message
            return

        options = options_or_error  # Assign the options for summarization

        # Summarize the conversation
        response = await summarize_conversation(interaction, conversation_history, options, query)

        # Send the summarized response in chunks
        if response:  # Ensure response is not empty
            await send_response_in_chunks(interaction.channel, response)
        else:
            await interaction.followup.send("No content to summarize.")  # Optional: handle empty response



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
        prompt = (f"Summarize the following feedback messages regarding the AIDM’s performance. "
                f"Here is the entire message history from the #telldm channel:\n\n{conversation_history}"
                f"Pay special attention to the **last feedback message**, which is:\n\n{last_message}\n\n"
                f"Summarize this last message briefly and confirm you understood the feedback. "
                f"Also mention that you have reviewed all feedback messages for better implementation. ")

        response = await get_assistant_response(prompt, interaction.channel.id)

        await send_response_in_chunks(response)


        # Step 7: Confirm that the feedback was processed
        await interaction.followup.send(f"Feedback has been processed and a summary has been posted in {feedback_channel.mention}.")



    class ChannelInCategoryTransformer(app_commands.Transformer):
        async def transform(self, interaction: discord.Interaction, value: str) -> discord.TextChannel:
            channel = interaction.guild.get_channel(int(value))
            if channel and channel.category == interaction.channel.category:
                return channel
            raise app_commands.TransformError("Channel is not in the same category.")

        async def autocomplete(self, interaction: discord.Interaction, current: str):
            current_category = interaction.channel.category
            channels_in_category = [
                app_commands.Choice(name=channel.name, value=str(channel.id))
                for channel in interaction.guild.text_channels if channel.category == current_category
            ]
            return channels_in_category
    class ThreadInChannelTransformer(app_commands.Transformer):
        async def transform(self, interaction: discord.Interaction, value: str) -> discord.Thread:
            try:
                thread_id = int(value)
            except ValueError:
                raise app_commands.TransformerError(
                    f"Invalid thread ID: {value}",
                    opt_type=self.__class__,
                    transformer=self
                )

            # Fetch the thread by its ID
            thread = interaction.guild.get_thread(thread_id)
            if thread is None:
                raise app_commands.TransformerError(
                    f"No thread found with ID: {thread_id}",
                    opt_type=self.__class__,
                    transformer=self
                )

            # Fetch target_channel object from the interaction namespace (autocomplete might pass a string)
            target_channel = interaction.namespace.target_channel
            if isinstance(target_channel, discord.TextChannel):
                # We already have the channel object from autocomplete
                pass
            elif isinstance(target_channel, str):
                # Convert target_channel string (ID) to an actual channel object
                try:
                    target_channel = interaction.guild.get_channel(int(target_channel))
                except (ValueError, TypeError):
                    raise app_commands.TransformerError(
                        f"Invalid channel ID: {target_channel}",
                        opt_type=self.__class__,
                        transformer=self
                    )
            else:
                raise app_commands.TransformerError(
                    "Unable to determine target channel.",
                    opt_type=self.__class__,
                    transformer=self
                )

            # Debugging: log thread and parent information
            logger.info(f"Checking thread: {thread.name} (ID: {thread.id})")
            logger.info(f"Thread parent ID: {thread.parent_id}, Target Channel ID: {target_channel.id}")

            # Ensure the thread belongs to the selected target channel
            if thread.parent_id != target_channel.id:
                raise app_commands.TransformerError(
                    "Selected thread does not belong to the specified channel.",
                    opt_type=self.__class__,
                    transformer=self
                )

            return thread

        async def autocomplete(self, interaction: discord.Interaction, current: str):
            # Get the selected target channel's threads
            target_channel_id = interaction.data.get('options')[0].get('value')  # Get the ID from the previous selection
            if target_channel_id:
                target_channel = interaction.guild.get_channel(int(target_channel_id))
                if target_channel:
                    # Log the channel being fetched
                    logger.info(f"Fetching threads for channel: {target_channel.name} (ID: {target_channel.id})")
                    threads = await fetch_discord_threads(target_channel)
                    logger.info(f"Fetched threads: {[thread.name for thread in threads]}")  # Log fetched threads
                    return [
                        app_commands.Choice(name=thread.name, value=str(thread.id))
                        for thread in threads
                    ]
            return []


    @tree.command(name="send", description="Send specified messages to another channel.")
    @app_commands.describe(
        target_channel="Channel(s) to send messages to (select from the same category).",
        subchannel="Select a thread in the target channel (optional).",
        start="Message ID to start from (if applicable).",
        end="Message ID to end at (if applicable).",
        message_ids="Individual message IDs to send (comma-separated if multiple).",
        summarize_options="Options for summarization: yes, no, only summary.",
        query="Additional requests or context for the messages."
    )
    @app_commands.choices(summarize_options=[
        app_commands.Choice(name="Yes", value="yes"),
        app_commands.Choice(name="No", value="no"),
        app_commands.Choice(name="Only Summary", value="only summary")
    ])
    async def send(
        interaction: discord.Interaction,
        target_channel: ChannelInCategoryTransformer,
        subchannel: ThreadInChannelTransformer = None,
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
        if target_channel.category == channel.category:
            # Fetch threads for the selected target_channel
            discord_threads = await fetch_discord_threads(target_channel)

            # If there are threads, send them as options to the user
            if discord_threads:
                thread_names = ", ".join(thread.name for thread in discord_threads)
            else:
                await interaction.followup.send(f"No threads available in {target_channel.name}.")

            # Use the target thread if specified, otherwise use the target channel directly
            target = subchannel if subchannel else target_channel

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
                await interaction.followup.send(f"Messages and summary sent successfully to {'thread' if subchannel else 'channel'} <#{target.id}>.")

            elif summarize_options == "no":
                if messages_sent:
                    await interaction.followup.send(f"Messages sent successfully to {'thread' if subchannel else 'channel'} <#{target.id}>.")

            elif summarize_options == "only summary":
                summary = await summarize_conversation(interaction, conversation_history, options_or_error, query)  # Pass query to summary
                if summary:
                    await send_response_in_chunks(target, summary)
                # await interaction.followup.send("Summary sent successfully to {target.mention}.")
                await interaction.followup.send(f"Summary sent successfully to {'thread' if subchannel else 'channel'} <#{target.id}>.")

        else:
            await interaction.followup.send(f"Cannot send messages to {target_channel.name}. Must be in the same category.")
