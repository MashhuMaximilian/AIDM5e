import asyncio
import aiohttp
import discord
import logging
import re
from pathlib import Path
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
    build_card_creation_prompt,
    build_card_update_prompt,
    discover_workspace_card_messages,
    parse_card_update_response,
    parse_workspace_metadata,
    parse_workspace_thread,
    sync_workspace_cards,
)
from .shared_functions import check_always_on, send_response_in_chunks

# Configure logging
logging.basicConfig(level=logging.INFO)

URL_RE = re.compile(r"https?://\S+")
PLAYER_ROW_RE = re.compile(r"PLAYER\.*:\s*([^\n`]+)", re.IGNORECASE)


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


async def _start_thinking_indicator(message: discord.Message) -> discord.Message | None:
    try:
        return await message.channel.send("*AIDM is thinking...*")
    except discord.HTTPException:
        return None


async def _stop_thinking_indicator(indicator_message: discord.Message | None) -> None:
    if indicator_message is None:
        return
    try:
        await indicator_message.delete()
    except discord.HTTPException:
        pass


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


def _is_workspace_card_action_request(text: str | None) -> bool:
    content = (text or "").lower().strip()
    if not content:
        return False
    action_words = ("update", "change", "add", "edit", "create", "make")
    card_words = ("card", "cards")
    return any(word in content for word in action_words) and any(word in content for word in card_words)


def _is_new_card_request(text: str | None) -> bool:
    content = (text or "").lower()
    return (
        "new card" in content
        or "separate card" in content
        or "create a card" in content
        or "create new card" in content
        or "make a card" in content
    )


def _card_aliases(title: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9& ]+", " ", title.lower()).strip()
    aliases = {cleaned, cleaned.replace("&", "and").strip()}
    parts = [part.strip() for part in cleaned.split(":", 1)]
    if len(parts) == 2:
        prefix, remainder = parts
        if remainder:
            aliases.add(remainder)
            aliases.add(remainder.replace("&", "and").strip())
        if prefix:
            aliases.add(prefix)
    if cleaned.endswith(" card"):
        aliases.add(cleaned[:-5].strip())
    if title == "Character Card":
        aliases.update({"character", "summary"})
    if title == "Skills & Actions":
        aliases.update({"skills", "actions"})
    if title == "Reference Links":
        aliases.update({"links", "reference links"})
    return {alias for alias in aliases if alias}


def _normalize_match_text(text: str | None) -> str:
    return re.sub(r"[^a-z0-9& ]+", " ", (text or "").lower()).strip()


def _tokenize_match_text(text: str | None) -> set[str]:
    normalized = _normalize_match_text(text).replace("&", "and")
    return {token for token in normalized.split() if token}


def _target_card_titles(message_text: str, card_titles: list[str]) -> list[str]:
    normalized_message = _normalize_match_text(message_text)
    lowered = f" {normalized_message} "
    message_tokens = _tokenize_match_text(message_text)
    matched: list[str] = []
    scored_matches: list[tuple[int, str]] = []
    for title in card_titles:
        aliases = _card_aliases(title)
        for alias in _card_aliases(title):
            if f" {alias} " in lowered:
                matched.append(title)
                break
        if title in matched:
            continue

        title_tokens = _tokenize_match_text(title)
        alias_tokens = [_tokenize_match_text(alias) for alias in aliases]
        candidate_token_sets = [tokens for tokens in [title_tokens, *alias_tokens] if tokens]

        best_score = 0
        for token_set in candidate_token_sets:
            overlap = len(token_set & message_tokens)
            if overlap >= max(1, len(token_set) - 1):
                best_score = max(best_score, overlap)
        if best_score:
            scored_matches.append((best_score, title))
    if matched:
        return matched
    if any(token in lowered for token in (" all cards ", " all card ", " update all cards ", " change all cards ", " edit all cards ")):
        return list(card_titles)

    if scored_matches:
        scored_matches.sort(key=lambda item: (-item[0], len(item[1])))
        top_score = scored_matches[0][0]
        top_titles = [title for score, title in scored_matches if score == top_score]
        if len(top_titles) == 1:
            return top_titles
    return []


async def _fetch_attachment_context(attachments: list[discord.Attachment]) -> str:
    blocks: list[str] = []
    for attachment in attachments:
        label = attachment.filename
        content_type = attachment.content_type or ""
        suffix = Path(attachment.filename).suffix.lower()
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
            if "image" in content_type or suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
                blocks.append(f"[Attached image: {attachment.url}]")
            elif "pdf" in content_type or suffix == ".pdf":
                blocks.append(f"[Attached PDF: {label}]\n{extract_text_from_pdf(file_data)}")
            elif "text/plain" in content_type or suffix in {".txt", ".md"}:
                blocks.append(f"[Attached text file: {label}]\n{file_data.decode('utf-8', errors='ignore')}")
            elif "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type or suffix == ".docx":
                blocks.append(f"[Attached DOCX: {label}]\n{extract_text_from_docx(file_data)}")
        except Exception as exc:
            logging.warning("Failed to extract attachment context from %s: %s", label, exc)
    return "\n\n".join(block for block in blocks if block.strip()).strip()


async def _collect_recent_workspace_context(message: discord.Message, *, limit: int = 6) -> str:
    note_lines: list[str] = []
    urls: list[str] = []
    attachments: list[discord.Attachment] = []

    async for prior_message in message.channel.history(limit=limit, before=message, oldest_first=True):
        if prior_message.author == client.user or prior_message.is_system():
            continue
        content = (prior_message.content or "").strip()
        if content:
            note_lines.append(f"{prior_message.author.display_name}: {content}")
            urls.extend(_extract_urls(content))
        if prior_message.attachments:
            attachments.extend(list(prior_message.attachments))

    deduped_urls = list(dict.fromkeys(urls))
    blocks: list[str] = []
    if note_lines:
        blocks.append("[Recent Workspace Notes]\n" + "\n".join(note_lines[-limit:]))
    if deduped_urls:
        recent_url_context = await _fetch_url_context(deduped_urls)
        if recent_url_context:
            blocks.append("[Recent Workspace URLs]\n" + recent_url_context)
    if attachments:
        recent_attachment_context = await _fetch_attachment_context(attachments[:4])
        if recent_attachment_context:
            blocks.append("[Recent Workspace Attachments]\n" + recent_attachment_context)
    return "\n\n".join(block for block in blocks if block.strip()).strip()


def _extract_player_name_from_workspace_cards(card_messages: dict[str, discord.Message]) -> str | None:
    for title in ("Profile Card", "Character Card"):
        card_message = card_messages.get(title)
        if card_message is None:
            continue
        body = card_message.embeds[0].description if card_message.embeds else (card_message.content or "")
        if not body:
            continue
        match = PLAYER_ROW_RE.search(body)
        if not match:
            continue
        candidate = match.group(1).strip()
        if candidate and candidate.lower() not in {"unknown", "needs review."}:
            return candidate
    return None


async def _workspace_system_prompt(thread: discord.Thread, card_messages: dict[str, discord.Message]) -> str | None:
    kind, entity_name = parse_workspace_thread(thread.name)
    if kind is None or not entity_name:
        return None
    if kind == "player":
        return build_player_workspace_system_prompt(entity_name, _extract_player_name_from_workspace_cards(card_messages))
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

    target_titles = _target_card_titles(message.content, list(card_messages.keys()))
    needs_assistant = _is_workspace_card_action_request(message.content) or _has_clear_question(message.content)
    indicator_message = await _start_thinking_indicator(message) if needs_assistant else None
    try:
        assigned_memory = await get_assigned_memory(channel_id, category_id, thread_id)
        if not assigned_memory:
            return False

        urls = _extract_urls(message.content)
        url_context = await _fetch_url_context(urls) if urls else ""
        attachment_context = await _fetch_attachment_context(list(message.attachments)) if message.attachments else ""
        extra_context = "\n\n".join(block for block in [url_context, attachment_context] if block).strip()
        recent_context = await _collect_recent_workspace_context(message)

        if _is_workspace_card_action_request(message.content):
            card_bodies = {
                title: (card_message.embeds[0].description if card_message.embeds else card_message.content or "")
                for title, card_message in card_messages.items()
            }
            prompt_text = build_card_creation_prompt(
                request_text=message.content,
                card_bodies=card_bodies,
            ) if _is_new_card_request(message.content) else build_card_update_prompt(
                request_text=message.content,
                card_bodies=card_bodies,
                target_titles=target_titles,
            )
            response = await get_assistant_response(
                prompt_text,
                channel_id,
                category_id,
                thread_id,
                assigned_memory,
                context_block="\n\n".join(block for block in [recent_context, extra_context] if block).strip() or None,
                system_prompt=system_prompt,
            )
            updates = parse_card_update_response(response)
            if not updates:
                await send_response_in_chunks(
                    message.channel,
                    "I could not turn that into card changes yet. Please mention which card to update, or say `create a new card for ...`."
                )
                return True
            if not _is_new_card_request(message.content) and not target_titles and len(updates) > 1:
                await send_response_in_chunks(
                    message.channel,
                    "I need a more specific target card for that update. Please name the card, or say `update all cards`."
                )
                return True
            merged_cards = dict(card_bodies)
            merged_cards.update(updates)
            resolved_messages = await sync_workspace_cards(message.channel, merged_cards)
            changed_titles = [title for title in updates.keys() if title in resolved_messages]
            if changed_titles:
                await send_response_in_chunks(message.channel, f"Updated: {', '.join(changed_titles)}.")
            return True

        if _has_clear_question(message.content):
            card_context = "\n\n".join(
                f"[{title}]\n{(card_message.embeds[0].description if card_message.embeds else card_message.content or '').strip()}"
                for title, card_message in card_messages.items()
            )
            context_block = "\n\n".join(block for block in [card_context, recent_context, extra_context] if block).strip() or None
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
            acknowledgment = (
                "I received the new source material for this workspace. "
                "Tell me `update the cards` when you want me to apply it."
            )
            if not (extra_context or recent_context):
                acknowledgment = (
                    "I received the source material, but I could not read it cleanly. "
                    "If it is a Google Doc, make sure public access is enabled, or attach/export a PDF."
                )
            await send_response_in_chunks(message.channel, acknowledgment)
            return True
        return False
    finally:
        await _stop_thinking_indicator(indicator_message)

@client.event
async def on_message(message):
    if message.author == client.user or message.is_system():
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
    indicator_message = await _start_thinking_indicator(message) if should_respond else None

    try:
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
    finally:
        await _stop_thinking_indicator(indicator_message)


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
