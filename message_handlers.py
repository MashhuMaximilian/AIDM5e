# message_handlers.py

import aiohttp
import logging
from datetime import datetime
from config import client, HEADERS, category_threads, category_conversations
from assistant_interactions import get_assistant_response



@client.event
async def on_message(message):
    if message.author == client.user:
        return

    channel_id = message.channel.id
    category_id = message.channel.category_id
    user_message = message.content.strip() if message.content else "No message provided."

    # Process file attachments
    if message.attachments:
        for attachment in message.attachments:
            file_url = attachment.url
            logging.info(f"File '{attachment.filename}' retrieved with URL: {file_url}")

            async with aiohttp.ClientSession() as session:
                # Directly send the image file to the assistant
                response = await get_assistant_response(user_message, channel_id, category_id)
                await message.channel.send(f"Processed file '{attachment.filename}': {response}\nMessage: {user_message}")

    # Respond to mentions
    if client.user in message.mentions:
        cleaned_message = message.content.replace(f'<@{client.user.id}>', '').strip()

        async with message.channel.typing():
            response = await get_assistant_response(cleaned_message, channel_id, category_id)

            # Send the response back to the channel, handling message length
            await send_response_in_chunks(message.channel, response)

async def send_response_in_chunks(channel, response):
    # Helper function to send long responses in chunks
    if len(response) > 2000:
        for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
            await channel.send(chunk)
    else:
        await channel.send(response)
