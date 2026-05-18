"""Tests for message_tools module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from discord_app.message_tools import (
    parse_ai_tool_invocation,
    edit_message,
    reply_to_message,
    forward_message,
    get_message_content,
    execute_tool_invocations,
)


class TestParseAIToolInvocation:
    """Tests for parse_ai_tool_invocation function."""

    def test_parses_simple_invocation(self):
        text = "Some response text\n[AIDM-TOOL: edit_message | message_id=123456 | new_content=Hello world]\nMore text"
        result = parse_ai_tool_invocation(text)
        
        assert len(result) == 1
        assert result[0]["name"] == "edit_message"
        assert result[0]["args"]["message_id"] == "123456"
        assert result[0]["args"]["new_content"] == "Hello world"

    def test_parses_invocation_with_no_args(self):
        text = "[AIDM-TOOL: get_message_content | message_id=123456]"
        result = parse_ai_tool_invocation(text)
        
        assert len(result) == 1
        assert result[0]["name"] == "get_message_content"
        assert result[0]["args"]["message_id"] == "123456"

    def test_parses_multiple_invocations(self):
        text = "[AIDM-TOOL: edit_message | message_id=123][AIDM-TOOL: reply_to_message | message_id=456]"
        result = parse_ai_tool_invocation(text)
        
        assert len(result) == 2
        assert result[0]["name"] == "edit_message"
        assert result[1]["name"] == "reply_to_message"

    def test_parses_invocation_with_mention_option(self):
        text = "[AIDM-TOOL: reply_to_message | message_id=123 | content=Hello | mention=true]"
        result = parse_ai_tool_invocation(text)
        
        assert len(result) == 1
        assert result[0]["args"]["mention"] == "true"

    def test_returns_empty_list_for_no_invocations(self):
        text = "Just a normal response without any tools."
        result = parse_ai_tool_invocation(text)
        
        assert result == []

    def test_parses_case_insensitive(self):
        text = "[AIDM-TOOL: EDIT_MESSAGE | MESSAGE_ID=123]"
        result = parse_ai_tool_invocation(text)
        
        assert len(result) == 1
        assert result[0]["name"] == "edit_message"

    def test_includes_raw_text_and_positions(self):
        text = "Prefix [AIDM-TOOL: edit_message | message_id=123] suffix"
        result = parse_ai_tool_invocation(text)
        
        assert len(result) == 1
        assert result[0]["raw"] == "[AIDM-TOOL: edit_message | message_id=123]"
        assert result[0]["start"] == 7
        assert result[0]["end"] == 49


class TestEditMessage:
    """Tests for edit_message function."""

    @pytest.mark.asyncio
    async def test_edit_message_success(self):
        mock_message = MagicMock()
        mock_message.edit = AsyncMock()
        
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        
        with patch("discord_app.message_tools.client") as mock_client:
            mock_client.get_channel.return_value = mock_channel
            
            result = await edit_message(123456, "New content", 987654)
            
            assert result is True
            mock_message.edit.assert_called_once_with(content="New content")

    @pytest.mark.asyncio
    async def test_edit_message_not_found(self):
        import discord
        
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Not found"))
        
        with patch("discord_app.message_tools.client") as mock_client:
            mock_client.get_channel.return_value = mock_channel
            
            result = await edit_message(123456, "New content", 987654)
            
            assert result is False

    @pytest.mark.asyncio
    async def test_edit_message_http_exception(self):
        import discord
        
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "HTTP error"))
        
        with patch("discord_app.message_tools.client") as mock_client:
            mock_client.get_channel.return_value = mock_channel
            
            result = await edit_message(123456, "New content", 987654)
            
            assert result is False


class TestReplyToMessage:
    """Tests for reply_to_message function."""

    @pytest.mark.asyncio
    async def test_reply_to_message_success(self):
        mock_original = MagicMock()
        mock_original.to_reference.return_value = MagicMock()
        
        mock_reply = MagicMock()
        mock_reply.id = 789012
        
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_original)
        mock_channel.send = AsyncMock(return_value=mock_reply)
        
        with patch("discord_app.message_tools.client") as mock_client:
            mock_client.get_channel.return_value = mock_channel
            
            result = await reply_to_message(123456, "Reply content", 987654)
            
            assert result == mock_reply
            mock_channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_reply_to_message_not_found(self):
        import discord
        
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Not found"))
        
        with patch("discord_app.message_tools.client") as mock_client:
            mock_client.get_channel.return_value = mock_channel
            
            result = await reply_to_message(123456, "Reply content", 987654)
            
            assert result is None


class TestGetMessageContent:
    """Tests for get_message_content function."""

    @pytest.mark.asyncio
    async def test_get_message_content_success(self):
        mock_message = MagicMock()
        mock_message.content = "Test message content"
        mock_message.author.display_name = "TestUser"
        mock_message.author.id = 111
        mock_message.created_at.isoformat.return_value = "2025-01-01T00:00:00"
        mock_message.embeds = []
        mock_message.attachments = []
        
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        
        with patch("discord_app.message_tools.client") as mock_client:
            mock_client.get_channel.return_value = mock_channel
            
            result = await get_message_content(123456, 987654)
            
            assert result["success"] is True
            assert result["text"] == "Test message content"
            assert result["author"] == "TestUser"

    @pytest.mark.asyncio
    async def test_get_message_content_with_embeds(self):
        mock_embed = MagicMock()
        mock_embed.title = "Test Title"
        mock_embed.description = "Test Description"
        mock_embed.color.value = 0x3498db
        mock_embed.fields = []
        
        mock_message = MagicMock()
        mock_message.content = "Message with embed"
        mock_message.author.display_name = "TestUser"
        mock_message.author.id = 111
        mock_message.created_at.isoformat.return_value = "2025-01-01T00:00:00"
        mock_message.embeds = [mock_embed]
        mock_message.attachments = []
        
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        
        with patch("discord_app.message_tools.client") as mock_client:
            mock_client.get_channel.return_value = mock_channel
            
            result = await get_message_content(123456, 987654)
            
            assert result["success"] is True
            assert len(result["embeds"]) == 1
            assert result["embeds"][0]["title"] == "Test Title"


class TestExecuteToolInvocations:
    """Tests for execute_tool_invocations function."""

    @pytest.mark.asyncio
    async def test_execute_edit_message_invocation(self):
        mock_message = MagicMock()
        mock_message.edit = AsyncMock()
        
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_channel.id = 987654
        
        invocations = [{
            "name": "edit_message",
            "args": {"message_id": "123456", "new_content": "Updated", "channel_id": "987654"},
            "raw": "[AIDM-TOOL: edit_message | message_id=123456 | new_content=Updated]",
            "start": 0,
            "end": 60,
        }]
        
        with patch("discord_app.message_tools.client") as mock_client:
            mock_client.get_channel.return_value = mock_channel
            
            result = await execute_tool_invocations(invocations, mock_channel)
            
            assert "Edited message 123456" in result

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        mock_channel = MagicMock()
        
        invocations = [{
            "name": "unknown_tool",
            "args": {},
            "raw": "[AIDM-TOOL: unknown_tool]",
            "start": 0,
            "end": 25,
        }]
        
        result = await execute_tool_invocations(invocations, mock_channel)
        
        assert "Unknown tool: unknown_tool" in result

    @pytest.mark.asyncio
    async def test_execute_empty_invocations(self):
        mock_channel = MagicMock()
        result = await execute_tool_invocations([], mock_channel)
        assert result == ""


class TestForwardMessage:
    """Tests for forward_message function."""

    @pytest.mark.asyncio
    async def test_forward_message_success(self):
        mock_original = MagicMock()
        mock_original.content = "Original message content"
        mock_original.author.display_name = "OriginalAuthor"
        mock_original.created_at.strftime.return_value = "2025-01-01 12:00:00"
        mock_original.embeds = []
        mock_original.attachments = []
        
        mock_source = MagicMock()
        mock_source.fetch_message = AsyncMock(return_value=mock_original)
        
        mock_target = MagicMock()
        mock_forwarded = MagicMock()
        mock_forwarded.id = 789012
        mock_target.send = AsyncMock(return_value=mock_forwarded)
        
        with patch("discord_app.message_tools.client") as mock_client:
            def get_channel_side_effect(channel_id):
                if channel_id == 987654:
                    return mock_source
                elif channel_id == 111222:
                    return mock_target
                return None
            
            mock_client.get_channel.side_effect = get_channel_side_effect
            
            result = await forward_message(123456, 111222, 987654, include_context=True)
            
            assert result == mock_forwarded
            mock_target.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_forward_message_not_found(self):
        import discord
        
        mock_source = MagicMock()
        mock_source.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Not found"))
        
        with patch("discord_app.message_tools.client") as mock_client:
            mock_client.get_channel.return_value = mock_source
            
            result = await forward_message(123456, 111222, 987654)
            
            assert result is None


class TestSharedFunctionsMessageTracking:
    """Tests for message tracking in shared_functions."""

    def test_record_sent_messages(self):
        from discord_app.shared_functions import _record_sent_messages, sent_messages
        
        # Clear any existing records
        sent_messages.clear()
        
        _record_sent_messages(123456, [789012, 789013], "Test message")
        
        assert 123456 in sent_messages
        assert len(sent_messages[123456]) == 2
        assert sent_messages[123456][0]["message_id"] == 789012

    def test_get_sent_messages(self):
        from discord_app.shared_functions import _record_sent_messages, get_sent_messages, sent_messages
        
        sent_messages.clear()
        _record_sent_messages(123456, [789012], "Test")
        
        records = get_sent_messages(123456)
        assert len(records) == 1
        assert records[0]["message_id"] == 789012

    def test_get_last_sent_message(self):
        from discord_app.shared_functions import _record_sent_messages, get_last_sent_message, sent_messages
        
        sent_messages.clear()
        _record_sent_messages(123456, [789012, 789013], "Test")
        
        last = get_last_sent_message(123456)
        assert last["message_id"] == 789013

    def test_get_last_sent_message_empty(self):
        from discord_app.shared_functions import get_last_sent_message, sent_messages
        
        sent_messages.clear()
        
        last = get_last_sent_message(999999)
        assert last is None