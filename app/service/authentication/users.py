from sqlalchemy.future import select
from app.model.authentication.users import Users
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.service.subscription.user_subscription_service import UserSubscriptionService


class UserService:
    @staticmethod
    def _primary_role_from_user(user) -> str | None:
        role_codes = {
            (getattr(role, "role_code", "") or "").upper()
            for role in getattr(user, "roles", []) or []
        }
        if role_codes.intersection({"ROLE_EMPLOYER", "ROLE_RECRUITER"}):
            return "EMPLOYER"
        if "ROLE_CANDIDATE" in role_codes:
            return "CANDIDATE"
        if role_codes.intersection({"ROLE_ADMIN", "ROLE_SUPER_ADMIN"}):
            return "ADMIN"
        return None

    @staticmethod
    async def get_user_profile(
        session: AsyncSession,
        email: str,
    ):
        query = (
            select(Users)
            .options(selectinload(Users.roles))
            .where(Users.email == email)
        )
        result = await session.execute(query)

        user = result.scalar_one_or_none()
        if not user:
            return None

        role = UserService._primary_role_from_user(user)
        summary = await UserSubscriptionService.get_current_subscription_summary(
            session=session,
            user_id=user.user_id,
            expected_type=role,
        )
        plan_name = summary.subscription_name if summary else "No Active Plan"

        return {
            "user_id": str(user.user_id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "role": role,
            "mobile_number": user.mobile_number,
            "user_status": user.user_status,
            "email_verified": user.email_verified,
            "mobile_verified": user.mobile_verified,
            "subscription": summary.model_dump(mode="json") if summary else None,
            "subscription_name": plan_name,
            "plan_name": plan_name,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "created_by": user.created_by,
            "updated_by": user.updated_by,
        }

