"""
Langchain-based chat service
"""

import asyncio
import base64
import binascii
import contextlib
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes as orm_attributes, selectinload

from airbeeps.ai_models.client_factory import create_chat_model
from airbeeps.ai_models.models import Model
from airbeeps.assistants.models import Assistant, Conversation, Message, MessageTypeEnum
from airbeeps.files.storage import storage_service
from airbeeps.system_config.service import config_service

from .conversation_service import ConversationService
from .effective_config import resolve_followup_config, resolve_generation_config
from .models import ChatMessage, MessageRole
from .prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


class LangchainChatService:
    """Chat service using langchain for AI interactions"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.conversation_service = ConversationService(session)
        self.prompt_builder = PromptBuilder(session=session)
        self._in_think_block = False  # Track if we're inside a <think> block

    async def _store_inline_media_to_s3(
        self, *, base64_data: str, mime_type: str
    ) -> dict[str, Any] | None:
        """Persist inline media blob to S3 and return metadata for downstream usage."""
        logger.debug(
            f"_store_inline_media_to_s3 called with mime_type={mime_type}, data_len={len(base64_data) if base64_data else 0}"
        )
        if not base64_data:
            logger.warning("Empty base64_data provided to _store_inline_media_to_s3")
            return None

        try:
            binary_data = base64.b64decode(base64_data)
            logger.debug(f"Decoded {len(binary_data)} bytes from base64")
        except (binascii.Error, ValueError) as e:
            logger.warning(
                f"Failed to decode inline media payload from Gemini response: {e}"
            )
            return None

        file_id = uuid.uuid4()
        subtype = ""
        if "/" in mime_type:
            subtype = mime_type.split("/", 1)[1].split(";", 1)[0]
        filename = f"{file_id}.{subtype}" if subtype else str(file_id)

        buffer = BytesIO(binary_data)
        buffer.seek(0)

        try:
            file_key = await storage_service.upload_file(
                file_data=buffer,
                file_type="ai-generated",
                file_id=file_id,
                filename=filename,
                content_type=mime_type,
                file_size=len(binary_data),
            )
            public_url = await storage_service.get_public_url(file_key)
            return {
                "file_key": file_key,
                "url": public_url,
                "size": len(binary_data),
                "content_type": mime_type,
            }
        except Exception as exc:
            logger.error("Failed to upload inline media to S3: %s", exc, exc_info=True)
            return None

    async def _store_gemini_parts_snapshot(
        self, *, parts: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Persist sanitized Gemini response parts JSON to S3."""
        if not parts:
            return None

        try:
            payload = json.dumps(parts).encode("utf-8")
        except (TypeError, ValueError) as exc:
            logger.error("Failed to serialize Gemini parts payload: %s", exc)
            return None

        file_id = uuid.uuid4()
        filename = f"{file_id}.json"
        buffer = BytesIO(payload)
        buffer.seek(0)

        try:
            file_key = await storage_service.upload_file(
                file_data=buffer,
                file_type="gemini-parts",
                file_id=file_id,
                filename=filename,
                content_type="application/json",
                file_size=len(payload),
            )
            public_url = await storage_service.get_public_url(file_key)
            return {
                "file_key": file_key,
                "url": public_url,
                "size": len(payload),
                "content_type": "application/json",
            }
        except Exception as exc:
            logger.error(
                "Failed to upload Gemini parts snapshot to S3: %s", exc, exc_info=True
            )
            return None

    async def create_conversation(
        self, assistant_id: uuid.UUID, user_id: uuid.UUID, title: str | None = None
    ) -> Conversation:
        logger.info(
            f"Creating conversation for assistant {assistant_id}, user {user_id}"
        )
        conversation = await self.conversation_service.create_conversation(
            assistant_id=assistant_id,
            user_id=user_id,
            title=title,
        )
        logger.info(f"Successfully created conversation {conversation.id}")
        return conversation

    async def get_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        return await self.conversation_service.get_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
        )

    async def get_conversation_messages(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Message]:
        return await self.conversation_service.get_conversation_messages(
            conversation_id=conversation_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    def _prepare_image_attachments(
        self,
        raw_images: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Create prompt + storage payloads for user-provided images."""
        prompt_payloads: list[dict[str, Any]] = []
        stored_payloads: list[dict[str, Any]] = []

        for index, image in enumerate(raw_images):
            if not isinstance(image, dict):
                logger.debug("Skipping non-dict image attachment at index %s", index)
                continue

            sanitized = self._sanitize_single_image(image, index)
            if not sanitized:
                continue

            stored_payloads.append(sanitized)
            prompt_payload = dict(image)
            prompt_payload.update(sanitized)
            prompt_payloads.append(prompt_payload)

        return prompt_payloads, stored_payloads

    def _sanitize_single_image(
        self,
        image: dict[str, Any],
        index: int,
    ) -> dict[str, Any] | None:
        url = image.get("url")
        file_key = (
            image.get("file_key")
            or image.get("fileKey")
            or image.get("file_path")
            or image.get("filePath")
        )

        data_url = image.get("data_url") or image.get("dataUrl")
        if not url and data_url and data_url.startswith("http"):
            url = data_url

        if not url and not file_key:
            logger.warning(
                "Skipping image attachment %s: missing both url and file reference",
                index,
            )
            return None

        sanitized: dict[str, Any] = {
            "id": str(image.get("id") or uuid.uuid4()),
        }
        if url:
            sanitized["url"] = url
        if file_key:
            sanitized["file_key"] = file_key

        mime_value = (
            image.get("mime_type")
            or image.get("mimeType")
            or image.get("content_type")
            or image.get("contentType")
        )
        if mime_value:
            sanitized["mime_type"] = mime_value

        if image.get("alt"):
            sanitized["alt"] = image["alt"]
        size_value = image.get("size")
        if isinstance(size_value, (int, float)):
            sanitized["size"] = size_value
        if image.get("source"):
            sanitized["source"] = image["source"]

        return sanitized

    @staticmethod
    def _summarize_messages(
        messages: list[ChatMessage], max_snippet: int = 400
    ) -> list[dict[str, Any]]:
        """Build a lightweight, redacted summary of messages for debugging."""
        summary: list[dict[str, Any]] = []
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role.value}
            content = msg.content
            if isinstance(content, str):
                entry["len"] = len(content)
                entry["snippet"] = content[:max_snippet]
            elif isinstance(content, list):
                text_parts: list[str] = []
                media_count = 0
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "text" and part.get("text"):
                        text_parts.append(str(part.get("text")))
                    else:
                        media_count += 1
                combined = " ".join(text_parts)
                entry["text_len"] = len(combined)
                entry["text_snippet"] = combined[:max_snippet]
                entry["media_items"] = media_count
            else:
                entry["len"] = 0
                entry["snippet"] = ""
            summary.append(entry)
        return summary

    def _debug_log_prompt(
        self,
        messages: list[ChatMessage],
        conversation_id: uuid.UUID,
        label: str = "prompt",
    ) -> None:
        """Log sanitized prompt for debugging; avoid logging full content."""
        try:
            summary = self._summarize_messages(messages)
            logger.debug(
                "DebugPrompt [%s] conv=%s messages=%s",
                label,
                conversation_id,
                json.dumps(summary, ensure_ascii=False),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to log debug prompt: %s", exc)

    async def send_message_stream(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        images: list[dict[str, Any]] | None = None,
        language: str | None = None,
        model_id_override: uuid.UUID | None = None,
        web_search_enabled: bool | None = None,
    ) -> AsyncIterator[dict]:
        """Send a message and get streaming AI response (supports Agent mode)"""
        logger.info(
            f"Starting message stream for conversation {conversation_id}, user {user_id}, has_images={bool(images)}"
        )
        logger.debug(
            f"Message content length: {len(content)}, language: {language}, model_override: {model_id_override}"
        )

        conversation = await self.conversation_service.get_conversation_with_model(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        if not conversation:
            logger.warning(
                f"Conversation {conversation_id} not found or access denied for user {user_id}"
            )
            raise ValueError("Conversation not found or access denied")

        # Handle model override if provided
        effective_model_name = conversation.assistant.model.name
        if model_id_override:
            override_model = await self.session.execute(
                select(Model)
                .options(selectinload(Model.provider))
                .where(Model.id == model_id_override)
            )
            override_model = override_model.scalar_one_or_none()
            if override_model and override_model.provider:
                # Temporarily swap the model for this request
                conversation.assistant.model = override_model
                effective_model_name = override_model.name
                logger.info(f"Using override model: {effective_model_name}")

        # Handle web search toggle if provided (affects agent tool availability)
        # Store the override in conversation extra_data for agent executor to pick up
        if web_search_enabled is not None:
            if not conversation.extra_data:
                conversation.extra_data = {}
            conversation.extra_data["web_search_enabled_override"] = web_search_enabled
            logger.debug(f"Web search override set to: {web_search_enabled}")

        # Prepare image attachments for prompting + persistence
        prompt_images: list[dict[str, Any]] | None = None
        user_extra_data: dict[str, Any] = {}
        if images:
            logger.debug(f"Processing {len(images)} image attachments")
            prompt_images, stored_images = self._prepare_image_attachments(images)
            if stored_images:
                user_extra_data["images"] = stored_images
                logger.debug(f"Stored {len(stored_images)} images in user message")
        else:
            stored_images = None

        # Explicitly set created_at to ensure proper ordering
        # Add a small delay to assistant message to ensure it appears after user message
        now = datetime.now(UTC)

        user_message = Message(
            content=content,
            message_type=MessageTypeEnum.USER,
            conversation_id=conversation_id,
            user_id=user_id,
            extra_data=user_extra_data if user_extra_data else None,
            created_at=now,
        )

        assistant_message = Message(
            content="",  # Will be updated after streaming
            message_type=MessageTypeEnum.ASSISTANT,
            conversation_id=conversation_id,
            extra_data={"model": effective_model_name},
            created_at=now + timedelta(milliseconds=10),
        )

        self.session.add(user_message)
        self.session.add(assistant_message)
        await self.session.flush()  # Get IDs
        logger.debug(
            f"Created user message {user_message.id} and assistant message {assistant_message.id}"
        )

        # Variables to store streaming results
        content_chunks = []
        media_outputs: list[dict[str, Any]] = []
        assistant_citations: list[dict[str, Any]] = []
        error_occurred = False
        error_message = ""
        agent_execution_log = []  # Store agent thought chain (only for agent mode)
        reasoning_traces: list[
            dict[str, Any]
        ] = []  # Store reasoning traces from LLM (e.g., o1, o3)
        current_reasoning_content = ""  # Accumulate reasoning content during streaming
        token_usage = None  # Store token usage information
        exclude_ids = [user_message.id, assistant_message.id]

        try:
            # Choose streaming method based on mode
            if conversation.assistant.enable_agent:
                logger.info(f"Using agent mode for conversation {conversation_id}")
                # Agent mode: use agent execution engine with tools
                stream_generator = self._stream_agent_response(
                    conversation.assistant,
                    content,
                    conversation,
                    assistant_message.id,
                    exclude_ids,
                    language=language,
                )
            else:
                logger.debug(f"Using non-agent mode for conversation {conversation_id}")
                # Non-agent mode: direct LLM chat with optional RAG
                # Yield assistant message start event
                yield {
                    "type": "assistant_message_start",
                    "data": {
                        "id": str(assistant_message.id),
                        "conversation_id": str(conversation_id),
                        "message_type": "ASSISTANT",
                        "model": effective_model_name,
                        "created_at": assistant_message.created_at.isoformat(),
                    },
                }

                chat_messages, assistant_citations = await self.build_prompt_messages(
                    conversation,
                    content,
                    exclude_ids,
                    current_images=prompt_images,
                    language=language,
                )
                self._debug_log_prompt(
                    chat_messages, conversation_id, label="chat_input"
                )
                stream_generator = self._stream_ai_response(
                    conversation.assistant, chat_messages
                )

            # Process streaming events (unified handling for both modes)
            async for chunk_data in stream_generator:
                # Track agent execution steps (agent mode only)
                if chunk_data["type"] == "agent_action":
                    agent_execution_log.append(chunk_data["data"])

                # Collect reasoning traces (non-agent mode, for models like o1, o3)
                if chunk_data["type"] == "reasoning_trace":
                    reasoning_content = chunk_data["data"].get("content", "")
                    is_final = chunk_data["data"].get("is_final", False)
                    if reasoning_content:
                        current_reasoning_content += reasoning_content
                    if is_final and current_reasoning_content:
                        # Finalize reasoning trace
                        reasoning_traces.append(
                            {
                                "type": "agent_thought",
                                "thought": current_reasoning_content.strip(),
                                "description": "Model reasoning process",
                                "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                            }
                        )
                        current_reasoning_content = ""

                # Collect reasoning traces batch (if sent as batch)
                if chunk_data["type"] == "reasoning_traces":
                    traces = chunk_data["data"].get("traces", [])
                    if traces:
                        reasoning_traces.extend(traces)

                # Collect content chunks (both modes)
                if chunk_data["type"] == "content_chunk":
                    chunk_content = chunk_data["data"].get("content", "")
                    if chunk_content:
                        content_chunks.append(chunk_content)
                    chunk_media = chunk_data["data"].get("media")
                    if chunk_media:
                        logger.info(
                            f"Collecting {len(chunk_media)} media items from chunk"
                        )
                        media_outputs.extend(chunk_media)
                        logger.info(f"Total media_outputs now: {len(media_outputs)}")

                # Collect token usage (both modes)
                if chunk_data["type"] == "token_usage":
                    token_usage = chunk_data["data"]

                # Forward all events to client
                yield chunk_data

        except asyncio.CancelledError:
            logger.warning(
                f"Streaming cancelled by client for conversation {conversation_id}"
            )
            with contextlib.suppress(Exception):
                await self.session.rollback()
            raise
        except Exception as e:
            error_occurred = True
            error_message = str(e)
            logger.error(
                f"Streaming error for conversation {conversation_id}: {error_message}",
                exc_info=True,
            )

        # After all streaming is complete, handle database operations and final response
        if error_occurred:
            # Rollback any pending changes
            with contextlib.suppress(Exception):
                await self.session.rollback()

            yield {
                "type": "error",
                "data": {
                    "error": error_message,
                    "conversation_id": str(conversation_id),
                },
            }
        else:
            # Success case - update database and send completion
            complete_content = "".join(content_chunks)
            logger.info(
                f"Stream completed for conversation {conversation_id}: {len(complete_content)} chars, {len(media_outputs)} media items"
            )
            with contextlib.suppress(Exception):
                logger.debug(
                    "DebugOutput conv=%s len=%s snippet=%s",
                    conversation_id,
                    len(complete_content),
                    complete_content[:400],
                )

            assistant_message.content = complete_content

            # Store agent execution log if available (agent mode)
            if agent_execution_log:
                assistant_message.extra_data["agent_execution"] = agent_execution_log

            # Store reasoning traces if available (non-agent mode, for models like o1, o3)
            if reasoning_traces:
                # Merge with existing agent_execution if present, otherwise create new
                if "agent_execution" in assistant_message.extra_data:
                    existing_execution = assistant_message.extra_data["agent_execution"]
                    if isinstance(existing_execution, list):
                        assistant_message.extra_data["agent_execution"] = (
                            existing_execution + reasoning_traces
                        )
                    else:
                        assistant_message.extra_data["agent_execution"] = (
                            reasoning_traces
                        )
                else:
                    assistant_message.extra_data["agent_execution"] = reasoning_traces
                orm_attributes.flag_modified(assistant_message, "extra_data")
                logger.info(
                    f"Stored {len(reasoning_traces)} reasoning traces in message extra_data"
                )

            logger.info(
                f"Preparing to save message. media_outputs length: {len(media_outputs)}"
            )
            if assistant_citations:
                assistant_message.extra_data["citations"] = assistant_citations
                orm_attributes.flag_modified(assistant_message, "extra_data")

            if media_outputs:
                logger.info(
                    f"Saving {len(media_outputs)} media items to assistant_message.extra_data"
                )
                assistant_message.extra_data["media"] = media_outputs
                # Mark extra_data as modified for SQLAlchemy to detect changes
                orm_attributes.flag_modified(assistant_message, "extra_data")
                logger.info(
                    f"assistant_message.extra_data after assignment: {assistant_message.extra_data}"
                )

            # Follow-up question suggestions (best-effort; never fail the main chat flow)
            try:
                followup_cfg = await resolve_followup_config(
                    self.session, conversation.assistant
                )
                logger.info(
                    f"Follow-up config: enabled={followup_cfg.enabled}, count={followup_cfg.count}"
                )
                if followup_cfg.enabled and followup_cfg.count > 0:
                    followups = await self._generate_followup_questions(
                        assistant=conversation.assistant,
                        user_input=content,
                        assistant_reply=complete_content,
                        count=followup_cfg.count,
                        language=language,
                    )
                    logger.info(
                        f"Generated {len(followups)} follow-up questions: {followups}"
                    )
                    if followups:
                        assistant_message.extra_data["followup_questions"] = followups
                        orm_attributes.flag_modified(assistant_message, "extra_data")
                        # Ensure follow-ups persist before the refresh below
                        await self.session.flush()
            except Exception as exc:
                logger.warning(
                    "Failed to generate follow-up questions (conv=%s): %s",
                    conversation_id,
                    exc,
                )

            # Update conversation metadata
            conversation.last_message_at = datetime.now(UTC)
            conversation.message_count = conversation.message_count + 2

            # Refresh ORM objects to ensure all DB-generated attributes (e.g. updated_at) are loaded
            # This is necessary after async operations like _generate_followup_questions
            await self.session.refresh(assistant_message)

            # Always yield completion (with or without DB update success)
            completion_data = {
                "type": "assistant_message_complete",
                "data": {
                    "id": str(assistant_message.id),
                    "content": complete_content,
                    "conversation_id": str(conversation_id),
                    "message_type": "ASSISTANT",
                    "model": effective_model_name,
                    "created_at": assistant_message.created_at.isoformat(),
                    "updated_at": assistant_message.updated_at.isoformat(),
                    "user_message_id": str(user_message.id),
                },
            }

            if media_outputs:
                logger.info(
                    f"Adding {len(media_outputs)} media items to completion_data"
                )
                completion_data["data"]["media"] = media_outputs

            # Add token usage to completion data if available
            if token_usage:
                completion_data["data"]["token_usage"] = token_usage

            completion_data["data"]["extra_data"] = assistant_message.extra_data
            logger.info(
                f"Final completion_data keys: {list(completion_data['data'].keys())}"
            )
            if "followup_questions" in assistant_message.extra_data:
                logger.info(
                    f"Follow-up questions in extra_data: {assistant_message.extra_data.get('followup_questions')}"
                )
            logger.info(
                f"Completion extra_data.media length: {len(completion_data['data'].get('extra_data', {}).get('media', []))}"
            )
            # Log reasoning traces in completion data for debugging
            if reasoning_traces:
                logger.info(
                    f"Completion extra_data.agent_execution has {len(reasoning_traces)} reasoning traces"
                )
                logger.debug(
                    f"Reasoning traces: {[{'type': t.get('type'), 'has_thought': bool(t.get('thought'))} for t in reasoning_traces]}"
                )
            elif assistant_message.extra_data.get("agent_execution"):
                exec_data = assistant_message.extra_data["agent_execution"]
                if isinstance(exec_data, list):
                    logger.info(
                        f"Completion extra_data.agent_execution has {len(exec_data)} items (not reasoning traces)"
                    )
                else:
                    logger.info(
                        f"Completion extra_data.agent_execution is not a list: {type(exec_data)}"
                    )
            else:
                logger.info("No agent_execution in completion extra_data")

            # Record token usage and execution stats
            if token_usage and token_usage.get("total_tokens", 0) > 0:
                assistant_message.extra_data["token_usage"] = token_usage
                orm_attributes.flag_modified(assistant_message, "extra_data")

            # Calculate execution time
            if assistant_message.created_at:
                now_utc = datetime.now(UTC)
                msg_created = assistant_message.created_at
                # Ensure both are timezone-aware for subtraction (SQLite may return naive datetimes)
                if msg_created.tzinfo is None:
                    msg_created = msg_created.replace(tzinfo=UTC)
                execution_time_ms = (now_utc - msg_created).total_seconds() * 1000
                # Ensure positive duration
                execution_time_ms = max(execution_time_ms, 0)

                assistant_message.extra_data["execution_time_ms"] = int(
                    execution_time_ms
                )
                orm_attributes.flag_modified(assistant_message, "extra_data")

                if "data" in completion_data:
                    completion_data["data"]["execution_time_ms"] = int(
                        execution_time_ms
                    )

            # Commit all updates together (message, conversation, and token usage)
            await self.session.commit()

            yield completion_data

    @staticmethod
    def _parse_followup_questions(raw: str, *, count: int) -> list[str]:
        """Parse model output into a de-duplicated list of follow-up questions."""
        if not raw or count <= 0:
            return []

        def normalize(item: Any) -> str | None:
            if item is None:
                return None
            text = str(item).strip()
            if not text:
                return None
            # Strip common bullets / numbering.
            text = re.sub(r"^\s*[-*•]\s+", "", text)
            text = re.sub(r"^\s*\d+[\).\s-]+\s*", "", text)
            text = text.strip().strip('"').strip("'").strip()
            if not text:
                return None
            # Keep it reasonably short for UI.
            if len(text) > 200:
                text = text[:200].rstrip()
            return text

        candidates: list[str] = []

        # Try strict JSON array first.
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for item in parsed:
                    norm = normalize(item)
                    if norm:
                        candidates.append(norm)
        except Exception:
            logger.debug("Failed to parse follow-up questions as strict JSON")
            candidates = []

        # Try extracting a JSON array from surrounding text/code blocks.
        if not candidates:
            try:
                start = raw.find("[")
                end = raw.rfind("]")
                if start != -1 and end != -1 and end > start:
                    parsed = json.loads(raw[start : end + 1])
                    if isinstance(parsed, list):
                        for item in parsed:
                            norm = normalize(item)
                            if norm:
                                candidates.append(norm)
            except Exception:
                logger.debug(
                    "Failed to extract JSON array from follow-up questions response"
                )
                candidates = []

        # Fallback: split lines.
        if not candidates:
            for line in raw.splitlines():
                norm = normalize(line)
                if norm:
                    candidates.append(norm)

        # De-duplicate while preserving order.
        seen = set()
        deduped: list[str] = []
        for q in candidates:
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(q)
            if len(deduped) >= count:
                break

        return deduped

    async def _generate_followup_questions(
        self,
        *,
        assistant: Assistant,
        user_input: str,
        assistant_reply: str,
        count: int,
        language: str | None = None,
    ) -> list[str]:
        """Generate follow-up question suggestions using the assistant's model."""
        if count <= 0:
            return []
        if not user_input or not assistant_reply:
            return []

        # Keep prompt compact; follow-ups should be fast and cheap.
        system_prompt = (
            "You generate follow-up question suggestions for a chat UI.\n"
            "Rules:\n"
            f"- Output MUST be a JSON array of strings with exactly {count} items.\n"
            "- Each item is a natural-sounding question the user might ask next.\n"
            "- Keep each question concise (<= 120 characters).\n"
            "- No numbering, bullets, markdown, or extra text.\n"
            "- Do not repeat the user's question verbatim.\n"
            "- Use the same language as the conversation.\n"
        )
        if language:
            system_prompt += f"- Preferred language code: {language}\n"

        user_prompt = (
            "Conversation context:\n"
            f"User message:\n{user_input}\n\n"
            f"Assistant answer:\n{assistant_reply}\n"
        )

        client = create_chat_model(
            provider=assistant.model.provider,
            model_name=assistant.model.name,
            temperature=0.4,
            max_tokens=256,
        )
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]
        response = await client.ainvoke([m.to_litellm_message() for m in messages])

        content = ""
        try:
            if response and hasattr(response, "choices") and response.choices:
                content = (
                    response.choices[0].message.content.strip()
                    if response.choices[0].message
                    and response.choices[0].message.content
                    else ""
                )
        except Exception:
            logger.debug("Failed to extract follow-up questions from response")
            content = ""

        return self._parse_followup_questions(content, count=count)

    async def build_prompt_messages(
        self,
        conversation: Conversation,
        user_input: str,
        exclude_message_ids: list[uuid.UUID] | None = None,
        current_images: list[dict[str, Any]] | None = None,
        language: str | None = None,
        include_agent_rag: bool = False,
    ) -> tuple[list[ChatMessage], list[dict[str, Any]]]:
        """Delegate prompt construction to PromptBuilder for reuse."""
        return await self.prompt_builder.build_prompt_messages(
            conversation=conversation,
            user_input=user_input,
            exclude_message_ids=exclude_message_ids,
            current_images=current_images,
            language=language,
            include_agent_rag=include_agent_rag,
        )

    async def _stream_agent_response(
        self,
        assistant: Assistant,
        user_input: str,
        conversation: Conversation,
        assistant_message_id: uuid.UUID,
        exclude_message_ids: list[uuid.UUID] | None = None,
        language: str | None = None,
    ) -> AsyncIterator[dict]:
        """
        Stream Agent execution response with thought chain and history support

        Yields chunks in the format:
        - {"type": "agent_action", "data": {"tool": str, "input": dict, "thought": str}}
        - {"type": "agent_observation", "data": {"observation": str}}
        - {"type": "content_chunk", "data": {"content": str, "is_final": bool}}
        - {"type": "token_usage", "data": {"input_tokens": int, "output_tokens": int, "total_tokens": int}}
        """
        from airbeeps.agents.executor import AgentExecutionEngine

        # Build chat history using the same method as non-agent mode
        # This ensures consistent token management and history handling
        chat_messages, _ = await self.build_prompt_messages(
            conversation,
            user_input,
            exclude_message_ids,
            language=language,
            include_agent_rag=True,
        )
        self._debug_log_prompt(chat_messages, conversation.id, label="agent_input")

        # Convert ChatMessage to dict format for agent
        # Agent expects [{"role": "user", "content": "..."}, ...]
        # Skip system messages as they're handled separately in agent
        chat_history = []
        for msg in chat_messages:
            if (
                msg.role != MessageRole.SYSTEM
            ):  # System prompt already in assistant config
                chat_history.append({"role": msg.role.value, "content": msg.content})

        # Remove the last user message (current input) from history
        # as it will be passed separately to stream_execute
        if chat_history and chat_history[-1]["role"] == "user":
            chat_history.pop()

        # Get translated system prompt
        system_prompt = self.prompt_builder.get_system_prompt(assistant, language)

        # Initialize Agent execution engine with user for permission checking
        agent_engine = AgentExecutionEngine(
            assistant=assistant,
            session=self.session,
            system_prompt_override=system_prompt,
            user=conversation.user,  # Pass user for proper permission checks
        )

        # Yield agent start event
        yield {
            "type": "agent_start",
            "data": {
                "assistant_message_id": str(assistant_message_id),
                "max_iterations": assistant.agent_max_iterations or 10,
                "history_messages": len(chat_history),
            },
        }

        try:
            # Stream agent execution with history
            async for event in agent_engine.stream_execute(
                user_input=user_input,
                conversation_id=conversation.id,
                chat_history=chat_history,
            ):
                # Forward agent events to client
                yield event

        except Exception as e:
            logger.error(f"Agent execution error: {e!s}")
            yield {
                "type": "error",
                "data": {"error": f"Agent execution failed: {e!s}"},
            }

    async def _stream_ai_response(
        self, assistant: Assistant, messages: list[ChatMessage]
    ) -> AsyncIterator[dict]:
        """Stream AI response using LiteLLM with token usage tracking"""

        # Use LiteLLM for all providers
        provider = assistant.model.provider
        effective = await resolve_generation_config(self.session, assistant)
        generation_params = effective.additional_params

        # Create LiteLLM client
        try:
            client = create_chat_model(
                provider=provider,
                model_name=assistant.model.name,
                temperature=effective.temperature,
                max_tokens=effective.max_tokens,
                **generation_params,
            )
        except Exception as e:
            raise ValueError(f"Failed to create chat client: {e!s}")

        # Convert ChatMessage to LiteLLM messages
        litellm_messages = [msg.to_litellm_message() for msg in messages]

        # Track token usage
        token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        media_counter = 0

        # Collect full response parts for Gemini (includes thought_signature)
        # This is critical for multi-turn image editing

        # Collect reasoning traces for models that support it (e.g., o1, o3)
        reasoning_traces: list[dict[str, Any]] = []
        current_reasoning_chunk = ""
        last_chunk = None  # Track last chunk to extract final reasoning

        def _register_media_payload(
            *,
            mime_type: str,
            origin: str,
            url: str | None = None,
            data_url: str | None = None,
            storage_info: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Normalize media metadata for downstream consumers."""
            nonlocal media_counter
            media_counter += 1
            entry: dict[str, Any] = {
                "id": f"media-{media_counter}",
                "type": "image" if mime_type.startswith("image/") else "binary",
                "mime_type": mime_type,
                "alt": f"Generated image {media_counter}"
                if mime_type.startswith("image/")
                else mime_type,
                "index": media_counter,
                "source": origin,
            }
            if url:
                entry["url"] = url
            elif data_url:
                entry["data_url"] = data_url
            if storage_info:
                entry["storage"] = storage_info
            return entry

        def _media_markdown(entry: dict[str, Any]) -> str:
            """Render lightweight placeholder for media to avoid huge prompts."""
            # Don't add placeholder text - frontend will render media from the media array
            return ""

        async def _extract_content_and_media(
            content_part: Any,
        ) -> tuple[str, list[dict[str, Any]]]:
            """Normalize LangChain chunk content and capture inline media."""
            text_segments: list[str] = []
            chunk_media: list[dict[str, Any]] = []

            async def _walk(part: Any) -> None:
                if part is None:
                    return
                if isinstance(part, str):
                    text_segments.append(part)
                    return
                if isinstance(part, list):
                    for item in part:
                        await _walk(item)
                    return
                if isinstance(part, dict):
                    # Log dict structure for debugging
                    logger.debug(f"Processing dict part with keys: {list(part.keys())}")

                    # Nested parts from Google responses
                    nested_parts = part.get("parts")
                    if nested_parts:
                        logger.debug(f"Found nested parts: {nested_parts}")
                        await _walk(nested_parts)

                    text_value = part.get("text")
                    if text_value:
                        text_segments.append(text_value)

                    inline_data = part.get("inline_data") or part.get("inlineData")
                    if inline_data:
                        logger.debug(
                            f"Found inline_data in chunk: {list(inline_data.keys())}"
                        )
                        mime_type = (
                            inline_data.get("mime_type")
                            or inline_data.get("mimeType")
                            or "application/octet-stream"
                        )
                        data = inline_data.get("data")
                        if data:
                            logger.info(
                                f"Attempting to upload inline media to S3 (mime: {mime_type}, size: {len(data)} chars)"
                            )
                            storage_info = await self._store_inline_media_to_s3(
                                base64_data=data, mime_type=mime_type
                            )
                            logger.info(f"S3 upload result: {storage_info is not None}")
                            if storage_info:
                                media_entry = _register_media_payload(
                                    mime_type=mime_type,
                                    origin="inline_data",
                                    url=storage_info.get("url"),
                                    storage_info=storage_info,
                                )
                            else:
                                data_url = f"data:{mime_type};base64,{data}"
                                media_entry = _register_media_payload(
                                    mime_type=mime_type,
                                    origin="inline_data",
                                    data_url=data_url,
                                )
                            chunk_media.append(media_entry)
                            placeholder = _media_markdown(media_entry)
                            if placeholder:
                                text_segments.append(placeholder)

                    image_url = part.get("image_url") or part.get("imageUrl")
                    if image_url:
                        if isinstance(image_url, dict):
                            url_value = image_url.get("url")
                        else:
                            url_value = image_url
                        if url_value:
                            # Check if it's a data URL that needs to be uploaded to S3
                            if url_value.startswith("data:"):
                                logger.info(
                                    "Found data URL in image_url, uploading to S3"
                                )
                                # Extract mime type and base64 data from data URL
                                # Format: data:image/jpeg;base64,<base64_data>
                                try:
                                    header, base64_data = url_value.split(",", 1)
                                    mime_type = (
                                        header.split(":")[1].split(";")[0]
                                        if ":" in header
                                        else "image/*"
                                    )

                                    logger.info(
                                        f"Uploading image_url data to S3 (mime: {mime_type}, size: {len(base64_data)} chars)"
                                    )
                                    storage_info = await self._store_inline_media_to_s3(
                                        base64_data=base64_data, mime_type=mime_type
                                    )
                                    logger.info(
                                        f"S3 upload result: {storage_info is not None}"
                                    )

                                    if storage_info:
                                        media_entry = _register_media_payload(
                                            mime_type=mime_type,
                                            origin="image_url",
                                            url=storage_info.get("url"),
                                            storage_info=storage_info,
                                        )
                                    else:
                                        # Fallback to data URL if upload failed
                                        media_entry = _register_media_payload(
                                            mime_type=mime_type,
                                            origin="image_url",
                                            data_url=url_value,
                                        )
                                except Exception as e:
                                    logger.warning(f"Failed to parse data URL: {e}")
                                    mime_type = part.get("mime_type") or "image/*"
                                    media_entry = _register_media_payload(
                                        mime_type=mime_type,
                                        origin="image_url",
                                        data_url=url_value,
                                    )
                            else:
                                # Regular HTTP(S) URL, use directly
                                mime_type = part.get("mime_type") or "image/*"
                                media_entry = _register_media_payload(
                                    mime_type=mime_type,
                                    origin="image_url",
                                    url=url_value,
                                )

                            chunk_media.append(media_entry)
                            placeholder = _media_markdown(media_entry)
                            if placeholder:
                                text_segments.append(placeholder)

                    file_data = part.get("file_data") or part.get("fileData")
                    if file_data:
                        await _walk(file_data)
                    return

                text_attr = getattr(part, "text", None)
                if text_attr:
                    text_segments.append(text_attr)
                inline_attr = getattr(part, "inline_data", None)
                if inline_attr:
                    await _walk(
                        {
                            "inline_data": {
                                "mime_type": getattr(inline_attr, "mime_type", None),
                                "data": getattr(inline_attr, "data", None),
                            }
                        }
                    )
                content_attr = getattr(part, "content", None)
                if content_attr:
                    await _walk(content_attr)

            await _walk(content_part)
            return "".join(text_segments), chunk_media

        # Check if we should use non-streaming mode to capture reasoning
        # LiteLLM streaming does NOT include reasoning field - it's only in non-streaming responses
        # See: https://github.com/BerriAI/litellm/issues/16155
        use_non_streaming_for_reasoning = await config_service.get_config_value(
            self.session, "ui_show_agent_thinking", True
        )
        logger.info(
            f"[REASONING] ui_show_agent_thinking={use_non_streaming_for_reasoning}"
        )

        try:
            if use_non_streaming_for_reasoning:
                # Use non-streaming mode to capture reasoning, then simulate streaming
                logger.info(
                    "[REASONING] Using non-streaming mode to capture reasoning content"
                )
                response = await client.ainvoke(litellm_messages)

                if response and hasattr(response, "choices") and response.choices:
                    choice = response.choices[0]
                    message = choice.message if hasattr(choice, "message") else None

                    if message:
                        # Log message structure for debugging
                        logger.info(
                            f"[REASONING] Non-streaming message type: {type(message)}"
                        )
                        if hasattr(message, "__dict__"):
                            logger.info(
                                f"[REASONING] Non-streaming message __dict__: {message.__dict__}"
                            )

                        # Extract reasoning from message
                        reasoning_content = None
                        if hasattr(message, "reasoning") and message.reasoning:
                            reasoning_content = message.reasoning
                            logger.info(
                                f"[REASONING] Found message.reasoning: {len(reasoning_content)} chars"
                            )
                        elif (
                            hasattr(message, "reasoning_content")
                            and message.reasoning_content
                        ):
                            reasoning_content = message.reasoning_content
                            logger.info("[REASONING] Found message.reasoning_content")
                        elif hasattr(message, "__dict__"):
                            msg_dict = message.__dict__
                            reasoning_content = msg_dict.get(
                                "reasoning"
                            ) or msg_dict.get("reasoning_content")
                            if reasoning_content:
                                logger.info(
                                    f"[REASONING] Found reasoning in __dict__: {len(reasoning_content)} chars"
                                )

                        # Yield reasoning traces
                        if (
                            reasoning_content
                            and isinstance(reasoning_content, str)
                            and reasoning_content.strip()
                        ):
                            current_reasoning_chunk = reasoning_content
                            reasoning_traces.append(
                                {
                                    "type": "agent_thought",
                                    "thought": reasoning_content.strip(),
                                    "description": "Model reasoning process",
                                    "timestamp": int(
                                        datetime.now(UTC).timestamp() * 1000
                                    ),
                                }
                            )
                            # Yield reasoning in chunks for streaming effect
                            chunk_size = 50  # Characters per chunk
                            for i in range(0, len(reasoning_content), chunk_size):
                                yield {
                                    "type": "reasoning_trace",
                                    "data": {
                                        "content": reasoning_content[
                                            i : i + chunk_size
                                        ],
                                        "is_final": False,
                                    },
                                }
                                await asyncio.sleep(
                                    0.01
                                )  # Small delay for streaming effect

                        # Extract content from message
                        content = ""
                        if hasattr(message, "content") and message.content:
                            content = (
                                message.content
                                if isinstance(message.content, str)
                                else str(message.content)
                            )

                        # Check for <think> blocks in content
                        if "<think>" in content:
                            think_match = re.search(
                                r"<think>(.*?)</think>", content, re.DOTALL
                            )
                            if think_match:
                                think_content = think_match.group(1).strip()
                                if (
                                    think_content
                                    and think_content not in current_reasoning_chunk
                                ):
                                    current_reasoning_chunk += "\n" + think_content
                                    reasoning_traces.append(
                                        {
                                            "type": "agent_thought",
                                            "thought": think_content,
                                            "description": "Model thinking",
                                            "timestamp": int(
                                                datetime.now(UTC).timestamp() * 1000
                                            ),
                                        }
                                    )
                                    # Yield the think content
                                    for i in range(0, len(think_content), 50):
                                        yield {
                                            "type": "reasoning_trace",
                                            "data": {
                                                "content": think_content[i : i + 50],
                                                "is_final": False,
                                            },
                                        }
                                        await asyncio.sleep(0.01)
                                # Remove think blocks from content
                                content = re.sub(
                                    r"<think>.*?</think>", "", content, flags=re.DOTALL
                                ).strip()

                        # Simulate streaming for the main content
                        if content:
                            chunk_size = 20  # Characters per chunk for content
                            for i in range(0, len(content), chunk_size):
                                yield {
                                    "type": "content_chunk",
                                    "data": {
                                        "content": content[i : i + chunk_size],
                                        "is_final": False,
                                    },
                                }
                                await asyncio.sleep(
                                    0.01
                                )  # Small delay for streaming effect

                        # Extract token usage
                        if hasattr(response, "usage") and response.usage:
                            usage = response.usage
                            if hasattr(usage, "prompt_tokens"):
                                token_usage["input_tokens"] = usage.prompt_tokens or 0
                            if hasattr(usage, "completion_tokens"):
                                token_usage["output_tokens"] = (
                                    usage.completion_tokens or 0
                                )
                            if hasattr(usage, "total_tokens"):
                                token_usage["total_tokens"] = usage.total_tokens or 0

                        # Final content chunk
                        yield {
                            "type": "content_chunk",
                            "data": {"content": "", "is_final": True},
                        }

                        # Skip the streaming loop since we handled everything
                        # Jump to finalization
                        if reasoning_traces:
                            yield {
                                "type": "reasoning_trace",
                                "data": {
                                    "content": "",
                                    "is_final": True,
                                    "traces": reasoning_traces,
                                },
                            }

                        yield {
                            "type": "token_usage",
                            "data": token_usage,
                        }
                        return  # Exit the function after non-streaming handling

            # Standard streaming mode (when reasoning display is disabled)
            first_chunk_logged = False
            async for chunk in client.astream(litellm_messages):
                # LiteLLM returns ModelResponse objects with choices
                if not chunk or not hasattr(chunk, "choices") or not chunk.choices:
                    continue

                # Track last chunk for final reasoning extraction
                last_chunk = chunk

                # Debug: Log chunk structure for first chunk to understand structure
                if not first_chunk_logged:
                    logger.info(
                        f"[REASONING DEBUG] First chunk structure: {type(chunk)}"
                    )
                    if chunk.choices:
                        choice = chunk.choices[0]
                        logger.info(f"[REASONING DEBUG] Choice attrs: {dir(choice)}")
                        if hasattr(choice, "delta") and choice.delta:
                            delta = choice.delta
                            logger.info(
                                f"[REASONING DEBUG] Delta type: {type(delta)}, attrs: {dir(delta)}"
                            )
                            if hasattr(delta, "__dict__"):
                                logger.info(
                                    f"[REASONING DEBUG] Delta __dict__: {delta.__dict__}"
                                )
                        if hasattr(choice, "message") and choice.message:
                            msg = choice.message
                            logger.info(
                                f"[REASONING DEBUG] Message type: {type(msg)}, attrs: {dir(msg)}"
                            )
                            if hasattr(msg, "__dict__"):
                                logger.info(
                                    f"[REASONING DEBUG] Message __dict__: {msg.__dict__}"
                                )
                    first_chunk_logged = True

                delta = chunk.choices[0].delta

                # Extract token usage from LiteLLM response
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = chunk.usage
                    if hasattr(usage, "prompt_tokens"):
                        token_usage["input_tokens"] = usage.prompt_tokens or 0
                    if hasattr(usage, "completion_tokens"):
                        token_usage["output_tokens"] = usage.completion_tokens or 0
                    if hasattr(usage, "total_tokens"):
                        token_usage["total_tokens"] = usage.total_tokens or 0

                # Extract reasoning traces (for models like o1, o3, DeepSeek-R1, Groq gpt-oss)
                # LiteLLM returns reasoning in different formats depending on provider
                reasoning_text = None
                choice = chunk.choices[0]

                # Method 1: Check delta object directly (streaming mode)
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    reasoning_text = delta.reasoning_content
                    logger.info("[REASONING] Found in delta.reasoning_content")
                elif hasattr(delta, "reasoning") and delta.reasoning:
                    reasoning_text = delta.reasoning
                    logger.info("[REASONING] Found in delta.reasoning")

                # Method 2: Check delta.__dict__ (some LiteLLM versions)
                if not reasoning_text and hasattr(delta, "__dict__"):
                    delta_dict = delta.__dict__
                    reasoning_text = (
                        delta_dict.get("reasoning_content")
                        or delta_dict.get("reasoning")
                        or delta_dict.get("reasoning_trace")
                    )
                    if reasoning_text:
                        logger.info("[REASONING] Found in delta.__dict__")

                # Method 3: Check choice.message.reasoning (Groq/OpenAI style - often in final chunk)
                if not reasoning_text and hasattr(choice, "message") and choice.message:
                    msg = choice.message
                    if hasattr(msg, "reasoning") and msg.reasoning:
                        reasoning_text = msg.reasoning
                        logger.info(
                            f"[REASONING] Found in choice.message.reasoning: {len(reasoning_text)} chars"
                        )
                    elif hasattr(msg, "reasoning_content") and msg.reasoning_content:
                        reasoning_text = msg.reasoning_content
                        logger.info(
                            "[REASONING] Found in choice.message.reasoning_content"
                        )
                    elif hasattr(msg, "__dict__"):
                        msg_dict = msg.__dict__
                        reasoning_text = msg_dict.get("reasoning") or msg_dict.get(
                            "reasoning_content"
                        )
                        if reasoning_text:
                            logger.info("[REASONING] Found in choice.message.__dict__")

                # Method 4: Check chunk-level attributes
                if not reasoning_text:
                    if hasattr(chunk, "reasoning") and chunk.reasoning:
                        reasoning_text = chunk.reasoning
                        logger.info("[REASONING] Found at chunk.reasoning")
                    elif hasattr(chunk, "__dict__"):
                        chunk_dict = chunk.__dict__
                        reasoning_text = chunk_dict.get("reasoning") or chunk_dict.get(
                            "reasoning_content"
                        )
                        if reasoning_text:
                            logger.info("[REASONING] Found in chunk.__dict__")

                if reasoning_text:
                    if isinstance(reasoning_text, str) and reasoning_text.strip():
                        current_reasoning_chunk += reasoning_text
                        # Yield reasoning trace event for real-time display
                        yield {
                            "type": "reasoning_trace",
                            "data": {
                                "content": reasoning_text,
                                "is_final": False,
                            },
                        }
                        logger.info(
                            f"[REASONING] Yielded reasoning trace: {len(reasoning_text)} chars"
                        )
                    elif reasoning_text:
                        logger.debug(
                            f"[REASONING] Found but not valid string: {type(reasoning_text)}"
                        )

                # Extract content from delta
                content_text = ""
                chunk_media = []

                if hasattr(delta, "content") and delta.content:
                    if isinstance(delta.content, str):
                        content_text = delta.content
                    elif isinstance(delta.content, list):
                        # Multi-modal content
                        content_text, chunk_media = await _extract_content_and_media(
                            delta.content
                        )

                # Check for reasoning in the message object during streaming
                # Some models provide reasoning in chunk.choices[0].message.reasoning_content
                if (
                    not reasoning_text
                    and hasattr(chunk.choices[0], "message")
                    and chunk.choices[0].message
                ):
                    message_obj = chunk.choices[0].message
                    chunk_reasoning = None

                    # Check for reasoning_content first (DeepSeek), then reasoning (OpenAI o1)
                    if (
                        hasattr(message_obj, "reasoning_content")
                        and message_obj.reasoning_content
                    ):
                        chunk_reasoning = message_obj.reasoning_content
                    elif hasattr(message_obj, "reasoning") and message_obj.reasoning:
                        chunk_reasoning = message_obj.reasoning
                    elif hasattr(message_obj, "__dict__"):
                        msg_dict = message_obj.__dict__
                        chunk_reasoning = msg_dict.get(
                            "reasoning_content"
                        ) or msg_dict.get("reasoning")

                    if (
                        chunk_reasoning
                        and isinstance(chunk_reasoning, str)
                        and chunk_reasoning.strip()
                    ):
                        # Avoid duplicates - only add if it's new content
                        if chunk_reasoning not in current_reasoning_chunk:
                            current_reasoning_chunk += chunk_reasoning
                            logger.debug(
                                f"Found reasoning in chunk message: {len(chunk_reasoning)} chars"
                            )
                            yield {
                                "type": "reasoning_trace",
                                "data": {
                                    "content": chunk_reasoning,
                                    "is_final": False,
                                },
                            }

                if not content_text and not chunk_media and not reasoning_text:
                    continue

                # Check for inline thinking tags (e.g., <think>...</think> used by DeepSeek-R1)
                # Parse and extract thinking content from the response
                if content_text and not reasoning_text:
                    # Check for opening think tag
                    if "<think>" in content_text or self._in_think_block:
                        self._in_think_block = True

                        # Check for closing tag
                        if "</think>" in content_text:
                            self._in_think_block = False
                            # Extract think content and regular content
                            think_match = re.search(
                                r"<think>(.*?)</think>", content_text, re.DOTALL
                            )
                            if think_match:
                                think_content = think_match.group(1)
                                if think_content.strip():
                                    current_reasoning_chunk += think_content
                                    yield {
                                        "type": "reasoning_trace",
                                        "data": {
                                            "content": think_content,
                                            "is_final": False,
                                        },
                                    }
                                # Remove think block from content
                                content_text = re.sub(
                                    r"<think>.*?</think>",
                                    "",
                                    content_text,
                                    flags=re.DOTALL,
                                ).strip()
                        else:
                            # Still inside think block, accumulate as reasoning
                            # Remove the opening tag if present
                            think_part = content_text.replace("<think>", "")
                            if think_part.strip():
                                current_reasoning_chunk += think_part
                                yield {
                                    "type": "reasoning_trace",
                                    "data": {"content": think_part, "is_final": False},
                                }
                            content_text = (
                                ""  # Don't show think content as regular content
                            )

                event_payload = {
                    "type": "content_chunk",
                    "data": {"content": content_text, "is_final": False},
                }
                if chunk_media:
                    event_payload["data"]["media"] = chunk_media
                yield event_payload

            # After streaming completes, check final chunk for reasoning in message object
            logger.info(
                f"[REASONING] Checking final chunk for reasoning. Has last_chunk: {last_chunk is not None}"
            )
            logger.info(
                f"[REASONING] Current reasoning chunk length: {len(current_reasoning_chunk)}"
            )

            if last_chunk and hasattr(last_chunk, "choices") and last_chunk.choices:
                choice = last_chunk.choices[0]

                # Debug: Log the structure of the last chunk
                logger.info(
                    f"[REASONING] Last chunk - has message: {hasattr(choice, 'message')}, "
                    f"has delta: {hasattr(choice, 'delta')}"
                )
                if hasattr(choice, "message") and choice.message:
                    logger.info(
                        f"[REASONING] Last chunk message attrs: {dir(choice.message)}"
                    )
                    if hasattr(choice.message, "__dict__"):
                        logger.info(
                            f"[REASONING] Last chunk message __dict__: {choice.message.__dict__}"
                        )

                # Check if the final chunk has a complete message object with reasoning
                if hasattr(choice, "message") and choice.message:
                    message_obj = choice.message
                    final_reasoning = None

                    # Check reasoning_content first (DeepSeek), then reasoning (OpenAI)
                    if (
                        hasattr(message_obj, "reasoning_content")
                        and message_obj.reasoning_content
                    ):
                        final_reasoning = message_obj.reasoning_content
                        logger.debug(
                            f"Found reasoning via message_obj.reasoning_content: {type(final_reasoning)}"
                        )
                    elif hasattr(message_obj, "reasoning") and message_obj.reasoning:
                        final_reasoning = message_obj.reasoning
                        logger.debug(
                            f"Found reasoning via message_obj.reasoning: {type(final_reasoning)}"
                        )

                    # Also check if message_obj has __dict__ with reasoning
                    if not final_reasoning and hasattr(message_obj, "__dict__"):
                        msg_dict = message_obj.__dict__
                        final_reasoning = msg_dict.get(
                            "reasoning_content"
                        ) or msg_dict.get("reasoning")
                        if final_reasoning:
                            logger.debug(
                                f"Found reasoning via __dict__: {type(final_reasoning)}"
                            )

                    if final_reasoning:
                        if isinstance(final_reasoning, str) and final_reasoning.strip():
                            # Only add if we haven't already captured it during streaming
                            if final_reasoning not in current_reasoning_chunk:
                                logger.info(
                                    f"Extracted reasoning from final chunk message: {len(final_reasoning)} chars"
                                )
                                current_reasoning_chunk = (
                                    final_reasoning  # Replace with final reasoning
                                )
                                # Send reasoning trace event
                                yield {
                                    "type": "reasoning_trace",
                                    "data": {
                                        "content": final_reasoning,
                                        "is_final": False,
                                    },
                                }
                        elif final_reasoning:
                            logger.debug(
                                f"Reasoning found but not valid string: {type(final_reasoning)}"
                            )
                    else:
                        logger.debug("No reasoning found in final chunk message object")
                else:
                    logger.debug("Last chunk does not have message object")

            # Finalize reasoning trace if we collected any
            if current_reasoning_chunk and current_reasoning_chunk.strip():
                reasoning_traces.append(
                    {
                        "type": "agent_thought",
                        "thought": current_reasoning_chunk.strip(),
                        "description": "Model reasoning process",
                        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                    }
                )
                # Send final reasoning trace event
                yield {
                    "type": "reasoning_trace",
                    "data": {
                        "content": "",
                        "is_final": True,
                    },
                }
                logger.info(
                    f"Finalized reasoning trace: {len(current_reasoning_chunk)} chars, content preview: {current_reasoning_chunk[:100]}..."
                )
            else:
                logger.info(
                    "No reasoning traces found during streaming - checking if model supports reasoning"
                )
                # Log what we checked for debugging
                if last_chunk:
                    logger.debug(f"Last chunk type: {type(last_chunk)}")
                    if hasattr(last_chunk, "choices") and last_chunk.choices:
                        choice = last_chunk.choices[0]
                        logger.debug(
                            f"Last choice has message: {hasattr(choice, 'message')}, has delta: {hasattr(choice, 'delta')}"
                        )
                        if hasattr(choice, "message") and choice.message:
                            msg = choice.message
                            logger.debug(f"Message type: {type(msg)}")
                            if hasattr(msg, "__dict__"):
                                logger.debug(
                                    f"Message attributes: {list(msg.__dict__.keys())}"
                                )

            # Send final chunk
            yield {"type": "content_chunk", "data": {"content": "", "is_final": True}}

            # Send token usage if available
            if token_usage["total_tokens"] > 0:
                yield {"type": "token_usage", "data": token_usage}

            # Send reasoning traces if available
            if reasoning_traces:
                yield {"type": "reasoning_traces", "data": {"traces": reasoning_traces}}

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            raise ValueError(f"AI model error: {e!s}")

    async def generate_conversation_title(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, auto_update: bool = True
    ) -> tuple[str, str, bool]:
        """
        Generate conversation title with graceful fallbacks and de-duplication.

        Returns:
            tuple[str, str, bool]: (Generated title, Model name used, Whether updated to database)
        """
        logger.info(
            f"Generating title for conversation {conversation_id}, user {user_id}, auto_update={auto_update}"
        )

        conversation = await self.conversation_service.get_conversation_with_model(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        if not conversation:
            logger.warning(
                f"Conversation {conversation_id} not found for title generation"
            )
            raise ValueError("Conversation not found or access denied")

        # Helpers
        def build_fallback_title(message_content: str) -> str:
            """Create a deterministic, short title from the first user message."""
            snippet = " ".join(message_content.replace("\n", " ").split()).strip()
            if not snippet:
                return f"Conversation – {datetime.now():%b %d}"

            words = snippet.split()[:12]
            title = " ".join(words)
            title = title[:60].rstrip()
            if not title:
                return f"Conversation – {datetime.now():%b %d}"
            return title.title()

        async def ensure_unique_title(base_title: str) -> str:
            """Avoid duplicates for the same user by suffixing."""
            result = await self.session.execute(
                select(Conversation.title).where(
                    Conversation.user_id == user_id,
                    Conversation.id != conversation_id,
                    Conversation.title.ilike(f"{base_title}%"),
                )
            )
            existing_titles = {row[0] for row in result.all()}
            if base_title not in existing_titles:
                return base_title

            suffix = 2
            while True:
                candidate = f"{base_title} ({suffix})"
                if candidate not in existing_titles:
                    return candidate
                suffix += 1

        # Get system configured title generation model ID
        raw_title_model_id = await config_service.get_title_generation_model_id(
            self.session
        )

        title_model_id: str | None = None
        if isinstance(raw_title_model_id, str):
            candidate = raw_title_model_id.strip()
            if candidate and candidate.lower() != "null":
                title_model_id = candidate

        # Determine which model to use (may be None if not configured)
        title_model = None
        use_llm_title_generation = False

        if title_model_id:
            try:
                uuid.UUID(title_model_id)
            except Exception:
                logger.warning(
                    "Configured title model ID is not a valid UUID (%s); using fallback",
                    title_model_id,
                )
                title_model_id = None

        if title_model_id:
            title_model_result = await self.session.execute(
                select(Model)
                .options(selectinload(Model.provider))
                .where(
                    and_(
                        Model.id == uuid.UUID(title_model_id), Model.status == "ACTIVE"
                    )
                )
            )
            title_model = title_model_result.scalar_one_or_none()

            if title_model:
                use_llm_title_generation = True
                logger.debug(
                    "Using configured title model %s for title generation",
                    title_model.name,
                )
            else:
                logger.warning(
                    "Configured title model ID %s not found or inactive, using fallback",
                    title_model_id,
                )
        else:
            logger.debug("No title model configured, using fallback title generation")

        # Get first user message content as context
        messages_result = await self.session.execute(
            select(Message)
            .where(
                and_(
                    Message.conversation_id == conversation_id,
                    Message.message_type == MessageTypeEnum.USER,
                )
            )
            .order_by(Message.created_at.asc())
            .limit(1)
        )
        messages = messages_result.scalars().all()

        if not messages:
            logger.warning(
                f"No messages found in conversation {conversation_id} for title generation"
            )
            raise ValueError("No messages found in conversation")

        first_user_message = messages[0]

        # Prepare fallback title early
        fallback_base_title = build_fallback_title(first_user_message.content)
        fallback_title = await ensure_unique_title(fallback_base_title)

        title: str | None = None
        model_used: str = "fallback"
        updated = False

        # Try LLM-based title generation only if configured
        if use_llm_title_generation and title_model:
            try:
                instruction = (
                    "You are a professional conversation title generator. Based on the user's conversation, "
                    "you first identify the language used, then generate a concise and meaningful title. "
                    "Titles should be between 3 and 18 words, avoiding quotation marks or special characters."
                )
                combined_user_content = (
                    f"{instruction}\n\n"
                    + "--- Conversation starts below ---\n"
                    + first_user_message.content
                )
                chat_messages = [
                    ChatMessage(role=MessageRole.USER, content=combined_user_content)
                ]

                client = create_chat_model(
                    provider=title_model.provider,
                    model_name=title_model.name,
                    temperature=0.3,
                    max_tokens=50,
                )

                litellm_messages = [msg.to_litellm_message() for msg in chat_messages]
                response = await client.ainvoke(litellm_messages)

                # Extract content from LiteLLM response
                if hasattr(response, "choices") and response.choices:
                    title = response.choices[0].message.content.strip()
                else:
                    title = None

                if title:
                    model_used = title_model.name
                    logger.info(
                        "Generated title for conversation %s: '%s' using model %s",
                        conversation_id,
                        title,
                        model_used,
                    )
                else:
                    logger.warning(
                        "LLM returned empty title for conversation %s, using fallback",
                        conversation_id,
                    )
            except Exception as e:
                logger.warning(
                    "Title generation via model failed for conversation %s: %s. Falling back to heuristic.",
                    conversation_id,
                    e,
                )
                title = None
        else:
            logger.debug(
                "Skipping LLM title generation for conversation %s (not configured or disabled)",
                conversation_id,
            )

        # Apply fallback if needed
        if not title:
            title = fallback_title
            model_used = model_used or "fallback"
            logger.info(
                "Using fallback title for conversation %s: '%s'",
                conversation_id,
                title,
            )

        # Ensure final title is unique for this user
        unique_title = await ensure_unique_title(title)

        if auto_update:
            try:
                conversation.title = unique_title
                await self.session.commit()
                updated = True
                logger.debug(
                    "Updated conversation %s title in database to '%s'",
                    conversation_id,
                    unique_title,
                )
            except Exception as e:
                logger.warning(
                    "Failed to update conversation %s title: %s",
                    conversation_id,
                    e,
                )
                await self.session.rollback()
                updated = False

        return unique_title, model_used, updated

    async def delete_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        return await self.conversation_service.delete_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
        )

    async def archive_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        return await self.conversation_service.archive_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
        )
