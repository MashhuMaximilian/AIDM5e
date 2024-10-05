import aiohttp
import logging
from config import client
from assistant_interactions import get_assistant_response
import PyPDF2
import io
from docx import Document

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

                elif content_type in ["text/plain", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]:
                    # Process .txt, .docx, and .doc files
                    file_data = await resp.read()  # Read the file data
                    extracted_text = await extract_text_from_file(file_url, content_type)  # Call the unified extraction function
                    combined_message = f"{user_message}\n\nExtracted text:\n{extracted_text}"
                    gpt_request_content = [
                        {"type": "text", "text": combined_message}
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
            text += page.extract_text() or ""
    return text

async def extract_text_from_file(file_url, content_type):
    """Extract text based on file type."""
    if "text/plain" in content_type:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                return await resp.text()  # Directly return the text for .txt files

    elif "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type:
        # For .docx files
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                docx_data = await resp.read()
                return extract_text_from_docx(docx_data)

    elif "application/msword" in content_type:
        # For .doc files (you can implement extraction logic here as needed)
        raise NotImplementedError("Extraction from .doc files is not implemented.")
    else:
        raise ValueError("Unsupported file format.")

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

async def send_response_in_chunks(channel, response):
    if len(response) > 2000:
        for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
            await channel.send(chunk)
    else:
        await channel.send(response)
