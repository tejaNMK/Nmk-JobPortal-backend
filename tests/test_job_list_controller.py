from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import init_app


# The application mapper bootstrap is failing in this repo snapshot
# (Job -> JobSkill relationship). Controller tests should avoid
# executing ORM mapper initialization by skipping app startup.



@pytest.fixture(scope="function")
def client():
    app = init_app()
    with patch("app.main.db") as mock_db:
        mock_db.init.return_value = None
        mock_db.close = AsyncMock(return_value=None)
        mock_db.session = None
        app = init_app()
        return TestClient(app)


recruiter_employer_payload = {
    "user_id": "user-1",
    "email": "emp1@acme.com",
    "roles": [
        {
            "role_id": "11111111-1111-1111-1111-111111111111",
            "role_name": "Recruiter",
            "role_code": "ROLE_EMPLOYER",
        }
    ],
}


class TestJobListController:
    def test_list_jobs_success_returns_response_shape(self, client):
        mocked_service_result = {
            "rows": [],
            "page": 1,
            "page_size": 20,
            "total_records": 0,
        }

        with patch(
            "app.repository.authentication.auth_repo.JWTRepo.extract_token",
            return_value=recruiter_employer_payload,
        ), patch(
            "app.service.employer_service.job_service.JobService.list_employer_jobs",
            new_callable=AsyncMock,
            return_value=mocked_service_result,
        ) as mock_list:
            r = client.get(
                "/jobs/list",
                params={
                    "search": "python",
                    "page": 1,
                    "page_size": 20,
                    "sort_by": "POSTED_DATE_DESC",
                },
                headers={"Authorization": "Bearer test"},
            )


            assert r.status_code == 200
            data = r.json()
            assert "message" in data
            assert "data" in data
            assert data["data"] == mocked_service_result
            mock_list.assert_awaited_once()

    def test_list_jobs_no_authorization_returns_401(self, client):
        r = client.get("/jobs/list", params={"search": "python"})
        assert r.status_code in (401, 403)

    def test_list_jobs_clear_filters_empties_search(self, client):
        mocked_service_result = {
            "rows": [],
            "page": 1,
            "page_size": 10,
            "total_records": 0,
        }

        with patch(
            "app.repository.authentication.auth_repo.JWTRepo.extract_token",
            return_value=recruiter_employer_payload,
        ), patch(
            "app.service.employer_service.job_service.JobService.list_employer_jobs",
            new_callable=AsyncMock,
            return_value=mocked_service_result,
        ) as mock_list:
            r = client.get(
                "/jobs/list",
                params={
                    "search": "python",
                    "clear_filters": "true",
                    "page": 1,
                    "page_size": 10,
                },
                headers={"Authorization": "Bearer test"},
            )
            assert r.status_code == 200
            assert r.json()["data"] == mocked_service_result
            _, kwargs = mock_list.call_args
            filters = kwargs["filters"]
            assert getattr(filters, "search") in ("", None)

