import aiohttp
import logging
from config import client
from assistant_interactions import get_assistant_response
import PyPDF2
import io

# Configure logging
logging.basicConfig(level=logging.INFO)

@client.event
async def on_message(message):
    logging.info(f"Received message from {message.author}")

    if message.author == client.user:
        return

    user_message = message.content.strip() if message.content else "No message provided."

    # Check for attachments
    if message.attachments:
        for attachment in message.attachments:
            logging.info(f"Found attachment: {attachment.filename} with URL: {attachment.url}")
            await handle_attachments(attachment, user_message, message.channel)

    # Respond to mentions
    if client.user in message.mentions:
        cleaned_message = message.content.replace(f'<@{client.user.id}>', '').strip()
        await send_assistant_response(cleaned_message, message.channel)


async def handle_attachments(attachment, user_message, channel):
    """Handle image and PDF attachments from the message."""
    logging.info(f"Processing attachment: {attachment.filename}")
    file_url = attachment.url

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            if resp.status == 200:
                logging.info(f"Successfully retrieved attachment: {attachment.filename}")
                content_type = attachment.content_type  # Get content type to differentiate files

                if "image" in content_type:
                    # Process image files
                    image_data = await resp.read()
                    gpt_request_content = [
                        {"type": "text", "text": user_message},
                        {"type": "image_url", "image_url": {"url": file_url, "detail": "high"}},
                    ]
                    await send_assistant_response(gpt_request_content, channel)

                elif "pdf" in content_type:
                    # Process PDF files
                    pdf_data = await resp.read()
                    text = extract_text_from_pdf(pdf_data)
                    combined_message = f"{user_message}\n\nExtracted text from PDF:\n{text}"  # Combine user message and PDF text
                    gpt_request_content = [
                        {"type": "text", "text": combined_message}  # Send as a single text message
                    ]
                    await send_assistant_response(gpt_request_content, channel)

            else:
                logging.error(f"Failed to retrieve attachment: {attachment.filename}, Status: {resp.status}")

def extract_text_from_pdf(pdf_data):
    """Extract text from a PDF file."""
    text = ""
    with io.BytesIO(pdf_data) as pdf_file:
        reader = PyPDF2.PdfReader(pdf_file)
        for page in reader.pages:
            text += page.extract_text() or ""  # Extract text from each page
    return text

async def send_assistant_response(gpt_request_content, channel):
    async with channel.typing():  # Show typing indicator
        logging.info("Assistant is typing...")
        response = await get_assistant_response(gpt_request_content, channel.id)
        await send_response_in_chunks(channel, response)

async def send_response_in_chunks(channel, response):
    if len(response) > 2000:
        for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
            await channel.send(chunk)
    else:
        await channel.send(response)

