import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import paginate as sqlalchemy_paginate
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from airbeeps.agents.tools.registry import LocalToolRegistry
from airbeeps.ai_models.models import Model
from airbeeps.assistants.models import (
    Assistant,
    AssistantModeEnum,
    Conversation,
    Message,
    MessageTypeEnum,
)
from airbeeps.auth import current_active_user
from airbeeps.database import get_async_session
from airbeeps.rag.models import KnowledgeBase
from airbeeps.users.models import User

from .schemas import (
    AssistantCreate,
    AssistantResponse,
    AssistantStatusEnum,
    AssistantTranslationsResponse,
    AssistantUpdate,
    UpdateTranslationRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _log_http_error(message: str, exc: HTTPException) -> None:
    """Log HTTP exceptions with detail for easier debugging."""
    logger.warning("%s (status=%s detail=%s)", message, exc.status_code, exc.detail)


def _log_unexpected_error(message: str, exc: Exception) -> None:
    """Log unexpected exceptions with stack traces."""
    logger.exception("%s: %s", message, exc)


def _log_http_error(message: str, exc: HTTPException) -> None:
    """Log HTTP exceptions with detail for easier debugging."""
    logger.warning("%s (status=%s detail=%s)", message, exc.status_code, exc.detail)


def _log_unexpected_error(message: str, exc: Exception) -> None:
    """Log unexpected exceptions with stack traces."""
    logger.exception("%s: %s", message, exc)


SORTABLE_FIELDS = {
    "name": Assistant.name,
    "status": Assistant.status,
    "created_at": Assistant.created_at,
    "updated_at": Assistant.updated_at,
}

DEFAULT_SORT_FIELD = "updated_at"
DEFAULT_SORT_DESC = True


# Tool listing schemas
class LocalToolInfo(BaseModel):
    name: str
    description: str


class MCPServerInfo(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None


class AvailableToolsResponse(BaseModel):
    local_tools: list[LocalToolInfo]
    mcp_servers: list[MCPServerInfo]


@router.get(
    "/assistants", response_model=Page[AssistantResponse], summary="List assistants"
)
async def list_assistants(
    status: AssistantStatusEnum | None = Query(None, description="Filter by status"),
    is_public: bool | None = Query(None, description="Filter by public/private"),
    search: str | None = Query(None, description="Search in name or description"),
    mode: AssistantModeEnum | None = Query(None, description="Filter by mode"),
    sort_by: str | None = Query(
        None, description="Sort field: name, status, created_at, updated_at"
    ),
    sort_desc: bool | None = Query(None, description="Sort descending if true"),
    params: Params = Depends(),
    session: AsyncSession = Depends(get_async_session),
):
    """List assistants with filtering"""
    try:
        logger.debug(
            "Listing assistants status=%s is_public=%s search=%s mode=%s",
            status,
            is_public,
            search,
            mode,
        )
        query = select(Assistant).options(
            selectinload(Assistant.model), selectinload(Assistant.owner)
        )

        # Apply filters
        if status:
            query = query.where(Assistant.status == status)

        if is_public is not None:
            query = query.where(Assistant.is_public == is_public)

        if search:
            search_term = f"%{search}%"
            query = query.where(
                (Assistant.name.ilike(search_term))
                | (Assistant.description.ilike(search_term))
            )

        if mode:
            query = query.where(Assistant.mode == mode)

        sort_field_key = sort_by if sort_by in SORTABLE_FIELDS else DEFAULT_SORT_FIELD
        if sort_desc is None:
            sort_desc_value = (
                DEFAULT_SORT_DESC if sort_by not in SORTABLE_FIELDS else False
            )
        else:
            sort_desc_value = sort_desc

        order_column = SORTABLE_FIELDS[sort_field_key]
        order_clause = order_column.desc() if sort_desc_value else order_column.asc()
        query = query.order_by(order_clause, Assistant.id.desc())

        # Get paginated results
        page_result = await sqlalchemy_paginate(session, query, params)

        # Create new page result with enriched items
        return Page(
            items=page_result.items,
            total=page_result.total,
            page=page_result.page,
            size=page_result.size,
            pages=page_result.pages,
        )
    except HTTPException as exc:
        _log_http_error("Failed to list assistants", exc)
        raise
    except Exception as exc:
        _log_unexpected_error("Unexpected error listing assistants", exc)
        raise


@router.post(
    "/assistants", response_model=AssistantResponse, summary="Create a new assistant"
)
async def create_assistant(
    assistant_data: AssistantCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Create a new assistant"""
    from airbeeps.agents.models import MCPServerConfig

    try:
        logger.info(
            "Creating assistant '%s' for user %s", assistant_data.name, current_user.id
        )
        logger.debug(
            "Assistant data: model_id=%s enable_agent=%s",
            assistant_data.model_id,
            assistant_data.enable_agent,
        )

        # Check if model exists and is active
        model_result = await session.execute(
            select(Model).where(
                (Model.id == assistant_data.model_id) & (Model.status == "ACTIVE")
            )
        )
        if not model_result.scalar_one_or_none():
            logger.warning(
                "Model %s not found or not active for user %s",
                assistant_data.model_id,
                current_user.id,
            )
            raise HTTPException(status_code=400, detail="Model not found or not active")

        knowledge_base_ids = assistant_data.knowledge_base_ids

        if len(knowledge_base_ids) != len(set(knowledge_base_ids)):
            raise HTTPException(
                status_code=400, detail="Duplicate knowledge base IDs provided"
            )

        if knowledge_base_ids:
            kb_result = await session.execute(
                select(KnowledgeBase.id).where(
                    KnowledgeBase.id.in_(knowledge_base_ids),
                    KnowledgeBase.owner_id == current_user.id,
                    KnowledgeBase.status == "ACTIVE",
                )
            )
            valid_ids = set(kb_result.scalars().all())
            missing_ids = set(knowledge_base_ids) - valid_ids
            if missing_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Knowledge base not found or not accessible",
                )

        # Validate MCP server IDs
        mcp_server_ids = assistant_data.mcp_server_ids or []
        mcp_servers = []
        if mcp_server_ids:
            if len(mcp_server_ids) != len(set(mcp_server_ids)):
                raise HTTPException(
                    status_code=400, detail="Duplicate MCP server IDs provided"
                )

            mcp_result = await session.execute(
                select(MCPServerConfig).where(
                    MCPServerConfig.id.in_(mcp_server_ids),
                    MCPServerConfig.is_active.is_(True),
                )
            )
            mcp_servers = list(mcp_result.scalars().all())
            found_ids = {mcp.id for mcp in mcp_servers}
            missing_ids = set(mcp_server_ids) - found_ids
            if missing_ids:
                raise HTTPException(
                    status_code=400, detail="MCP server not found or not active"
                )

        assistant_payload = assistant_data.model_dump(
            exclude={"knowledge_base_ids", "mcp_server_ids"}
        )
        assistant = Assistant(**assistant_payload, owner_id=current_user.id)

        assistant.knowledge_base_ids = [str(kb_id) for kb_id in knowledge_base_ids]

        # Enforce mode semantics
        if assistant.mode == AssistantModeEnum.RAG:
            if not assistant.knowledge_base_ids:
                raise HTTPException(
                    status_code=400,
                    detail="RAG mode requires at least one knowledge base",
                )
        else:
            # GENERAL mode: ensure no KBs are attached
            assistant.knowledge_base_ids = []
            assistant.rag_config = {}

        # If inheriting global RAG defaults, do not store per-assistant rag_config overrides.
        if getattr(assistant, "use_global_rag_defaults", True):
            assistant.rag_config = {}
        assistant.mcp_servers = mcp_servers

        session.add(assistant)
        await session.commit()

        result = await session.execute(
            select(Assistant)
            .options(
                selectinload(Assistant.model),
                selectinload(Assistant.owner),
                selectinload(Assistant.mcp_servers),
            )
            .where(Assistant.id == assistant.id)
        )
        assistant = result.scalar_one()

        return assistant
    except HTTPException as exc:
        _log_http_error("Failed to create assistant", exc)
        raise
    except Exception as exc:
        _log_unexpected_error("Unexpected error creating assistant", exc)
        raise


@router.get(
    "/assistants/{assistant_id}",
    response_model=AssistantResponse,
    summary="Get an assistant",
)
async def get_assistant(
    assistant_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Get a specific assistant by ID"""
    try:
        result = await session.execute(
            select(Assistant)
            .options(
                selectinload(Assistant.model),
                selectinload(Assistant.owner),
                selectinload(Assistant.mcp_servers),
            )
            .where(Assistant.id == assistant_id)
        )
        assistant = result.scalar_one_or_none()

        if not assistant:
            raise HTTPException(status_code=404, detail="Assistant not found")

        # Admin router: superusers can access any assistant. Otherwise: owner or public.
        if (
            assistant.owner_id != current_user.id
            and not assistant.is_public
            and not current_user.is_superuser
        ):
            raise HTTPException(status_code=403, detail="Access denied")

        return assistant
    except HTTPException as exc:
        _log_http_error(
            f"Failed to get assistant {assistant_id} for user {current_user.id}", exc
        )
        raise
    except Exception as exc:
        _log_unexpected_error(
            f"Unexpected error retrieving assistant {assistant_id}", exc
        )
        raise


@router.put(
    "/assistants/{assistant_id}",
    response_model=AssistantResponse,
    summary="Update an assistant",
)
async def update_assistant(
    assistant_id: uuid.UUID,
    assistant_data: AssistantUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Update an assistant"""
    from airbeeps.agents.models import MCPServerConfig

    try:
        logger.info("Updating assistant %s by user %s", assistant_id, current_user.id)

        result = await session.execute(
            select(Assistant)
            .options(
                selectinload(Assistant.model),
                selectinload(Assistant.owner),
                selectinload(Assistant.mcp_servers),
            )
            .where(Assistant.id == assistant_id)
        )
        assistant = result.scalar_one_or_none()

        if not assistant:
            logger.warning("Assistant %s not found for update", assistant_id)
            raise HTTPException(status_code=404, detail="Assistant not found")

        # Admin router: superusers can update any assistant.
        if assistant.owner_id != current_user.id and not current_user.is_superuser:
            logger.warning(
                "User %s denied permission to update assistant %s",
                current_user.id,
                assistant_id,
            )
            raise HTTPException(
                status_code=403, detail="Only owner can update assistant"
            )

        # Check if model exists and is active if model_id is being updated
        if assistant_data.model_id and assistant_data.model_id != assistant.model_id:
            model_result = await session.execute(
                select(Model).where(
                    (Model.id == assistant_data.model_id) & (Model.status == "ACTIVE")
                )
            )
            if not model_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=400, detail="Model not found or not active"
                )

        update_data = assistant_data.model_dump(exclude_unset=True)
        mode_provided = "mode" in update_data
        knowledge_base_ids = update_data.pop("knowledge_base_ids", None)
        mcp_server_ids = update_data.pop("mcp_server_ids", None)

        # Update primitive fields
        for field, value in update_data.items():
            setattr(assistant, field, value)

        if knowledge_base_ids is not None:
            if len(knowledge_base_ids) != len(set(knowledge_base_ids)):
                raise HTTPException(
                    status_code=400, detail="Duplicate knowledge base IDs provided"
                )

            if knowledge_base_ids:
                logger.debug(
                    "Validating KB ids on update: %s (assistant=%s user=%s superuser=%s)",
                    knowledge_base_ids,
                    assistant_id,
                    current_user.id,
                    current_user.is_superuser,
                )
                kb_query = select(KnowledgeBase.id).where(
                    KnowledgeBase.id.in_(knowledge_base_ids),
                    KnowledgeBase.status == "ACTIVE",
                )
                if not current_user.is_superuser:
                    kb_query = kb_query.where(KnowledgeBase.owner_id == current_user.id)
                kb_result = await session.execute(kb_query)
                valid_ids = set(kb_result.scalars().all())
                missing_ids = set(knowledge_base_ids) - valid_ids
                if missing_ids and not current_user.is_superuser:
                    raise HTTPException(
                        status_code=400,
                        detail="Knowledge base not found or not accessible",
                    )
                if missing_ids and current_user.is_superuser:
                    logger.warning(
                        "Dropping missing KB ids on update (assistant=%s user=%s): %s",
                        assistant_id,
                        current_user.id,
                        list(missing_ids),
                    )

                assistant.knowledge_base_ids = [str(kb_id) for kb_id in valid_ids]
            else:
                assistant.knowledge_base_ids = []

        # Enforce mode semantics (explicit mode wins; otherwise infer from KB attachment updates)
        if mode_provided:
            if assistant.mode == AssistantModeEnum.RAG:
                if not assistant.knowledge_base_ids:
                    raise HTTPException(
                        status_code=400,
                        detail="RAG mode requires at least one knowledge base",
                    )
            else:
                assistant.mode = AssistantModeEnum.GENERAL
                assistant.knowledge_base_ids = []
                assistant.rag_config = {}
        elif knowledge_base_ids is not None:
            assistant.mode = (
                AssistantModeEnum.RAG
                if assistant.knowledge_base_ids
                else AssistantModeEnum.GENERAL
            )

        # If inheriting global RAG defaults, do not store per-assistant rag_config overrides.
        if getattr(assistant, "use_global_rag_defaults", True):
            assistant.rag_config = {}

        # Update MCP servers if provided
        if mcp_server_ids is not None:
            if len(mcp_server_ids) != len(set(mcp_server_ids)):
                raise HTTPException(
                    status_code=400, detail="Duplicate MCP server IDs provided"
                )

            if mcp_server_ids:
                mcp_result = await session.execute(
                    select(MCPServerConfig).where(
                        MCPServerConfig.id.in_(mcp_server_ids),
                        MCPServerConfig.is_active.is_(True),
                    )
                )
                mcp_servers = list(mcp_result.scalars().all())
                found_ids = {mcp.id for mcp in mcp_servers}
                missing_ids = set(mcp_server_ids) - found_ids
                if missing_ids:
                    raise HTTPException(
                        status_code=400, detail="MCP server not found or not active"
                    )
                assistant.mcp_servers = mcp_servers
            else:
                assistant.mcp_servers = []

        await session.commit()

        result = await session.execute(
            select(Assistant)
            .options(
                selectinload(Assistant.model),
                selectinload(Assistant.owner),
                selectinload(Assistant.mcp_servers),
            )
            .where(Assistant.id == assistant_id)
        )
        assistant = result.scalar_one()

        return assistant
    except HTTPException as exc:
        _log_http_error(
            f"Failed to update assistant {assistant_id} for user {current_user.id}", exc
        )
        raise
    except Exception as exc:
        _log_unexpected_error(
            f"Unexpected error updating assistant {assistant_id}", exc
        )
        raise


@router.delete("/assistants/{assistant_id}", summary="Delete an assistant")
async def delete_assistant(
    assistant_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Delete an assistant and all associated conversations"""
    try:
        logger.info("Deleting assistant %s by user %s", assistant_id, current_user.id)
        result = await session.execute(
            select(Assistant).where(Assistant.id == assistant_id)
        )
        assistant = result.scalar_one_or_none()

        if not assistant:
            logger.warning("Assistant %s not found for deletion", assistant_id)
            raise HTTPException(status_code=404, detail="Assistant not found")

        # Admin router: superusers can delete any assistant.
        if assistant.owner_id != current_user.id and not current_user.is_superuser:
            logger.warning(
                "User %s denied permission to delete assistant %s",
                current_user.id,
                assistant_id,
            )
            raise HTTPException(
                status_code=403, detail="Only owner can delete assistant"
            )

        await session.delete(assistant)
        await session.commit()
        logger.info("Successfully deleted assistant %s", assistant_id)
        return {"message": "Assistant deleted successfully"}
    except HTTPException as exc:
        _log_http_error(
            f"Failed to delete assistant {assistant_id} for user {current_user.id}", exc
        )
        raise
    except Exception as exc:
        _log_unexpected_error(
            f"Unexpected error deleting assistant {assistant_id}", exc
        )
        raise


@router.get("/assistants/{assistant_id}/stats", summary="Get assistant statistics")
async def get_assistant_stats(
    assistant_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Get comprehensive statistics for an assistant including usage data."""
    try:
        assistant_result = await session.execute(
            select(Assistant).where(Assistant.id == assistant_id)
        )
        assistant = assistant_result.scalar_one_or_none()

        if not assistant:
            raise HTTPException(status_code=404, detail="Assistant not found")

        # Admin router: superusers can access stats for any assistant. Otherwise: owner or public.
        if (
            assistant.owner_id != current_user.id
            and not assistant.is_public
            and not current_user.is_superuser
        ):
            raise HTTPException(status_code=403, detail="Access denied")

        # Get conversation count
        conv_count_result = await session.execute(
            select(func.count(Conversation.id)).where(
                Conversation.assistant_id == assistant_id
            )
        )
        conversation_count = conv_count_result.scalar() or 0

        # Get active conversation count
        active_conv_result = await session.execute(
            select(func.count(Conversation.id)).where(
                and_(
                    Conversation.assistant_id == assistant_id,
                    Conversation.status == "ACTIVE",
                )
            )
        )
        active_conversations = active_conv_result.scalar() or 0

        # Get all conversation IDs for this assistant
        conv_ids_result = await session.execute(
            select(Conversation.id).where(Conversation.assistant_id == assistant_id)
        )
        conversation_ids = [row[0] for row in conv_ids_result.all()]

        # Initialize usage stats
        total_messages = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_execution_time_ms = 0
        assistant_message_count = 0

        if conversation_ids:
            # Get message count
            msg_count_result = await session.execute(
                select(func.count(Message.id)).where(
                    Message.conversation_id.in_(conversation_ids)
                )
            )
            total_messages = msg_count_result.scalar() or 0

            # Get all assistant messages to extract token/timing data from extra_data
            messages_result = await session.execute(
                select(Message.extra_data).where(
                    and_(
                        Message.conversation_id.in_(conversation_ids),
                        Message.message_type == MessageTypeEnum.ASSISTANT,
                    )
                )
            )

            for (extra_data,) in messages_result.all():
                if extra_data:
                    token_usage = extra_data.get("token_usage", {})
                    total_input_tokens += token_usage.get("input_tokens", 0) or 0
                    total_output_tokens += token_usage.get("output_tokens", 0) or 0
                    exec_time = extra_data.get("execution_time_ms", 0) or 0
                    if exec_time > 0:
                        total_execution_time_ms += exec_time
                        assistant_message_count += 1

        # Calculate average response time
        avg_response_time_ms = (
            total_execution_time_ms / assistant_message_count
            if assistant_message_count > 0
            else 0
        )

        return {
            "assistant_id": assistant_id,
            "total_conversations": conversation_count,
            "active_conversations": active_conversations,
            "total_messages": total_messages,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "avg_response_time_ms": round(avg_response_time_ms, 2),
            "status": assistant.status.value,
            "is_public": assistant.is_public,
            "created_at": assistant.created_at,
        }
    except HTTPException as exc:
        _log_http_error(f"Failed to get assistant stats for {assistant_id}", exc)
        raise
    except Exception as exc:
        _log_unexpected_error(
            f"Unexpected error getting assistant stats {assistant_id}", exc
        )
        raise


@router.get(
    "/agent-tools/available",
    response_model=AvailableToolsResponse,
    summary="List available Agent tools",
)
async def get_available_agent_tools(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """
    Get all available tools (local + MCP) for Agent configuration.
    Local tools are added via agent_enabled_tools field (string array).
    MCP servers are added via mcp_server_ids field (UUID array).
    """
    from airbeeps.agents.models import MCPServerConfig

    try:
        # Get local tools with their descriptions
        local_tools_info = LocalToolRegistry.list_tools_with_info()
        local_tools = [
            LocalToolInfo(name=tool_info["name"], description=tool_info["description"])
            for tool_info in local_tools_info
        ]

        # Get active MCP servers from database
        mcp_result = await session.execute(
            select(MCPServerConfig).where(MCPServerConfig.is_active.is_(True))
        )
        mcp_servers_data = mcp_result.scalars().all()

        mcp_servers = [
            MCPServerInfo(
                id=mcp_server.id,
                name=mcp_server.name,
                description=mcp_server.description,
            )
            for mcp_server in mcp_servers_data
        ]

        return AvailableToolsResponse(local_tools=local_tools, mcp_servers=mcp_servers)
    except HTTPException as exc:
        _log_http_error("Failed to list available agent tools", exc)
        raise
    except Exception as exc:
        _log_unexpected_error("Unexpected error listing available agent tools", exc)
        raise


# Translation management endpoints
@router.get(
    "/assistants/{assistant_id}/translations",
    response_model=AssistantTranslationsResponse,
    summary="Get assistant translations",
)
async def get_assistant_translations(
    assistant_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Get assistant translations for translation management page"""
    assistant = await session.get(Assistant, assistant_id)
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    # Calculate translation progress for each locale
    translatable_fields = ["name", "description", "system_prompt"]
    translation_progress = {}

    if assistant.translations:
        for locale, trans in assistant.translations.items():
            filled = sum(1 for field in translatable_fields if trans.get(field))
            translation_progress[locale] = int(
                (filled / len(translatable_fields)) * 100
            )

    return AssistantTranslationsResponse(
        id=assistant.id,
        default_name=assistant.name,
        default_description=assistant.description,
        default_system_prompt=assistant.system_prompt,
        translations=assistant.translations or {},
        translation_progress=translation_progress,
    )


@router.put(
    "/assistants/{assistant_id}/translations/{locale}",
    summary="Update assistant translation for a locale",
)
async def update_assistant_translation(
    assistant_id: uuid.UUID,
    locale: str,
    translation_data: UpdateTranslationRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """Update translation for a specific locale"""
    assistant = await session.get(Assistant, assistant_id)
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    # Initialize translations dict if needed
    if not assistant.translations:
        assistant.translations = {}

    # Update translation data
    locale_data = assistant.translations.get(locale, {})

    if translation_data.name is not None:
        locale_data["name"] = translation_data.name
    if translation_data.description is not None:
        locale_data["description"] = translation_data.description
    if translation_data.system_prompt is not None:
        locale_data["system_prompt"] = translation_data.system_prompt

    assistant.translations[locale] = locale_data

    # Mark as modified for SQLAlchemy to detect change
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(assistant, "translations")

    await session.commit()

    return {"message": "Translation updated successfully", "locale": locale}


@router.delete(
    "/assistants/{assistant_id}/translations/{locale}",
    summary="Delete assistant translation for a locale",
)
async def delete_assistant_translation(
    assistant_id: uuid.UUID,
    locale: str,
    session: AsyncSession = Depends(get_async_session),
):
    """Delete translation for a specific locale"""
    assistant = await session.get(Assistant, assistant_id)
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    if assistant.translations and locale in assistant.translations:
        del assistant.translations[locale]

        # Mark as modified for SQLAlchemy to detect change
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(assistant, "translations")

        await session.commit()
        return {"message": "Translation deleted successfully", "locale": locale}

    raise HTTPException(
        status_code=404, detail=f"Translation for locale '{locale}' not found"
    )
