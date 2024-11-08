import logging
import discord
from config import client
from utils import load_thread_data, save_thread_data


always_on_channels = {}

async def set_always_on(channel_or_thread, always_on_value):
    existing_data = load_thread_data()
    if existing_data is None:
        existing_data = {}

    category_id = str(channel_or_thread.category.id)
    channel_id = str(channel_or_thread.id)

    # Check if it's a channel or thread
    if category_id in existing_data:
        if channel_id in existing_data[category_id]["channels"]:
            # It's a channel
            always_on = always_on_value is True  # Ensure only True/False values are considered
            existing_data[category_id]["channels"][channel_id]["always_on"] = always_on
            
            # Update runtime dictionary
            always_on_channels[channel_or_thread.id] = always_on
            if not always_on:
                always_on_channels.pop(channel_or_thread.id, None)

            # Log the state before saving
            logging.info(f"Setting channel {channel_id} always on: {always_on}")
            
            # Save changes to JSON
            save_thread_data(existing_data)

            # Send confirmation message
            status_message = "now always listening to all messages." if always_on else "now only responding when mentioned."
            await channel_or_thread.send(f"AI assistant is {status_message}")
            logging.info(f"Channel {channel_or_thread.id} set to always on: {always_on}. Current always_on_channels: {always_on_channels}")

        elif str(channel_or_thread.parent.id) in existing_data[category_id]["channels"]:
            # It's a thread
            parent_channel_id = str(channel_or_thread.parent.id)
            always_on = always_on_value is True

            if parent_channel_id in existing_data[category_id]["channels"]:
                # Check if the thread already exists
                if str(channel_or_thread.id) in existing_data[category_id]["channels"][parent_channel_id]["threads"]:
                    # Update only the always_on property
                    existing_data[category_id]["channels"][parent_channel_id]["threads"][str(channel_or_thread.id)]["always_on"] = always_on
                else:
                    # If the thread does not exist, create it with the always_on value
                    existing_data[category_id]["channels"][parent_channel_id]["threads"][str(channel_or_thread.id)] = {
                        "always_on": always_on  # Add the always_on attribute for the thread
                    }

                # Update runtime dictionary
                always_on_channels[channel_or_thread.id] = always_on
                if not always_on:
                    always_on_channels.pop(channel_or_thread.id, None)

                # Log the state before saving
                logging.info(f"Setting thread {channel_or_thread.id} always on: {always_on}")
                
                # Save changes to JSON
                save_thread_data(existing_data)

                # Send confirmation message
                status_message = "now always listening to all messages." if always_on else "now only responding when mentioned."
                await channel_or_thread.send(f"AI assistant is {status_message}")
                logging.info(f"Thread {channel_or_thread.id} set to always on: {always_on}. Current always_on_channels: {always_on_channels}")
            else:
                logging.error(f"Parent channel {parent_channel_id} not found in thread data.")
        else:
            logging.error(f"Channel/Thread {channel_or_thread.id} not found in thread data.")
    else:
        logging.error(f"Category {category_id} not found in thread data.")

# Function to check if a channel or thread has always_on set to true
async def check_always_on(channel_id, category_id, thread_id):
    # Load the data for the category
    category_threads = load_thread_data()

    # Check if the channel exists in the category
    channel_data = category_threads.get(str(category_id), {}).get('channels', {}).get(str(channel_id))
    if channel_data and channel_data.get('always_on'):
        return True  # Always on for the channel

    # Check if the thread exists and has always_on set to true
    if thread_id:
        thread_data = channel_data.get('threads', {}).get(str(thread_id))
        if thread_data and thread_data.get('always_on'):
            return True  # Always on for the thread

    return False  # Default to False if neither is set to true

async def send_response_in_chunks(channel, response):
    if response is None:
        logging.error("Received None as response.")
        return  # Early return if response is None
    if len(response) > 2000:
        for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
            await channel.send(chunk)
    else:
        await channel.send(response)

async def send_response(interaction, response, channel_id=None, thread_id=None, backup_channel_name=None):
    # Initialize target and backup channels
    target_channel = None
    backup_channel = None
    
    # Check for a specific channel
    if channel_id:
        target_channel = client.get_channel(channel_id)
        if not target_channel:
            logging.error(f"Channel with ID {channel_id} not found.")
            await interaction.followup.send(f"Error: Channel with ID {channel_id} not found.")
            return
    else:
        # No specific channel provided, find the backup channel in the same category
        category = interaction.channel.category
        if category:
            for ch in category.text_channels:
                if ch.name == backup_channel_name:
                    backup_channel = ch
                    break
        target_channel = backup_channel or interaction.channel  # Use backup or default to interaction's channel

    # Set target channel to a thread if a thread ID is specified
    if thread_id:
        thread = client.get_channel(thread_id)
        if thread is None:
            logging.error(f"Thread with ID {thread_id} not found.")
            await interaction.followup.send(f"Error: Thread with ID {thread_id} not found.")
            return
        target_channel = thread  # Directly use the thread as the target
    
    # Log an error and return if no target channel found
    if not target_channel:
        logging.error("Target channel could not be determined.")
        await interaction.followup.send("Error: Could not determine target channel.")
        return
    
    # Send response, handling length constraints
    if response:
        if len(response) > 2000:
            for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
                await target_channel.send(chunk)
        else:
            await target_channel.send(response)
    else:
        logging.error("Received None as response.")
        return

    # Send follow-up to inform the original channel about the response location
    location_msg = f"Response sent to <#{target_channel.id}>."
    await interaction.followup.send(location_msg)
