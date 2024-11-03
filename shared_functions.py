import logging
import discord
from helper_functions import get_category_id


always_on_channels = {}

async def set_always_on(channel_or_thread, always_on_value):
    """
    Set whether the AI assistant is always listening/responding in a channel or thread.
    
    :param channel_or_thread: The channel or thread where the setting will apply.
    :param always_on_value: String to turn always_on mode on ("on") or off ("off").
    """
    if always_on_value == "on":
        always_on_channels[channel_or_thread.id] = True  # Add to the dictionary
        await channel_or_thread.send("AI assistant is now always listening to all messages.")
        logging.info(f"Channel {channel_or_thread.id} set to always on.")
    else:
        if channel_or_thread.id in always_on_channels:
            del always_on_channels[channel_or_thread.id]  # Remove from the dictionary
            await channel_or_thread.send("AI assistant is now only responding when mentioned.")
            logging.info(f"Channel {channel_or_thread.id} set to respond only to mentions.")

async def send_response_in_chunks(channel, response):
    if len(response) > 2000:
        for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
            await channel.send(chunk)
    else:
        await channel.send(response)

async def send_response(interaction: discord.Interaction, response: str, channel_id: int = None, thread_id: int = None):
    """Send a response to a specified channel or thread. Defaults to #telldm if none provided."""
    logging.info(f"Channel ID: {channel_id}, Thread ID: {thread_id}")

    # Get the category ID from the interaction
    category_id = get_category_id(interaction)

    if channel_id is None:  # No channel provided, use #telldm
        target_channel = discord.utils.get(interaction.guild.channels, name='telldm', category=interaction.channel.category)
    else:
        target_channel = interaction.guild.get_channel(channel_id)

    if target_channel:
        # Attempt to fetch the thread by ID just before sending the response
        if thread_id:
            target_thread = discord.utils.get(target_channel.threads, id=thread_id)
            if not target_thread:
                await interaction.followup.send(f"Thread with ID {thread_id} not found in channel <#{target_channel.name}>.")
                return
            # Send response in the thread
            await send_response_in_chunks(target_thread, response)
            # Notify where the answer was sent with a channel mention
            await interaction.followup.send(f"Your answer has been sent in the thread: <#{target_thread.id}>  in channel: <#{target_channel.id}>.")
        else:
            # Send response in the main channel if no thread ID is given
            await send_response_in_chunks(target_channel, response)
            # Notify where the answer was sent with a channel mention
            await interaction.followup.send(f"Your answer has been sent in channel: <#{target_channel.id}>.")
    else:
        await interaction.followup.send(f"Channel with ID {channel_id} not found.")
