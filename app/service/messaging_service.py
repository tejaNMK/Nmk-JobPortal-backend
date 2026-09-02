from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.candidate_model.message import Message
from app.repository.candidate_repository.message_repo import MessageRepo
from app.schema.messaging import (
    ComposeMessageRequest,
    ComposeMessageResponse,
    ConversationDetailResponse,
    ConversationListItem,
    ConversationListResponse,
    ConversationParticipant,
    MarkReadResponse,
    MessageableCompaniesResponse,
    MessageableCompany,
    MessageItem,
    SendReplyResponse,
)

SYSTEM_SENDER_NAME = "JobsPortal Concierge"


def _full_name(user) -> str:
    if not user:
        return ""
    parts = [
        getattr(user, "first_name", None),
        getattr(user, "last_name", None),
    ]
    return " ".join(p for p in parts if p) or ""


class MessagingService:

    # ── Candidate resolution ────────────────────────────────────────────────
    @staticmethod
    async def _get_candidate(session: AsyncSession, user_id: UUID):
        profile = await MessageRepo.get_candidate_profile(session, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Candidate profile not found")
        return profile

    # ── Participant resolution ──────────────────────────────────────────────
    @staticmethod
    async def _build_participants(
        session: AsyncSession, other_user_ids: List[Optional[UUID]]
    ) -> Dict[Optional[UUID], ConversationParticipant]:
        real_ids = [uid for uid in other_user_ids if uid is not None]
        employer_map = await MessageRepo.get_employer_company_by_user_ids(session, real_ids)

        unresolved_ids = [uid for uid in real_ids if uid not in employer_map]
        fallback_users = await MessageRepo.get_users_by_ids(session, unresolved_ids) if unresolved_ids else {}

        participants: Dict[Optional[UUID], ConversationParticipant] = {
            None: ConversationParticipant(kind="SYSTEM", name=SYSTEM_SENDER_NAME)
        }

        for uid in real_ids:
            if uid in employer_map:
                employer, company, user = employer_map[uid]
                participants[uid] = ConversationParticipant(
                    kind="EMPLOYER",
                    employer_user_id=str(uid),
                    name=_full_name(user) or (company.company_name if company else "Recruiter"),
                    company_id=company.company_id if company else None,
                    company_name=company.company_name if company else None,
                    company_logo=(company.logo_url or company.logo_path) if company else None,
                )
            elif uid in fallback_users:
                user = fallback_users[uid]
                participants[uid] = ConversationParticipant(
                    kind="EMPLOYER",
                    employer_user_id=str(uid),
                    name=_full_name(user) or "Recruiter",
                )
            else:
                participants[uid] = ConversationParticipant(kind="SYSTEM", name=SYSTEM_SENDER_NAME)

        return participants

    @staticmethod
    def _to_message_item(message: Message, candidate_user_id: UUID, participant: ConversationParticipant) -> MessageItem:
        is_mine = message.sender_id == candidate_user_id
        return MessageItem(
            message_id=message.message_id,
            thread_id=message.thread_id,
            from_me=is_mine,
            is_system=(not is_mine and message.sender_id is None),
            sender_name=None if is_mine else participant.name,
            body=message.message_body or "",
            sent_at=message.sent_at,
            read=message.read_flag,
        )

    # ── List conversations ───────────────────────────────────────────────────
    @staticmethod
    async def list_conversations(
        session: AsyncSession,
        user_id: UUID,
        search: Optional[str],
        page: int,
        page_size: int,
    ) -> ConversationListResponse:
        await MessagingService._get_candidate(session, user_id)

        thread_ids, total = await MessageRepo.list_thread_ids_for_user(session, user_id, search, page, page_size)

        threads = await MessageRepo.get_threads_by_ids(session, thread_ids)
        last_messages = await MessageRepo.get_last_messages_for_threads(session, thread_ids)
        unread_counts = await MessageRepo.get_unread_counts_for_threads(session, thread_ids, user_id)
        other_party_ids = await MessageRepo.get_other_party_ids_for_threads(session, thread_ids, user_id)
        total_unread = await MessageRepo.count_total_unread(session, user_id)

        participants = await MessagingService._build_participants(session, list(other_party_ids.values()))

        items: List[ConversationListItem] = []
        for thread_id in thread_ids:
            thread = threads.get(thread_id)
            last_msg = last_messages.get(thread_id)
            participant = participants.get(other_party_ids.get(thread_id), participants[None])

            items.append(
                ConversationListItem(
                    thread_id=thread_id,
                    subject=(thread.subject if thread and thread.subject else "Conversation"),
                    participant=participant,
                    last_message_preview=last_msg.message_body if last_msg else None,
                    last_message_at=last_msg.sent_at if last_msg else (thread.created_at if thread else None),
                    last_message_is_mine=(last_msg.sender_id == user_id) if last_msg else False,
                    unread_count=unread_counts.get(thread_id, 0),
                )
            )

        return ConversationListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_unread=total_unread,
        )

    # ── Conversation detail ──────────────────────────────────────────────────
    @staticmethod
    async def get_conversation(session: AsyncSession, user_id: UUID, thread_id: str) -> ConversationDetailResponse:
        await MessagingService._get_candidate(session, user_id)

        thread = await MessageRepo.get_thread(session, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if not await MessageRepo.user_is_participant(session, thread_id, user_id):
            raise HTTPException(status_code=404, detail="Conversation not found")

        messages = await MessageRepo.get_messages_for_thread(session, thread_id)

        other_party_map = await MessageRepo.get_other_party_ids_for_threads(session, [thread_id], user_id)
        other_user_id = other_party_map.get(thread_id)
        participants = await MessagingService._build_participants(session, [other_user_id])
        participant = participants.get(other_user_id, participants[None])

        # Opening the conversation marks the candidate's unread messages as read.
        await MessageRepo.mark_thread_read(session, thread_id, user_id)
        for m in messages:
            if m.receiver_id == user_id:
                m.read_flag = True

        items = [MessagingService._to_message_item(m, user_id, participant) for m in messages]

        return ConversationDetailResponse(
            thread_id=thread_id,
            subject=thread.subject or "Conversation",
            participant=participant,
            messages=items,
        )

    # ── Send reply ───────────────────────────────────────────────────────────
    @staticmethod
    async def send_reply(session: AsyncSession, user_id: UUID, thread_id: str, body: str) -> SendReplyResponse:
        await MessagingService._get_candidate(session, user_id)

        thread = await MessageRepo.get_thread(session, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if not await MessageRepo.user_is_participant(session, thread_id, user_id):
            raise HTTPException(status_code=404, detail="Conversation not found")

        other_party_map = await MessageRepo.get_other_party_ids_for_threads(session, [thread_id], user_id)
        other_user_id = other_party_map.get(thread_id)

        if other_user_id is None:
            raise HTTPException(status_code=400, detail="This conversation cannot be replied to")

        message = await MessageRepo.create_message(
            session, thread_id=thread_id, sender_id=user_id, receiver_id=other_user_id, body=body.strip()
        )

        participants = await MessagingService._build_participants(session, [other_user_id])
        participant = participants.get(other_user_id, participants[None])

        return SendReplyResponse(message=MessagingService._to_message_item(message, user_id, participant))

    # ── Compose new conversation ─────────────────────────────────────────────
    @staticmethod
    async def list_messageable_companies(session: AsyncSession, user_id: UUID) -> MessageableCompaniesResponse:
        candidate = await MessagingService._get_candidate(session, user_id)
        companies = await MessageRepo.get_messageable_companies(session, candidate.candidate_id)
        return MessageableCompaniesResponse(
            items=[
                MessageableCompany(
                    company_id=c.company_id,
                    company_name=c.company_name,
                    company_logo=c.logo_url or c.logo_path,
                )
                for c in companies
            ]
        )

    @staticmethod
    async def compose(
        session: AsyncSession, user_id: UUID, request: ComposeMessageRequest
    ) -> ComposeMessageResponse:
        candidate = await MessagingService._get_candidate(session, user_id)

        company_row = await MessageRepo.get_employer_company_by_company_id(session, request.company_id)
        if not company_row:
            raise HTTPException(status_code=404, detail="Company not found")
        employer, company, employer_user = company_row

        has_connection = await MessageRepo.candidate_has_connection_to_company(
            session, candidate.candidate_id, request.company_id
        )
        if not has_connection:
            raise HTTPException(
                status_code=403,
                detail="You can only message companies you have applied to or been invited by",
            )

        thread = await MessageRepo.create_thread(session, subject=request.subject.strip())
        message = await MessageRepo.create_message(
            session,
            thread_id=thread.thread_id,
            sender_id=user_id,
            receiver_id=employer.user_id,
            body=request.message.strip(),
        )

        participants = await MessagingService._build_participants(session, [employer.user_id])
        participant = participants.get(employer.user_id, participants[None])

        return ComposeMessageResponse(
            thread_id=thread.thread_id,
            message=MessagingService._to_message_item(message, user_id, participant),
        )

    # ── Mark read ────────────────────────────────────────────────────────────
    @staticmethod
    async def mark_thread_read(session: AsyncSession, user_id: UUID, thread_id: str) -> MarkReadResponse:
        await MessagingService._get_candidate(session, user_id)

        thread = await MessageRepo.get_thread(session, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation not found")

        count = await MessageRepo.mark_thread_read(session, thread_id, user_id)
        return MarkReadResponse(thread_id=thread_id, marked_read=count)

    @staticmethod
    async def mark_all_read(session: AsyncSession, user_id: UUID) -> MarkReadResponse:
        await MessagingService._get_candidate(session, user_id)
        count = await MessageRepo.mark_all_read(session, user_id)
        return MarkReadResponse(marked_read=count)