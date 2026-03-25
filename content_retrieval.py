import io
import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import discord
import PyPDF2
from docx import Document


logger = logging.getLogger(__name__)

MAX_FETCHED_TEXT_CHARS = 40000
MAX_FETCHED_BINARY_BYTES = 15 * 1024 * 1024
GOOGLE_DOC_RE = re.compile(r"https?://docs\.google\.com/document/(?:u/\d+/)?d/([a-zA-Z0-9_-]+)")
NOTION_URL_RE = re.compile(r"https?://(?:www\.)?(?:notion\.so|notion\.site)/", re.IGNORECASE)
NOTION_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>\s*(\{.*?\})\s*</script>',
    re.DOTALL | re.IGNORECASE,
)
NOTION_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL | re.IGNORECASE)
NOTION_META_DESC_RE = re.compile(
    r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
    re.IGNORECASE,
)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def extract_text_from_pdf_bytes(pdf_data: bytes) -> str:
    text = ""
    with io.BytesIO(pdf_data) as pdf_file:
        reader = PyPDF2.PdfReader(pdf_file)
        for page in reader.pages:
            text += page.extract_text() or ""
    return text


def extract_text_from_docx_bytes(docx_data: bytes) -> str:
    text = ""
    with io.BytesIO(docx_data) as docx_file:
        doc = Document(docx_file)
        for para in doc.paragraphs:
            if para.text:
                text += para.text + "\n"
    return text


def extract_text_from_html(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


def extract_text_from_local_file(path: str) -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    payload = file_path.read_bytes()

    if suffix == ".pdf":
        text = extract_text_from_pdf_bytes(payload)
    elif suffix in {".txt", ".md"}:
        text = payload.decode("utf-8", errors="replace")
    elif suffix == ".docx":
        text = extract_text_from_docx_bytes(payload)
    elif suffix in {".html", ".htm"}:
        text = extract_text_from_html(payload.decode("utf-8", errors="replace"))
    else:
        raise ValueError(f"Unsupported local file type for {file_path.name}.")

    return _truncate_text(text)


def _truncate_text(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_FETCHED_TEXT_CHARS:
        return text
    return text[:MAX_FETCHED_TEXT_CHARS] + "\n...[truncated]..."


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _looks_like_notion_url(url: str) -> bool:
    return bool(NOTION_URL_RE.match(url or ""))


async def _read_http_bytes(url: str) -> tuple[bytes, str | None]:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise ValueError(f"Failed to fetch {url} (HTTP {resp.status}).")
            content_type = resp.headers.get("Content-Type")
            payload = await resp.read()
            if len(payload) > MAX_FETCHED_BINARY_BYTES:
                raise ValueError(f"Fetched content from {url} is too large to process safely.")
            return payload, content_type


def _collect_notion_strings(node, out: list[str]) -> None:  # noqa: ANN001
    if isinstance(node, str):
        text = _collapse_whitespace(node)
        if (
            len(text) >= 3
            and not text.startswith("http")
            and text not in {"en", "block", "page", "text", "notion"}
        ):
            out.append(text)
        return
    if isinstance(node, list):
        for item in node:
            _collect_notion_strings(item, out)
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in {
                "id",
                "version",
                "spaceid",
                "userid",
                "file_ids",
                "permissions",
                "icon",
                "cover",
                "created_time",
                "last_edited_time",
                "signedurl",
                "copyspaceid",
                "copysourceurl",
                "copysourceworkspaceid",
            }:
                continue
            _collect_notion_strings(value, out)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _extract_notion_text_from_next_data(html: str) -> str:
    match = NOTION_NEXT_DATA_RE.search(html or "")
    if not match:
        return ""
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return ""
    strings: list[str] = []
    _collect_notion_strings(data, strings)
    filtered: list[str] = []
    for value in _dedupe_preserve_order(strings):
        lowered = value.lower()
        if lowered in {"notion", "made with notion", "the page you are looking for cannot be found"}:
            continue
        if len(value) == 32 and re.fullmatch(r"[a-f0-9-]+", value, re.IGNORECASE):
            continue
        filtered.append(value)
    return _truncate_text("\n".join(filtered))


def _extract_notion_text_from_html(html: str) -> str:
    parts: list[str] = []
    title_match = NOTION_TITLE_RE.search(html or "")
    if title_match:
        title = _collapse_whitespace(title_match.group(1).replace(" | Notion", ""))
        if title:
            parts.append(title)
    meta_match = NOTION_META_DESC_RE.search(html or "")
    if meta_match:
        description = _collapse_whitespace(meta_match.group(1))
        if description and description not in parts:
            parts.append(description)
    page_text = extract_text_from_html(html or "")
    cleaned_lines: list[str] = []
    for raw in page_text.splitlines():
        line = _collapse_whitespace(raw)
        lowered = line.lower()
        if not line:
            continue
        if lowered in {
            "made with notion",
            "duplicate",
            "search",
            "backlinks",
            "comments",
            "add a comment",
            "notion",
        }:
            continue
        cleaned_lines.append(line)
    for value in _dedupe_preserve_order(cleaned_lines):
        if value not in parts:
            parts.append(value)
    return _truncate_text("\n".join(parts))


async def extract_notion_url_text(url: str) -> str:
    payload, _ = await _read_http_bytes(url)
    html = payload.decode("utf-8", errors="replace")
    notion_json_text = _extract_notion_text_from_next_data(html)
    if notion_json_text:
        return notion_json_text
    notion_html_text = _extract_notion_text_from_html(html)
    if notion_html_text:
        return notion_html_text
    raise ValueError(f"No readable Notion text could be extracted from {url}.")


async def extract_attachment_text(attachment: discord.Attachment) -> str:
    payload, content_type = await _read_http_bytes(attachment.url)
    content_type = (content_type or attachment.content_type or "").lower()
    filename = attachment.filename.lower()

    if "pdf" in content_type or filename.endswith(".pdf"):
        text = extract_text_from_pdf_bytes(payload)
    elif "text/plain" in content_type or filename.endswith((".txt", ".md")):
        text = payload.decode("utf-8", errors="replace")
    elif (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type
        or filename.endswith(".docx")
    ):
        text = extract_text_from_docx_bytes(payload)
    elif "text/html" in content_type or filename.endswith((".html", ".htm")):
        text = extract_text_from_html(payload.decode("utf-8", errors="replace"))
    else:
        raise ValueError(f"Unsupported attachment type for {attachment.filename}.")

    return _truncate_text(text)


async def extract_public_url_text(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are supported.")

    if _looks_like_notion_url(url):
        return await extract_notion_url_text(url)

    google_doc_match = GOOGLE_DOC_RE.match(url)
    if google_doc_match:
        document_id = google_doc_match.group(1)
        export_url = f"https://docs.google.com/document/d/{document_id}/export?format=txt"
        payload, content_type = await _read_http_bytes(export_url)
        text = payload.decode("utf-8", errors="replace")
        text = _truncate_text(text)
        if text:
            return text

    payload, content_type = await _read_http_bytes(url)
    content_type = (content_type or "").lower()
    lower_url = url.lower()

    if "pdf" in content_type or lower_url.endswith(".pdf"):
        text = extract_text_from_pdf_bytes(payload)
    elif "text/plain" in content_type or lower_url.endswith((".txt", ".md")):
        text = payload.decode("utf-8", errors="replace")
    else:
        text = extract_text_from_html(payload.decode("utf-8", errors="replace"))

    text = _truncate_text(text)
    if not text:
        raise ValueError(f"No readable text could be extracted from {url}.")
    return text


def format_message_text(message: discord.Message) -> str:
    body = message.content.strip() if message.content else "[No message text]"
    return f"{message.author.display_name}: {body}"


async def format_message_with_attachments(message: discord.Message) -> str:
    parts = [format_message_text(message)]
    if not message.attachments:
        return "\n".join(parts)

    for attachment in message.attachments:
        try:
            extracted = await extract_attachment_text(attachment)
            parts.append(
                f"[Attachment: {attachment.filename}]\n{extracted}"
            )
        except Exception as exc:
            logger.warning("Failed to extract attachment %s from message %s: %s", attachment.filename, message.id, exc)
            parts.append(
                f"[Attachment present but unreadable: {attachment.filename}. Reason: {exc}]"
            )

    return "\n\n".join(parts)


async def select_messages(
    channel: discord.abc.Messageable,
    start: str | None = None,
    end: str | None = None,
    message_ids: str | None = None,
    last_n: int | None = None,
):
    messages: list[discord.Message] = []

    if message_ids is not None:
        message_ids_list = message_ids.split(",")
        for message_id in message_ids_list:
            try:
                message = await channel.fetch_message(int(message_id.strip()))
                messages.append(message)
            except (ValueError, discord.errors.NotFound):
                return None, f"Message ID {message_id.strip()} not found."
        return messages, {"type": "messages"}

    if start is not None and end is not None:
        try:
            start_id = int(start)
            end_id = int(end)
            start_message = await channel.fetch_message(start_id)
            end_message = await channel.fetch_message(end_id)
        except (ValueError, discord.errors.NotFound):
            return None, "Invalid message ID format or message not found."

        history_messages = []
        async for message in channel.history(after=start_message.created_at, before=end_message.created_at):
            history_messages.append(message)

        history_messages.reverse()
        messages = [start_message] + history_messages
        if start_id != end_id:
            messages.append(end_message)

        if not messages:
            return None, "No messages found between the specified messages."
        return messages, {"type": "between", "start_index": 0, "end_index": len(messages)}

    if start is not None:
        try:
            start_id = int(start)
            start_message = await channel.fetch_message(start_id)
        except (ValueError, discord.errors.NotFound):
            return None, "Invalid start message ID format or message not found."

        history_messages = []
        async for message in channel.history(after=start_message.created_at, limit=100):
            history_messages.append(message)
        history_messages.reverse()
        messages = [start_message] + history_messages

        if not messages:
            return None, "No messages found after the specified message."
        return messages, {"type": "from", "start_index": 0}

    if last_n is not None:
        try:
            last_n = int(last_n)
        except ValueError:
            return None, "Invalid value for 'last_n'. It must be an integer."

        async for message in channel.history(limit=last_n):
            messages.append(message)
        messages.reverse()

        if not messages:
            return None, "No messages found for the last 'n' messages."
        return messages, {"type": "last_n", "last_n": last_n}

    return None, "You must provide at least one of the options."
