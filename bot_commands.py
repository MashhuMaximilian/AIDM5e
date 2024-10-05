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
            prompt = f"This is a query about game mechanics and gameplay elements based on official sources like the Player’s Handbook (PHB) or Dungeon Master’s Guide (DMG). Please provide a detailed explanation with rules, examples, and references to relevant sources. Here is the question: {query}"

        elif query_type.value == "monsters_creatures":
            prompt = f"This is a question about monsters or creatures, including those from the Monster Manual or homebrew. Please include their abilities, weaknesses, lore, and strategies for handling them in combat. Provide references to the source and links to reliable websites. Question: {query}"

        elif query_type.value == "world_lore_history":
            prompt = f"This is an inquiry about the lore, history, and cosmology of the game world. Provide a detailed explanation with relevant background information, official sources, and any notable events or characters. Include links to 3 reliable websites. Question: {query}"

        elif query_type.value == "conditions_effects":
            prompt = f"This is a question about conditions and their effects, such as stunned, poisoned, grappled, etc. Please explain their rules, implications in combat and exploration, and provide any interactions with spells or abilities. Reference official sources like the PHB or DMG. Question: {query}"

        elif query_type.value == "rules_clarifications":
            prompt = f"This is a query about specific rule clarifications. Please provide a clear and detailed explanation based on official sources, and include any applicable errata or optional rules. Reference the PHB, DMG, or other official sourcebooks. Question: {query}"
        
        elif query_type.value == "race_class":
            prompt = f"This is a question about a D&D race, class, or subclass, including official content or homebrew. Please provide details on abilities, traits, key features, and how to optimize gameplay. Include lore, background, and roleplaying suggest for the race or class. If possible, compare it with similar races or classes. Provide references to the source material and links to reliable websites. Question: {query}"

        # Get response from the assistant
        response = await get_assistant_response(prompt, interaction.channel.id)

        # Check if the response is longer than 2000 characters and split it
        if len(response) > 2000:
            chunks = [response[i:i + 2000] for i in range(0, len(response), 2000)]
            for chunk in chunks:
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(response)  # Send the final response if it's within the limit

    @tree.command(name="send", description="Send specified messages or files to another channel.")
    async def send(interaction: discord.Interaction, message_ids: str, target_channel: discord.TextChannel):
        await interaction.response.defer()  # Defer the response while we process
        ids = message_ids.strip("[]").split(",")  # Parse the message IDs from input
        ids = [id.strip() for id in ids]

        try:
            for msg_id in ids:
                msg_id = int(msg_id.strip())
                # Retrieve the message object
                message = await interaction.channel.fetch_message(msg_id)

                if message.content:
                    await target_channel.send(content=f"{message.author} said: {message.content}")

                if message.attachments:
                    for attachment in message.attachments:
                        await attachment.to_file()
                        await target_channel.send(file=attachment)

            await interaction.followup.send(f"Messages and files sent to {target_channel.mention}")
        except Exception as e:
            await interaction.followup.send(f"Error sending messages: {str(e)}")

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

        # Ensure the response doesn't exceed Discord's message length limit
        if len(response) > 2000:
            for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(response)

    @tree.command(name="feedback", description="Provide feedback about the AIDM’s performance or game experience.")
    async def feedback(interaction: discord.Interaction, suggestions: str):
        await interaction.response.defer()  # Defer response while we process

        # Define the prompt for the feedback
        prompt = f"This is feedback regarding the AIDM’s performance or the game experience. Please consider this feedback to improve future responses and gameplay interactions. {suggestions}"

        # Find the channel in the same category named 'telldm'
        telldm_channel = discord.utils.get(interaction.channel.category.channels, name="telldm")

        # If the channel doesn't exist, create it
        if telldm_channel is None:
            # Ensure the bot has permission to create channels
            guild = interaction.guild
            telldm_channel = await guild.create_text_channel(name="telldm", category=interaction.channel.category)
            await interaction.followup.send(f"The #telldm channel was not found, so I created it in the same category.")

        # Send the feedback to the #telldm channel
        await telldm_channel.send(f"Feedback from {interaction.user}: {suggestions}")

        # Fetch message history from the #telldm channel
        messages = []
        async for message in telldm_channel.history(limit=100):
            messages.append(f"{message.author.name}: {message.content}")

        if not messages:
            await interaction.followup.send("No messages found in the #telldm channel.")
            return

        # Create a conversation history from the messages
        conversation_history = "\n".join(messages)

        # Send the conversation to the assistant for summarization
        response = await get_assistant_response(conversation_history, interaction.channel.id)

        # Ensure the response doesn't exceed Discord’s message length limit
        if len(response) > 2000:
            for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(response)
