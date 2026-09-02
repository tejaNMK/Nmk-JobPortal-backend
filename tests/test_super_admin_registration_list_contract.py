from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.service.super_admin.candidate_service import CandidateService


class FakeSession:
    pass


@pytest.mark.asyncio
async def test_candidate_list_defaults_newest_first_and_returns_created_at(monkeypatch):
    created_at = datetime(2026, 8, 5, 9, 12, 3, 221000)
    user = SimpleNamespace(
        user_id=uuid4(),
        first_name="Asha",
        last_name="Rao",
        email="asha@example.com",
        mobile_number="+919876543210",
        created_at=created_at,
        last_login_at=None,
    )
    profile = SimpleNamespace(
        candidate_id="candidate-1",
        headline="Backend Developer",
        total_experience=Decimal("3.5"),
        current_location="Hyderabad",
        profile_completion_pct=80,
        open_to_work=True,
        status="ACTIVE",
    )

    async def fake_list_candidates(
        session,
        page,
        page_size,
        search,
        status,
        subscription,
        registered_from,
        registered_to,
        sort_by,
        sort_order,
    ):
        assert sort_by == "created_at"
        assert sort_order == "desc"
        return [(profile, user, "Growth", 1)], 1

    monkeypatch.setattr(
        "app.service.super_admin.candidate_service.CandidateRepository.list_candidates",
        fake_list_candidates,
    )

    response = await CandidateService.list_candidates(
        session=FakeSession(),
        page=1,
        page_size=10,
        search=None,
    )

    assert response.total == 1
    assert response.items[0].created_at == created_at
    assert response.items[0].registered_on == created_at
