from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db
from app.dependencies.role_dependencies import candidate_only
from app.schema.common import ResponseSchema, success_response
from app.schema.messaging import ComposeMessageRequest, SendReplyRequest
from app.service.messaging_service import MessagingService

router = APIRouter(
    prefix="/candidate/messages",
    tags=["My Messages"],
)


def _get_user_id(payload: dict = Depends(candidate_only)) -> UUID:
    raw_user_id = payload.get("user_id")
    if not raw_user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing user_id in token")
    return UUID(str(raw_user_id))


@router.get("", response_model=ResponseSchema, response_model_exclude_none=True)
async def list_conversations(
    search: Optional[str] = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await MessagingService.list_conversations(session, user_id, search, page, page_size)
    return success_response(
        message="Conversations fetched successfully",
        data=result.model_dump(),
    )


@router.patch("/read-all", response_model=ResponseSchema, response_model_exclude_none=True)
async def mark_all_read(
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await MessagingService.mark_all_read(session, user_id)
    return success_response(
        message="All conversations marked as read",
        data=result.model_dump(),
    )


@router.get("/companies", response_model=ResponseSchema, response_model_exclude_none=True)
async def list_messageable_companies(
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await MessagingService.list_messageable_companies(session, user_id)
    return success_response(
        message="Messageable companies fetched successfully",
        data=result.model_dump(),
    )


@router.post("", response_model=ResponseSchema, response_model_exclude_none=True, status_code=201)
async def compose_conversation(
    body: ComposeMessageRequest,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await MessagingService.compose(session, user_id, body)
    return ResponseSchema(
        success=True,
        status=201,
        message="Message sent successfully",
        data=result.model_dump(),
    )


@router.get("/{thread_id}", response_model=ResponseSchema, response_model_exclude_none=True)
async def get_conversation(
    thread_id: str,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await MessagingService.get_conversation(session, user_id, thread_id)
    return success_response(
        message="Conversation fetched successfully",
        data=result.model_dump(),
    )


@router.post("/{thread_id}/messages", response_model=ResponseSchema, response_model_exclude_none=True, status_code=201)
async def send_reply(
    thread_id: str,
    body: SendReplyRequest,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await MessagingService.send_reply(session, user_id, thread_id, body.message)
    return ResponseSchema(
        success=True,
        status=201,
        message="Reply sent successfully",
        data=result.model_dump(),
    )


@router.patch("/{thread_id}/read", response_model=ResponseSchema, response_model_exclude_none=True)
async def mark_conversation_read(
    thread_id: str,
    user_id: UUID = Depends(_get_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await MessagingService.mark_thread_read(session, user_id, thread_id)
    return success_response(
        message="Conversation marked as read",
        data=result.model_dump(),
    )