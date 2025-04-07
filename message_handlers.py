import aiohttp
import logging
from config import client
from assistant_interactions import get_assistant_response
from memory_management import get_assigned_memory
from shared_functions import check_always_on, send_response_in_chunks
import PyPDF2
import io
from docx import Document

# Configure logging
logging.basicConfig(level=logging.INFO)

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    logging.info(f"Received message from {message.author}")

    user_message = f"{message.author.display_name} said: {message.content.strip()}" if message.content else "No message provided."
    logging.info(f"User message (first 100 characters): {user_message[:100]}")

    channel_name = message.channel.name
    channel_id = message.channel.id
    category_id = message.channel.category.id if message.channel.category else None
    thread_id = message.thread.id if hasattr(message, 'thread') and message.thread else None

    response_sent = False
    channel_always_on = await check_always_on(channel_id, category_id, thread_id)

    async def send_response(response):
        if response:
            await send_response_in_chunks(message.channel, response)
            return True
        return False

    if channel_always_on:
        assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id)
        if assigned_memory:
            response = await get_assistant_response(user_message, channel_id, category_id, thread_id, assigned_memory)
            response_sent = await send_response(response)
        else:
            logging.error("Assigned memory ID is invalid or empty.")

    if channel_name == "telldm" and not response_sent:
        assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id)
        if assigned_memory:
            response = await get_assistant_response(user_message, channel_id, category_id, thread_id, assigned_memory)
            response_sent = await send_response(response)
        else:
            logging.error("Assigned memory ID is invalid or empty.")

    if client.user in message.mentions and not response_sent:
        assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id)
        if assigned_memory:
            response = await get_assistant_response(user_message, channel_id, category_id, thread_id, assigned_memory)
            response_sent = await send_response(response)
        else:
            logging.error("Assigned memory ID is invalid or empty.")

    if message.attachments and not response_sent:
        for attachment in message.attachments:
            logging.info(f"Found attachment: {attachment.filename} with URL: {attachment.url}")
            await handle_attachments(attachment, user_message, channel_id, category_id, thread_id)

async def handle_attachments(attachment, user_message, channel_id, category_id, thread_id):
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
                    assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id)
                    if assigned_memory:
                        await get_assistant_response(gpt_request_content, channel_id, category_id, thread_id, assigned_memory)
                    else:
                        logging.error("Assigned memory ID is invalid or empty.")

                elif "pdf" in content_type:
                    # Process PDF files
                    pdf_data = await resp.read()
                    text = extract_text_from_pdf(pdf_data)
                    combined_message = f"{user_message}\n\nExtracted text from PDF:\n{text}"
                    assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id)
                    if assigned_memory:
                        await get_assistant_response(combined_message, channel_id, category_id, thread_id, assigned_memory)
                    else:
                        logging.error("Assigned memory ID is invalid or empty.")

                elif content_type in ["text/plain", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]:
                    # Process .txt, .docx, and .doc files
                    extracted_text = await extract_text_from_file(file_url, content_type)
                    combined_message = f"{user_message}\n\nExtracted text:\n{extracted_text}"
                    assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id)
                    if assigned_memory:
                        await get_assistant_response(combined_message, channel_id, category_id, thread_id, assigned_memory)
                    else:
                        logging.error("Assigned memory ID is invalid or empty.")

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
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            file_data = await resp.read()
            
            if "text/plain" in content_type:
                return file_data.decode('utf-8')  # Directly return the text for .txt files

            elif "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type:
                return extract_text_from_docx(file_data)

            elif "application/msword" in content_type:
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

# async def send_response_in_chunks(channel, response):
#     """Send response in chunks if it exceeds Discord's message length limit."""
#     if len(response) > 2000:
#         for chunk in [response[i:i + 2000] for i in range(0, len(response), 2000)]:
#             await channel.send(chunk)
#     else:
#         await channel.send(response)
