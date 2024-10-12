# bot_commands.py

import discord
from discord import app_commands


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

        # Check if the response is longer than 2000 characters and split it
        if len(response) > 2000:
            chunks = [response[i:i + 2000] for i in range(0, len(response), 2000)]
            for chunk in chunks:
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(response)  # Send the final response if it's within the limit


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
        if len(response) > 2000:
            chunks = [response[i:i + 2000] for i in range(0, len(response), 2000)]
            for chunk in chunks:
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(response)  # Send the final response if it's within the limit

    @tree.command(name="summarize", description="Summarize all messages starting from a given message ID.")
    async def summarize(interaction: discord.Interaction, start: str):
        await interaction.response.defer()  # Defer the response while processing

        # Convert the start ID to an integer
        try:
            start_id = int(start)
        except ValueError:
            await interaction.followup.send("Invalid message ID format. Please provide a valid message ID.")
            return

        # Fetch the channel and the message
        channel = interaction.channel
        try:
            start_message = await channel.fetch_message(start_id)
        except discord.errors.NotFound:
            await interaction.followup.send(f"Message with ID {start_id} not found.")
            return

        # Fetch all messages from the channel starting from the specified message
        messages = []
        async for message in channel.history(after=start_message, limit=100):
            messages.append(f"{message.author.name}: {message.content}")

        if not messages:
            await interaction.followup.send("No messages found after the specified message.")
            return

        # Create a single string to summarize
        conversation_history = "\n".join(messages)

        # Send the conversation to the assistant for summarization
        prompt = f"Summarize the following conversation. Summarize the events of this D&D session in detail, assuming the players might forget everything by next week. Include all important story elements, player actions, combat encounters, NPC interactions, and notable dialogue. Focus on providing enough detail so the players can pick up where they left off without confusion. Mention character names, key decisions, challenges they faced, and unresolved plot points. If there were major revelations or twists, highlight them. End the summary by outlining what the players need to remember or focus on for the next session. Here is where you start:\n\n{conversation_history}"
        response = await get_assistant_response(prompt, interaction.channel.id)

        # Check if 'session-summary' channel exists in the same category
        summary_channel = discord.utils.get(interaction.channel.category.channels, name="session-summary")

        if summary_channel is None:
            # Create the 'session-summary' channel in the same category
            summary_channel = await interaction.guild.create_text_channel(name="session-summary", category=interaction.channel.category)
            await interaction.followup.send(f"The #session-summary channel was not found, so I created it in the same category.")

        # Send the summary to the session-summary channel
        if len(response) > 2000:
            for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
                await summary_channel.send(chunk)
        else:
            await summary_channel.send(response)

        await interaction.followup.send(f"Summary has been posted to {summary_channel.mention}.")
# uncomment this function if it does not work.
        # async def summarize(interaction: discord.Interaction, start: str):
        #     await interaction.response.defer()  # Defer the response while processing

        #     # Convert the start ID to an integer
        #     try:
        #         start_id = int(start)
        #     except ValueError:
        #         await interaction.followup.send("Invalid message ID format. Please provide a valid message ID.")
        #         return

        #     # Fetch the channel and the message
        #     channel = interaction.channel
        #     try:
        #         start_message = await channel.fetch_message(start_id)
        #     except discord.errors.NotFound:
        #         await interaction.followup.send(f"Message with ID {start_id} not found.")
        #         return

        #     # Fetch all messages from the channel starting from the specified message
        #     messages = []
        #     async for message in channel.history(after=start_message, limit=100):
        #         messages.append(f"{message.author.name}: {message.content}")

        #     if not messages:
        #         await interaction.followup.send("No messages found after the specified message.")
        #         return

        #     # Create a single string to summarize
        #     conversation_history = "\n".join(messages)

        #     # Send the conversation to the assistant for summarization
        #     prompt = f"Summarize the following conversation. Summarize the events of this D&D session in detail, assuming the players might forget everything by next week. Include all important story elements, player actions, combat encounters, NPC interactions, and notable dialogue. Focus on providing enough detail so the players can pick up where they left off without confusion. Mention character names, key decisions, challenges they faced, and unresolved plot points. If there were major revelations or twists, highlight them. End the summary by outlining what the players need to remember or focus on for the next session. Here is where you start:\n\n{conversation_history}"
        #     response = await get_assistant_response(prompt, interaction.channel.id)

        #     # Ensure the response doesn't exceed Discord's message length limit
        #     if len(response) > 2000:
        #         for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
        #             await interaction.followup.send(chunk)
        #     else:
        #         await interaction.followup.send(response)

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
        async for message in feedback_channel.history(limit=100):
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

        # Step 6: Ensure the response doesn't exceed Discord's message length limit
        if len(response) > 2000:
            for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
                await feedback_channel.send(chunk)
        else:
            await feedback_channel.send(response)

        # Step 7: Confirm that the feedback was processed
        await interaction.followup.send(f"Feedback has been processed and a summary has been posted in {feedback_channel.mention}.")

    class ChannelInCategoryTransformer(app_commands.Transformer):
        async def transform(self, interaction: discord.Interaction, value: str) -> discord.TextChannel:
            # Convert the value (which should be a channel ID) into a channel object
            channel = interaction.guild.get_channel(int(value))
            if channel and channel.category == interaction.channel.category:
                return channel
            raise app_commands.TransformError(f"Channel is not in the same category as the current channel.")

        async def autocomplete(self, interaction: discord.Interaction, current: str):
            # Filter channels in the same category
            current_category = interaction.channel.category
            channels_in_category = [
                app_commands.Choice(name=channel.name, value=str(channel.id))
                for channel in interaction.guild.text_channels if channel.category == current_category
            ]
            return channels_in_category

    @tree.command(name="send", description="Send specified messages or files to another channel in the same category.")
    @app_commands.describe(message_ids="Comma-separated message IDs", target_channel="Select the target channel")
    @app_commands.autocomplete(target_channel=ChannelInCategoryTransformer().autocomplete)
    async def send(interaction: discord.Interaction, message_ids: str, target_channel: str):
        await interaction.response.defer()  # Defer the response while processing

        # Convert the string target_channel (ID) to a TextChannel object
        channel = interaction.guild.get_channel(int(target_channel))
        
        # Check that the target channel is in the same category (this is a safety check)
        if channel.category != interaction.channel.category:
            await interaction.followup.send("You can only send messages to channels in the same category.")
            return

        # Proceed with sending the messages if categories match
        ids = message_ids.strip("[]").split(",")
        ids = [id.strip() for id in ids]

        try:
            for msg_id in ids:
                msg_id = int(msg_id.strip())
                # Retrieve the message object
                message = await interaction.channel.fetch_message(msg_id)

                if message.content:
                    await channel.send(content=f"{message.author} said: {message.content}")

                if message.attachments:
                    for attachment in message.attachments:
                        await channel.send(file=await attachment.to_file())

            await interaction.followup.send(f"Messages and files sent to {channel.mention}")
        except Exception as e:
            await interaction.followup.send(f"Error sending messages: {str(e)}")
