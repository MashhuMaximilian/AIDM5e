import logging


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
