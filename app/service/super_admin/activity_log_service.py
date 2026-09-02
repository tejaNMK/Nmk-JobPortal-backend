import inspect
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.model.activity_log import ActivityLog
from app.model.authentication.role import Role
from app.model.authentication.user_role import UsersRole
from app.repository.super_admin.dashboard_api_repo import ActivityLogRepository
from app.schema.super_admin.dashboard_api import (
    ActivityLogItem,
    ActivityLogListResponse,
)
from app.utils.date_range import normalize_to_utc


logger = logging.getLogger(__name__)


class ActivityLogService:
    ROLE_ALIASES = {
        "SUPER_ADMIN": "ROLE_SUPER_ADMIN",
        "ADMIN": "ROLE_ADMIN",
        "EMPLOYER": "ROLE_EMPLOYER",
        "RECRUITER": "ROLE_RECRUITER",
        "CANDIDATE": "ROLE_CANDIDATE",
    }

    @staticmethod
    def _coerce_uuid(value: Any) -> Optional[UUID]:
        if not value:
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def normalize_role(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        normalized = str(value).strip().upper().replace("-", "_").replace(" ", "_")
        if not normalized:
            return None
        if normalized in ActivityLogService.ROLE_ALIASES:
            return ActivityLogService.ROLE_ALIASES[normalized]
        if not normalized.startswith("ROLE_"):
            normalized = f"ROLE_{normalized}"
        return normalized

    @staticmethod
    def _actor_id(actor: Any) -> Optional[UUID]:
        if actor is None:
            return None
        if isinstance(actor, dict):
            value = actor.get("user_id")
        else:
            value = getattr(actor, "user_id", None)
        return ActivityLogService._coerce_uuid(value)

    @staticmethod
    def _actor_role(actor: Any) -> Optional[str]:
        if actor is None:
            return None
        if isinstance(actor, dict):
            roles = actor.get("roles") or []
            if roles:
                role = roles[0]
                if isinstance(role, dict):
                    return ActivityLogService.normalize_role(
                        role.get("role_code") or role.get("role_name")
                    )
                return ActivityLogService.normalize_role(str(role))
            return ActivityLogService.normalize_role(
                actor.get("role") or actor.get("role_code") or actor.get("actor_role")
            )

        roles = getattr(actor, "roles", None) or []
        if roles:
            role = roles[0]
            return ActivityLogService.normalize_role(
                getattr(role, "role_code", None) or getattr(role, "role_name", None)
            )
        return None

    @staticmethod
    async def _role_for_user(
        session: AsyncSession,
        user_id: UUID,
    ) -> Optional[str]:
        result = await session.execute(
            select(Role.role_code)
            .join(UsersRole, UsersRole.role_id == Role.role_id)
            .where(
                UsersRole.user_id == user_id,
                UsersRole.active_flag == True,
            )
            .limit(1)
        )
        return ActivityLogService.normalize_role(result.scalar_one_or_none())

    @staticmethod
    async def create_log(
        session: AsyncSession,
        actor: Any,
        action: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        description: Optional[str] = None,
        ip_address: Optional[str] = None,
        actor_role: Optional[str] = None,
        metadata: Optional[dict] = None,
        target_entity_name: Optional[str] = None,
        commit: bool = True,
    ) -> ActivityLog:
        log = ActivityLog(
            actor_id=ActivityLogService._actor_id(actor),
            actor_role=ActivityLogService.normalize_role(actor_role)
            or ActivityLogService._actor_role(actor),
            action=action.upper(),
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            description=description,
            ip_address=ip_address,
            metadata_=metadata,
            target_entity_name=target_entity_name,
        )

        session_add = getattr(session, "add", None)
        if session is None or session_add is None or inspect.iscoroutinefunction(session_add):
            return log

        try:
            return await ActivityLogRepository.create(
                session=session,
                log=log,
                commit=commit,
            )
        except Exception:
            rollback = getattr(session, "rollback", None)
            if rollback:
                await rollback()
            logger.exception(
                "Activity log write failed. action=%s entity_type=%s entity_id=%s",
                action,
                entity_type,
                entity_id,
            )
            return log

    @staticmethod
    async def create_log_for_user_id(
        session: AsyncSession,
        user_id: Any,
        action: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        description: Optional[str] = None,
        actor_role: Optional[str] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[dict] = None,
        target_entity_name: Optional[str] = None,
        commit: bool = True,
    ) -> ActivityLog:
        actor_uuid = ActivityLogService._coerce_uuid(user_id)
        resolved_role = ActivityLogService.normalize_role(actor_role)
        if actor_uuid and not resolved_role:
            resolved_role = await ActivityLogService._role_for_user(
                session=session,
                user_id=actor_uuid,
            )
        return await ActivityLogService.create_log(
            session=session,
            actor={"user_id": str(actor_uuid) if actor_uuid else None},
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            ip_address=ip_address,
            actor_role=resolved_role,
            metadata=metadata,
            target_entity_name=target_entity_name,
            commit=commit,
        )

    @staticmethod
    async def list_logs(
        session: AsyncSession,
        page: int,
        page_size: int,
        action=None,
        actor=None,
        role=None,
        entity_type=None,
        search=None,
        start_date=None,
        end_date=None,
        date_range=None,
    ) -> ActivityLogListResponse:
        rows, total = await ActivityLogRepository.list_logs(
            session=session,
            page=page,
            page_size=page_size,
            action=action,
            actor=actor,
            role=role,
            entity_type=entity_type,
            search=search,
            start_date=start_date,
            end_date=end_date,
            date_range=date_range,
        )

        items = []
        for log, user in rows:
            performed_by = None
            if user:
                performed_by = " ".join(
                    part
                    for part in [user.first_name, user.last_name]
                    if part
                )
                if user.email:
                    performed_by = f"{performed_by} ({user.email})"
            elif log.actor_id:
                performed_by = str(log.actor_id)

            items.append(
                ActivityLogItem(
                    activity_log_id=log.id,
                    action=log.action,
                    performed_by=performed_by,
                    user_role=log.actor_role,
                    description=log.description,
                    entity_type=log.entity_type,
                    entity_id=log.entity_id,
                    target_entity_name=log.target_entity_name,
                    ip_address=log.ip_address,
                    metadata=log.metadata_,
                    created_at=normalize_to_utc(log.created_at),
                    timestamp=normalize_to_utc(log.created_at),
                )
            )

        return ActivityLogListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
