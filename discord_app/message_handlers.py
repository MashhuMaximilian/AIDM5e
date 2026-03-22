import asyncio
import aiohttp
import discord
import logging
import re
from config import client
import PyPDF2
import io
from docx import Document

from ai_services.assistant_interactions import get_assistant_response
from ai_services.gemini_client import gemini_client
from content_retrieval import extract_public_url_text
from data_store.memory_management import get_assigned_memory
from discord_app.player_workspace.prompting import (
    build_npc_workspace_system_prompt,
    build_other_workspace_system_prompt,
    build_player_workspace_system_prompt,
)
from discord_app.workspace_threads import (
    build_card_update_prompt,
    discover_workspace_card_messages,
    parse_card_update_response,
    parse_workspace_metadata,
    parse_workspace_thread,
)
from .shared_functions import check_always_on, send_response_in_chunks

# Configure logging
logging.basicConfig(level=logging.INFO)

URL_RE = re.compile(r"https?://\S+")


def _extract_urls(text: str | None) -> list[str]:
    if not text:
        return []
    cleaned_urls: list[str] = []
    seen: set[str] = set()
    for match in URL_RE.findall(text):
        url = match.rstrip(".,);]>\"'")
        if url in seen:
            continue
        seen.add(url)
        cleaned_urls.append(url)
    return cleaned_urls


def _url_kind(url: str) -> str:
    lowered = url.lower()
    if "notion.so" in lowered or "notion.site" in lowered:
        return "Notion URL"
    if "drive.google.com" in lowered or "docs.google.com" in lowered:
        return "Google Drive URL"
    return "Public URL"


async def _fetch_url_context(urls: list[str]) -> str:
    blocks: list[str] = []
    for url in urls:
        label = _url_kind(url)
        try:
            extracted = await extract_public_url_text(url)
            blocks.append(f"[{label}: {url}]\n{extracted}")
            continue
        except Exception as exc:
            logging.warning("Direct URL fetch failed for %s, falling back to Gemini URL Context: %s", url, exc)

        try:
            fallback = await asyncio.to_thread(
                gemini_client.generate_text_with_url_context,
                "Read the provided public URL and extract the most relevant factual content in plain text for downstream assistant context. "
                "Focus on the actual linked document/page. Do not answer the user directly. Do not add commentary.",
                [url],
                None,
            )
            if fallback:
                blocks.append(f"[{label}: {url}]\n{fallback.strip()}")
                continue
        except Exception as exc:
            logging.warning("Gemini URL context fallback failed for %s: %s", url, exc)

        blocks.append(f"[{label} could not be fetched: {url}]")

    return "\n\n".join(block for block in blocks if block.strip()).strip()


def _is_workspace_thread(channel: discord.abc.Messageable) -> bool:
    return isinstance(channel, discord.Thread) and parse_workspace_thread(channel.name)[0] is not None


def _has_clear_question(text: str | None) -> bool:
    content = (text or "").strip().lower()
    if not content:
        return False
    if "?" in content:
        return True
    return content.startswith(("what ", "how ", "why ", "who ", "where ", "when ", "can you", "could you", "would you"))


def _is_explicit_edit_request(text: str | None) -> bool:
    content = (text or "").lower()
    return any(word in content for word in (" update ", " change ", " add ", " edit ")) or content.startswith(("update ", "change ", "add ", "edit "))


def _card_aliases(title: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9& ]+", " ", title.lower()).strip()
    aliases = {cleaned, cleaned.replace("&", "and").strip()}
    if cleaned.endswith(" card"):
        aliases.add(cleaned[:-5].strip())
    if title == "Character Card":
        aliases.update({"character", "summary"})
    if title == "Skills & Actions":
        aliases.update({"skills", "actions"})
    if title == "Reference Links":
        aliases.update({"links", "reference links"})
    return {alias for alias in aliases if alias}


def _target_card_titles(message_text: str, card_titles: list[str]) -> list[str]:
    lowered = f" {re.sub(r'[^a-z0-9& ]+', ' ', (message_text or '').lower())} "
    matched: list[str] = []
    for title in card_titles:
        for alias in _card_aliases(title):
            if f" {alias} " in lowered:
                matched.append(title)
                break
    return matched


async def _fetch_attachment_context(attachments: list[discord.Attachment]) -> str:
    blocks: list[str] = []
    for attachment in attachments:
        label = attachment.filename
        content_type = attachment.content_type or ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    if resp.status != 200:
                        blocks.append(f"[Attachment could not be fetched: {label}]")
                        continue
                    file_data = await resp.read()
        except Exception as exc:
            logging.warning("Failed to fetch attachment %s: %s", label, exc)
            blocks.append(f"[Attachment could not be fetched: {label}]")
            continue

        try:
            if "image" in content_type:
                blocks.append(f"[Attached image: {attachment.url}]")
            elif "pdf" in content_type:
                blocks.append(f"[Attached PDF: {label}]\n{extract_text_from_pdf(file_data)}")
            elif "text/plain" in content_type:
                blocks.append(f"[Attached text file: {label}]\n{file_data.decode('utf-8', errors='ignore')}")
            elif "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type:
                blocks.append(f"[Attached DOCX: {label}]\n{extract_text_from_docx(file_data)}")
        except Exception as exc:
            logging.warning("Failed to extract attachment context from %s: %s", label, exc)
    return "\n\n".join(block for block in blocks if block.strip()).strip()


async def _workspace_system_prompt(thread: discord.Thread, card_messages: dict[str, discord.Message]) -> str | None:
    kind, entity_name = parse_workspace_thread(thread.name)
    if kind is None or not entity_name:
        return None
    if kind == "player":
        return build_player_workspace_system_prompt(entity_name, None)
    if kind == "npc":
        return build_npc_workspace_system_prompt(entity_name)

    metadata = None
    async for thread_message in thread.history(limit=20, oldest_first=True):
        metadata = parse_workspace_metadata(thread_message.content)
        if metadata is not None:
            break
    card_inventory_text = metadata.card_inventory_text if metadata else "\n".join(f"- {title}: Needs review." for title in card_messages.keys())
    cascade_rules_text = metadata.cascade_rules_text if metadata else "- If a change affects multiple cards, update all affected cards."
    user_note = metadata.user_note if metadata else ""
    return build_other_workspace_system_prompt(entity_name, user_note, card_inventory_text, cascade_rules_text)


async def _handle_workspace_thread_message(message: discord.Message, channel_id: int, category_id: int | None, thread_id: int) -> bool:
    card_messages = await discover_workspace_card_messages(message.channel)
    if not card_messages:
        return False

    system_prompt = await _workspace_system_prompt(message.channel, card_messages)
    if not system_prompt:
        return False

    assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id)
    if not assigned_memory:
        return False

    urls = _extract_urls(message.content)
    url_context = await _fetch_url_context(urls) if urls else ""
    attachment_context = await _fetch_attachment_context(list(message.attachments)) if message.attachments else ""
    extra_context = "\n\n".join(block for block in [url_context, attachment_context] if block).strip()

    target_titles = _target_card_titles(message.content, list(card_messages.keys()))
    if _is_explicit_edit_request(message.content) and target_titles:
        card_bodies = {
            title: (card_message.embeds[0].description if card_message.embeds else card_message.content or "")
            for title, card_message in card_messages.items()
        }
        response = await get_assistant_response(
            build_card_update_prompt(
                request_text=message.content,
                card_bodies=card_bodies,
                target_titles=target_titles,
            ),
            channel_id,
            category_id,
            thread_id,
            assigned_memory,
            context_block=extra_context or None,
            system_prompt=system_prompt,
        )
        updates = parse_card_update_response(response)
        if not updates:
            return True
        changed_titles: list[str] = []
        for title, new_body in updates.items():
            target_message = card_messages.get(title)
            if target_message is None:
                continue
            embed = target_message.embeds[0].copy() if target_message.embeds else discord.Embed(title=title, color=discord.Color.dark_grey())
            embed.description = new_body
            await target_message.edit(embed=embed)
            changed_titles.append(title)
        if changed_titles:
            await send_response_in_chunks(message.channel, f"Updated: {', '.join(changed_titles)}.")
        return True

    if _has_clear_question(message.content):
        card_context = "\n\n".join(
            f"[{title}]\n{(card_message.embeds[0].description if card_message.embeds else card_message.content or '').strip()}"
            for title, card_message in card_messages.items()
        )
        context_block = "\n\n".join(block for block in [card_context, extra_context] if block).strip() or None
        response = await get_assistant_response(
            message.content,
            channel_id,
            category_id,
            thread_id,
            assigned_memory,
            context_block=context_block,
            system_prompt=system_prompt,
        )
        if response:
            await send_response_in_chunks(message.channel, response)
        return True

    if message.attachments or urls:
        return True
    return False

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    logging.info(f"Received message from {message.author}")

    user_message = f"{message.author.display_name} said: {message.content.strip()}" if message.content else "No message provided."
    logging.info(f"User message (first 100 characters): {user_message[:100]}")

    channel_name = message.channel.name
    channel_id = message.channel.id
    category = message.channel.category if hasattr(message.channel, "category") else None
    if isinstance(message.channel, discord.Thread):
        category = message.channel.parent.category if message.channel.parent else None
        channel_id = message.channel.parent.id if message.channel.parent else message.channel.id
        thread_id = message.channel.id
    else:
        thread_id = None
    category_id = category.id if category else None

    if thread_id is not None and _is_workspace_thread(message.channel):
        handled = await _handle_workspace_thread_message(message, channel_id, category_id, thread_id)
        if handled:
            return

    response_sent = False
    channel_always_on = await check_always_on(channel_id, category_id, thread_id)
    urls = _extract_urls(message.content)

    async def send_response(response):
        if response:
            await send_response_in_chunks(message.channel, response)
            return True
        return False

    should_respond = channel_always_on or channel_name == "telldm" or client.user in message.mentions or bool(urls)

    if should_respond:
        assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id)
        if assigned_memory:
            context_block = await _fetch_url_context(urls) if urls else None
            response = await get_assistant_response(
                user_message,
                channel_id,
                category_id,
                thread_id,
                assigned_memory,
                context_block=context_block,
            )
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
    channel = client.get_channel(thread_id or channel_id)

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            if resp.status == 200:
                logging.info(f"Successfully retrieved attachment: {attachment.filename}")
                content_type = attachment.content_type

                assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id)
                if not assigned_memory:
                    logging.error("Assigned memory ID is invalid or empty.")
                    return

                # IMAGE HANDLING
                if content_type and "image" in content_type:
                    combined_message = f"{user_message}\n\nThe user attached an image here: {file_url}"
                    response = await get_assistant_response(combined_message, channel_id, category_id, thread_id, assigned_memory)
                    if response:
                        await send_response_in_chunks(channel, response)

                # PDF HANDLING
                elif content_type and "pdf" in content_type:
                    pdf_data = await resp.read()
                    text = extract_text_from_pdf(pdf_data)
                    combined_message = f"{user_message}\n\nExtracted text from PDF:\n{text}"
                    response = await get_assistant_response(combined_message, channel_id, category_id, thread_id, assigned_memory)
                    if response:
                        await send_response_in_chunks(channel, response)

                # TXT / DOCX / DOC HANDLING
                elif content_type in [
                    "text/plain",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/msword"
                ]:
                    extracted_text = await extract_text_from_file(file_url, content_type)
                    combined_message = f"{user_message}\n\nExtracted text:\n{extracted_text}"
                    response = await get_assistant_response(combined_message, channel_id, category_id, thread_id, assigned_memory)
                    if response:
                        await send_response_in_chunks(channel, response)

                else:
                    logging.warning(f"Unsupported content type: {content_type}")

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
