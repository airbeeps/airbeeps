import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_pagination import Page
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from airbeeps.assistants.models import Assistant, Conversation, Message
from airbeeps.auth import current_active_user
from airbeeps.chat.service import LangchainChatService
from airbeeps.database import get_async_session
from airbeeps.users.models import User

from .schemas import (
    AnalyticsStatsResponse,
    ChartDataPoint,
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    DashboardStatsResponse,
    MessageResponse,
)

router = APIRouter()


# Conversation endpoints
@router.get(
    "/conversations",
    response_model=Page[ConversationResponse],
    summary="List conversations",
)
async def list_conversations(
    assistant_id: uuid.UUID | None = Query(None, description="Filter by assistant"),
    status: str | None = Query("ACTIVE", description="Filter by status"),
    search: str | None = Query(None, description="Search in title"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """List user's conversations with pagination and filtering"""
    from sqlalchemy import func

    query = select(Conversation).options(joinedload(Conversation.assistant))

    # Apply filters
    if assistant_id:
        query = query.where(Conversation.assistant_id == assistant_id)

    if status:
        query = query.where(Conversation.status == status)

    if search:
        search_term = f"%{search}%"
        query = query.where(Conversation.title.ilike(search_term))

    query = query.order_by(Conversation.updated_at.desc())

    # Get total count
    count_query = select(func.count()).select_from(Conversation)
    if assistant_id:
        count_query = count_query.where(Conversation.assistant_id == assistant_id)
    if status:
        count_query = count_query.where(Conversation.status == status)
    if search:
        search_term = f"%{search}%"
        count_query = count_query.where(Conversation.title.ilike(search_term))

    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    query = query.limit(size).offset((page - 1) * size)

    # Execute query
    result = await session.execute(query)
    conversations = result.scalars().unique().all()

    # Enrich items with assistant names
    enriched_items = []
    for conversation in conversations:
        # Get assistant name - the assistant should be loaded via joinedload
        assistant_name = None
        if conversation.assistant:
            assistant_name = conversation.assistant.name

        # Convert to response dict and add assistant_name
        conv_dict = {
            "id": conversation.id,
            "title": conversation.title,
            "assistant_id": conversation.assistant_id,
            "user_id": conversation.user_id,
            "status": conversation.status,
            "last_message_at": conversation.last_message_at,
            "message_count": conversation.message_count,
            "input_tokens": getattr(conversation, "input_tokens", None),
            "output_tokens": getattr(conversation, "output_tokens", None),
            "total_tokens": getattr(conversation, "total_tokens", None),
            "extra_data": conversation.extra_data,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "assistant_name": assistant_name,
        }
        enriched_items.append(ConversationResponse(**conv_dict))

    # Calculate pages
    pages = (total + size - 1) // size if total > 0 else 0

    # Create page result
    return Page(items=enriched_items, total=total, page=page, size=size, pages=pages)


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    summary="Create a new conversation",
)
async def create_conversation(
    conversation_data: ConversationCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Create a new conversation with an assistant"""
    service = LangchainChatService(session)

    try:
        conversation = await service.create_conversation(
            assistant_id=conversation_data.assistant_id,
            user_id=current_user.id,
            title=conversation_data.title,
        )
        return conversation
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Get a conversation",
)
async def get_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Get a specific conversation"""
    # Direct query to bypass user_id check for admin
    query = (
        select(Conversation)
        .options(joinedload(Conversation.assistant))
        .where(Conversation.id == conversation_id)
    )

    result = await session.execute(query)
    conversation = result.scalars().unique().one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get assistant name
    assistant_name = conversation.assistant.name if conversation.assistant else None

    # Convert to response
    conv_dict = {
        "id": conversation.id,
        "title": conversation.title,
        "assistant_id": conversation.assistant_id,
        "user_id": conversation.user_id,
        "status": conversation.status,
        "last_message_at": conversation.last_message_at,
        "message_count": conversation.message_count,
        "input_tokens": getattr(conversation, "input_tokens", None),
        "output_tokens": getattr(conversation, "output_tokens", None),
        "total_tokens": getattr(conversation, "total_tokens", None),
        "extra_data": conversation.extra_data,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "assistant_name": assistant_name,
    }

    return ConversationResponse(**conv_dict)


@router.put(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Update a conversation",
)
async def update_conversation(
    conversation_id: uuid.UUID,
    conversation_data: ConversationUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Update a conversation"""
    service = LangchainChatService(session)
    conversation = await service.get_conversation(conversation_id, current_user.id)

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Update fields
    update_data = conversation_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(conversation, field, value)

    await session.commit()
    await session.refresh(conversation)
    return conversation


@router.delete("/conversations/{conversation_id}", summary="Delete a conversation")
async def delete_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Delete a conversation"""
    service = LangchainChatService(session)
    success = await service.delete_conversation(conversation_id, current_user.id)

    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"message": "Conversation deleted successfully"}


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=Page[MessageResponse],
    summary="Get conversation messages",
)
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    limit: int | None = Query(50, description="Number of messages to retrieve"),
    offset: int | None = Query(0, description="Offset for pagination"),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Get messages for a conversation"""
    # Direct query to bypass user_id check
    query = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )

    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)

    result = await session.execute(query)
    messages = result.scalars().all()

    return {
        "items": messages,
        "total": len(messages),
        "page": offset // limit + 1 if limit else 1,
        "size": limit or len(messages),
        "pages": 1,
    }


# Dashboard stats endpoint
@router.get(
    "/dashboard/stats",
    response_model=DashboardStatsResponse,
    summary="Get dashboard statistics",
)
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Get aggregated statistics for the admin dashboard"""
    from datetime import datetime, timedelta

    from sqlalchemy import desc, func

    # 1. Overview Metrics
    # Total Users
    total_users_result = await session.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar() or 0

    # Total Conversations
    total_conv_result = await session.execute(select(func.count(Conversation.id)))
    total_conversations = total_conv_result.scalar() or 0

    # Total Documents (ACTIVE)
    from airbeeps.rag.models import Document

    total_docs_result = await session.execute(
        select(func.count(Document.id)).where(Document.status == "ACTIVE")
    )
    total_documents = total_docs_result.scalar() or 0

    # 2. Charts Data (Last 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)

    # User Growth (Daily)
    # Note: SQLite doesn't support date_trunc, using strftime for compatibility if needed,
    # but assuming Postgres for production. For now using generic approach or assuming Postgres.
    # Using func.date() which works in both SQLite and Postgres (mostly)
    user_growth_query = (
        select(
            func.date(User.created_at).label("date"), func.count(User.id).label("count")
        )
        .where(User.created_at >= thirty_days_ago)
        .group_by(func.date(User.created_at))
        .order_by("date")
    )
    user_growth_result = await session.execute(user_growth_query)
    user_growth = [
        {"name": str(row.date), "value": row.count} for row in user_growth_result.all()
    ]

    # 3. Lists
    # Top Assistants (by conversation count)
    top_assistants_query = (
        select(Assistant.name, func.count(Conversation.id).label("conv_count"))
        .join(Conversation, Conversation.assistant_id == Assistant.id)
        .group_by(Assistant.id, Assistant.name)
        .order_by(desc("conv_count"))
        .limit(5)
    )
    top_assistants_result = await session.execute(top_assistants_query)
    top_assistants = [
        {"name": row.name, "count": row.conv_count}
        for row in top_assistants_result.all()
    ]

    # Recent Users
    recent_users_query = select(User).order_by(User.created_at.desc()).limit(5)
    recent_users_result = await session.execute(recent_users_query)
    recent_users = [
        {
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at,
            "avatar_url": user.avatar_url,
        }
        for user in recent_users_result.scalars().all()
    ]

    return DashboardStatsResponse(
        overview={
            "total_users": total_users,
            "total_conversations": total_conversations,
            "total_documents": total_documents,
        },
        user_growth=user_growth,
        top_assistants=top_assistants,
        recent_users=recent_users,
    )


@router.get(
    "/analytics/stats",
    response_model=AnalyticsStatsResponse,
    summary="Get analytics statistics",
)
async def get_analytics_stats(
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
):
    """Get aggregated analytics statistics for the admin dashboard"""
    from collections import defaultdict
    from datetime import datetime, timedelta

    # Fetch messages from last 30 days
    thirty_days_ago = datetime.now() - timedelta(days=30)

    query = (
        select(Message)
        .where(
            Message.created_at >= thirty_days_ago, Message.message_type == "ASSISTANT"
        )
        .order_by(Message.created_at.asc())
    )

    result = await session.execute(query)
    messages = result.scalars().all()

    total_requests = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_execution_time = 0

    # Aggregation buckets
    daily_stats = defaultdict(
        lambda: {"input": 0, "output": 0, "requests": 0, "latency_sum": 0, "date": ""}
    )

    for msg in messages:
        date_str = msg.created_at.strftime("%Y-%m-%d")
        stats = daily_stats[date_str]
        stats["date"] = date_str
        stats["requests"] += 1
        total_requests += 1

        extra = msg.extra_data or {}

        # Token usage
        usage = extra.get("token_usage", {})
        input_t = usage.get("input_tokens", 0)
        output_t = usage.get("output_tokens", 0)

        # If not in token_usage, check legacy fields (unlikely given recent changes but safe)
        if not input_t and not output_t:
            input_t = getattr(msg, "input_tokens", 0) or 0
            output_t = getattr(msg, "output_tokens", 0) or 0

        stats["input"] += input_t
        stats["output"] += output_t

        total_input_tokens += input_t
        total_output_tokens += output_t

        # Latency
        latency = extra.get("execution_time_ms", 0)
        stats["latency_sum"] += latency
        total_execution_time += latency

    # Prepare chart data
    sorted_dates = sorted(daily_stats.keys())

    daily_tokens = []
    daily_requests = []
    daily_latency = []

    for date in sorted_dates:
        stat = daily_stats[date]
        daily_tokens.append(
            {
                "date": date,
                "Input Tokens": stat["input"],
                "Output Tokens": stat["output"],
            }
        )

        daily_requests.append(ChartDataPoint(name=date, value=stat["requests"]))

        avg_latency = (
            stat["latency_sum"] / stat["requests"] if stat["requests"] > 0 else 0
        )
        daily_latency.append(ChartDataPoint(name=date, value=round(avg_latency, 2)))

    avg_total_latency = (
        total_execution_time / total_requests if total_requests > 0 else 0
    )

    return AnalyticsStatsResponse(
        total_requests=total_requests,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_execution_time_ms=int(total_execution_time),
        avg_execution_time_ms=round(avg_total_latency, 2),
        daily_tokens=daily_tokens,
        daily_requests=daily_requests,
        daily_latency=daily_latency,
    )
