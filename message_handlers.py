# message_handlers.py

import aiohttp
import logging
from datetime import datetime
from config import client, HEADERS, category_threads, category_conversations
from assistant_interactions import get_assistant_response
import base64
import imghdr

async def encode_image(image_data):
    # Determine the image type from the data
    image_type = imghdr.what(None, image_data)
    
    # Base64 encode for various supported types
    if image_type == 'jpeg':
        return f"data:image/jpeg;base64,{base64.b64encode(image_data).decode('utf-8')}"
    elif image_type == 'png':
        return f"data:image/png;base64,{base64.b64encode(image_data).decode('utf-8')}"
    elif image_type == 'webp':
        return f"data:image/webp;base64,{base64.b64encode(image_data).decode('utf-8')}"
    else:
        raise ValueError(f"Unsupported image type: {image_type}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    channel_id = message.channel.id
    category_id = message.channel.category_id
    user_message = message.content.strip() if message.content else "No message provided."

    if message.attachments:
        for attachment in message.attachments:
            file_url = attachment.url
            logging.info(f"File '{attachment.filename}' retrieved with URL: {file_url}")

            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()  # Read the image data
                        # No need to encode if you’re using the URL directly
                        gpt_request_content = [
                            {"type": "text", "text": user_message},
                            {"type": "image_url", "image_url": {"url": file_url, "detail": "high"}},
                        ]
                    async with message.channel.typing():
                        response = await get_assistant_response(gpt_request_content, channel_id, category_id)

                        # Ensure the response does not exceed Discord's limit
                        await send_response_in_chunks(message.channel, response)


    # Respond to mentions
    if client.user in message.mentions:
        cleaned_message = message.content.replace(f'<@{client.user.id}>', '').strip()

        async with message.channel.typing():
            response = await get_assistant_response(cleaned_message, channel_id, category_id)
            await send_response_in_chunks(message.channel, response)



async def send_response_in_chunks(channel, response):
    # Helper function to send long responses in chunks
    if len(response) > 2000:
        for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
            await channel.send(chunk)
    else:
        await channel.send(response)
