"""
Tests for message editing functionality (Phase 2).

Tests the PATCH /conversations/{conv_id}/messages/{msg_id}/edit endpoint:
1. Validates user owns conversation and message is USER type
2. Stores original content on first edit
3. Updates content and sets edited_at
4. Deletes subsequent messages
"""

import pytest

from tests.helpers import (
    login_and_get_cookies,
    register_user,
)
from tests.helpers.api import _auth_headers


class TestMessageEdit:
    """Tests for the message edit endpoint."""

    @pytest.mark.asyncio
    async def test_edit_requires_auth(self, client):
        """Test that edit endpoint requires authentication."""
        fake_conv_id = "00000000-0000-0000-0000-000000000000"
        fake_msg_id = "00000000-0000-0000-0000-000000000001"

        # Try without auth
        edit_resp = await client.patch(
            f"/api/v1/conversations/{fake_conv_id}/messages/{fake_msg_id}/edit",
            json={"content": "Test content"},
        )

        assert edit_resp.status_code in (401, 403)


class TestMessageEditSchema:
    """Tests for MessageEditRequest and MessageEditResponse schemas."""

    def test_message_edit_request_schema(self):
        """Test MessageEditRequest schema validation."""
        from airbeeps.chat.api.v1.schemas import MessageEditRequest

        # Valid request
        req = MessageEditRequest(content="Hello world")
        assert req.content == "Hello world"
        assert req.regenerate is True  # Default value

        # With regenerate set
        req = MessageEditRequest(content="Test", regenerate=False)
        assert req.regenerate is False

    def test_message_edit_request_min_length(self):
        """Test that empty content is rejected."""
        from pydantic import ValidationError
        from airbeeps.chat.api.v1.schemas import MessageEditRequest

        with pytest.raises(ValidationError):
            MessageEditRequest(content="")

    def test_message_edit_request_max_length(self):
        """Test that content over max length is rejected."""
        from pydantic import ValidationError
        from airbeeps.chat.api.v1.schemas import MessageEditRequest

        # Content over 50000 characters
        with pytest.raises(ValidationError):
            MessageEditRequest(content="x" * 50001)

    def test_message_response_edit_fields(self):
        """Test MessageResponse includes editing fields."""
        from datetime import datetime, timezone
        from uuid import uuid4
        from airbeeps.chat.api.v1.schemas import MessageResponse

        now = datetime.now(timezone.utc)
        msg_id = uuid4()
        conv_id = uuid4()

        response = MessageResponse(
            id=msg_id,
            message_type="USER",
            conversation_id=conv_id,
            content="Test content",
            created_at=now,
            updated_at=now,
            edited_at=now,
            original_content="Original content",
            is_regenerated=False,
            parent_message_id=None,
        )

        assert response.edited_at == now
        assert response.original_content == "Original content"
        assert response.is_regenerated is False
        assert response.parent_message_id is None

    def test_message_edit_response_schema(self):
        """Test MessageEditResponse schema."""
        from datetime import datetime, timezone
        from uuid import uuid4
        from airbeeps.chat.api.v1.schemas import MessageEditResponse, MessageResponse

        now = datetime.now(timezone.utc)
        msg_id = uuid4()
        conv_id = uuid4()

        message = MessageResponse(
            id=msg_id,
            message_type="USER",
            conversation_id=conv_id,
            content="Edited content",
            created_at=now,
            updated_at=now,
            edited_at=now,
            original_content="Original content",
        )

        response = MessageEditResponse(
            message=message,
            deleted_count=3,
        )

        assert response.message.content == "Edited content"
        assert response.deleted_count == 3


class TestMessageEditFields:
    """Tests for message model editing fields."""

    def test_message_model_has_edit_fields(self):
        """Verify Message model has required editing fields."""
        from airbeeps.assistants.models import Message
        from sqlalchemy import inspect

        mapper = inspect(Message)
        columns = {col.key for col in mapper.columns}

        assert "edited_at" in columns, "Message should have edited_at field"
        assert "original_content" in columns, (
            "Message should have original_content field"
        )
        assert "is_regenerated" in columns, "Message should have is_regenerated field"
        assert "parent_message_id" in columns, (
            "Message should have parent_message_id field"
        )

    def test_edit_fields_nullable(self):
        """Verify editing fields are nullable (optional for new messages)."""
        from airbeeps.assistants.models import Message
        from sqlalchemy import inspect

        mapper = inspect(Message)
        columns = {col.key: col for col in mapper.columns}

        assert columns["edited_at"].nullable is True
        assert columns["original_content"].nullable is True
        assert columns["parent_message_id"].nullable is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
