
import aiohttp
import logging
from config import client
from assistant_interactions import get_assistant_response
from shared_functions import always_on_channels
import PyPDF2
import io
from docx import Document
from shared_functions import send_response_in_chunks

# Configure logging
logging.basicConfig(level=logging.INFO)

@client.event
async def on_message(message):
    logging.info(f"Received message from {message.author}")

    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    user_message = message.content.strip() if message.content else "No message provided."
    channel_name = message.channel.name

    # Check if the channel is in the always_on_channels
    if message.channel.id in always_on_channels and always_on_channels[message.channel.id]:
        # If the channel is always on, respond to every message
        await send_assistant_response(user_message, message.channel)
        return  # Exit after responding

    # Automatically respond to messages in the #telldm channel
    if channel_name == "telldm":
        await send_assistant_response(user_message, message.channel)
        return  # Exit after responding

    # Check for attachments in other channels
    if message.attachments:
        for attachment in message.attachments:
            logging.info(f"Found attachment: {attachment.filename} with URL: {attachment.url}")
            await handle_attachments(attachment, user_message, message.channel)

    # Respond to mentions in other channels
    if client.user in message.mentions:
        cleaned_message = message.content.replace(f'<@{client.user.id}>', '').strip()
        await send_assistant_response(cleaned_message, message.channel)

async def handle_attachments(attachment, user_message, channel):
    """Handle image, PDF, and text file attachments from the message."""
    logging.info(f"Processing attachment: {attachment.filename}")
    file_url = attachment.url

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            if resp.status == 200:
                logging.info(f"Successfully retrieved attachment: {attachment.filename}")
                content_type = attachment.content_type  # Get content type to differentiate files
                logging.info(f"Attachment content type: {content_type}")  # Log the content type

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
                    combined_message = f"{user_message}\n\nExtracted text from PDF:\n{text}"
                    gpt_request_content = [
                        {"type": "text", "text": combined_message}
                    ]
                    await send_assistant_response(gpt_request_content, channel)

                # Update the condition to handle text files with different content types
                elif "text/plain" in content_type:  # Check if "text/plain" is part of content type
                    file_data = await resp.read()  # Read the file data
                    file_content = file_data.decode("utf-8")  # Decode bytes to string
                    combined_message = f"{user_message}\n\nExtracted text:\n{file_content}"
                    gpt_request_content = [
                        {"type": "text", "text": combined_message}
                    ]
                    await send_assistant_response(gpt_request_content, channel)

                else:
                    logging.error(f"Unsupported file type: {content_type}")

            else:
                logging.error(f"Failed to retrieve attachment: {attachment.filename}, Status: {resp.status}")

def extract_text_from_pdf(pdf_data):
    """Extract text from a PDF file."""
    text = ""
    with io.BytesIO(pdf_data) as pdf_file:
        reader = PyPDF2.PdfReader(pdf_file)
        for page in reader.pages:
            text += page.extract_text() or ""
    return text

async def extract_text_from_file(file_url, content_type):
    """Extract text based on file type."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if content_type == "text/plain" or file_url.endswith('.txt'):
                    return await resp.text()  # Directly return the text for .txt files

                elif "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type:
                    # For .docx files
                    docx_data = await resp.read()
                    return extract_text_from_docx(docx_data)

                elif "application/msword" in content_type:
                    # For .doc files (you can implement extraction logic here as needed)
                    raise NotImplementedError("Extraction from .doc files is not implemented.")
                
                else:
                    raise ValueError("Unsupported file format.")
    except Exception as e:
        logging.error(f"Error extracting text from file: {e}")


def extract_text_from_docx(docx_data):
    """Extract text from a DOCX file."""
    text = ""
    with io.BytesIO(docx_data) as docx_file:
        doc = Document(docx_file)
        for para in doc.paragraphs:
            text += para.text + "\n"
    return text

async def send_assistant_response(gpt_request_content, channel):
    async with channel.typing():
        logging.info("Assistant is typing...")
        response = await get_assistant_response(gpt_request_content, channel.id)
        await send_response_in_chunks(channel, response)

