from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib import response
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import get_db
from app.dependencies.auth_dependencies import get_jwt_payload_401
from app.main import init_app


USER_ID = uuid4()
EMPLOYER_USER_ID = uuid4()


class DumpableResult:
    def __init__(self, **data):
        self.data = data

    def model_dump(self):
        return self.data


class FakeSession:
    pass


def _fake_user(role_code: str, user_id):
    return SimpleNamespace(
        user_id=user_id,
        roles=[SimpleNamespace(role_code=role_code)],
    )


@pytest.fixture()
def auth_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_payload():
        return {"user_id": str(USER_ID), "email": "candidate@example.com"}

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload

    # The apply endpoints are now guarded by `candidate_only`, which looks up
    # the user's roles in the DB. Mock that lookup to return a candidate.
    patcher = patch(
        "app.dependencies.role_dependencies.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_fake_user("ROLE_CANDIDATE", USER_ID),
    )
    patcher.start()

    client = TestClient(app)
    client._role_patcher = patcher
    return client


@pytest.fixture()
def employer_auth_client():
    """An authenticated user who only holds an employer role."""
    app = init_app()

    async def fake_db():
        yield FakeSession()

    async def fake_payload():
        return {"user_id": str(EMPLOYER_USER_ID), "email": "employer@example.com"}

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_jwt_payload_401] = fake_payload

    patcher = patch(
        "app.dependencies.role_dependencies.UsersRepository.find_by_user_id",
        new_callable=AsyncMock,
        return_value=_fake_user("ROLE_EMPLOYER", EMPLOYER_USER_ID),
    )
    patcher.start()

    client = TestClient(app)
    client._role_patcher = patcher
    return client


@pytest.fixture()
def unauth_client():
    app = init_app()

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    return TestClient(app)


def test_employer_cannot_apply_for_job(employer_auth_client):
    """Regression test: only candidates may apply for jobs, not employers."""
    with patch(
        "app.controller.job_application.JobApplicationService.apply_for_job",
        new_callable=AsyncMock,
        return_value={"message": "Application submitted successfully", "application_id": "app-1"},
    ) as service:
        response = employer_auth_client.post(
            "/candidate/applications",
            json={"job_id": "job-1", "cover_letter_text": "I am interested."},
        )

    assert response.status_code == 403
    service.assert_not_awaited()


def test_apply_for_job_success(auth_client):
    with patch(
        "app.controller.job_application.JobApplicationService.apply_for_job",
        new_callable=AsyncMock,
        return_value={"message": "Application submitted successfully", "application_id": "app-1"},
    ) as service:
        response = auth_client.post(
            "/candidate/applications",
            json={"job_id": "job-1", "cover_letter_text": "I am interested."},
        )

    assert response.status_code == 201
    assert response.json()["message"] == "Application submitted successfully"
    assert response.json()["data"]["application_id"] == "app-1"
    service.assert_awaited_once()


def test_apply_for_job_requires_auth(unauth_client):
    response = unauth_client.post("/candidate/applications", json={"job_id": "job-1"})
    assert response.status_code == 401


def test_apply_for_job_validates_referral_contact(auth_client):
    response = auth_client.post(
        "/candidate/applications",
        json={"job_id": "job-1", "source": "Referral"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "status_code,detail",
    [
        (404, "Job not found"),
        (404, "Resume not found"),
        (409, "You have already applied for this job"),
    ],
)
def test_apply_for_job_propagates_service_errors(auth_client, status_code, detail):
    with patch(
        "app.controller.job_application.JobApplicationService.apply_for_job",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=status_code, detail=detail),
    ):
        response = auth_client.post("/candidate/applications", json={"job_id": "job-1"})

    assert response.status_code == status_code
    assert response.json()["success"] is False
    assert response.json()["status"] == status_code
    assert response.json()["message"] == detail


def test_list_applications_success(auth_client):
    with patch(
        "app.controller.job_application.JobApplicationService.list_applications",
        new_callable=AsyncMock,
        return_value=DumpableResult(total=1, page=1, page_size=20, items=[]),
    ) as service:
        response = auth_client.get(
            "/candidate/applications",
            params={"status": "APPLIED", "source": "Jobs Portal"},
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Applications fetched successfully"
    assert response.json()["data"]["total"] == 1
    service.assert_awaited_once()


def test_apply_for_job_with_resume_upload_success(auth_client):
    with patch(
        "app.controller.job_application.JobApplicationService.apply_for_job_with_resume_upload",
        new_callable=AsyncMock,
        return_value={
            "message": "Application submitted successfully",
            "application_id": "app-1",
            "application_status": "APPLIED",
            "resume_id": "resume-1",
        },
    ) as service:
        response = auth_client.post(
            "/candidate/applications/with-resume",
            data={
                "job_id": "job-1",
                "cover_letter_text": "I am interested.",
                "source": "Jobs Portal",
            },
            files={"resume": ("resume.pdf", b"%PDF-1.4", "application/pdf")},
        )

    assert response.status_code == 201
    assert response.json()["message"] == "Application submitted successfully"
    assert response.json()["data"]["resume_id"] == "resume-1"
    service.assert_awaited_once()


from pydantic import ValidationError

def test_apply_for_job_with_resume_upload_validates_referral_contact(auth_client):
    with pytest.raises(ValidationError):
        auth_client.post(
            "/candidate/applications/with-resume",
            data={"job_id": "job-1", "source": "Referral"},
            files={"resume": ("resume.pdf", b"%PDF-1.4", "application/pdf")},
        )


def test_my_job_applications_template_alias_success(auth_client):
    with patch(
        "app.controller.job_application.JobApplicationService.list_applications",
        new_callable=AsyncMock,
        return_value=DumpableResult(total=1, page=1, page_size=20, items=[]),
    ) as service:
        response = auth_client.get("/candidate/my-job-applications")

    assert response.status_code == 200
    assert response.json()["message"] == "My job applications fetched successfully"
    assert response.json()["data"]["total"] == 1
    service.assert_awaited_once()


def test_list_applications_rejects_invalid_status(auth_client):
    response = auth_client.get("/candidate/applications", params={"status": "1"})
    assert response.status_code == 422


def test_next_steps_success(auth_client):
    with patch(
        "app.controller.job_application.JobApplicationService.get_next_steps_panel",
        new_callable=AsyncMock,
        return_value=DumpableResult(items=[]),
    ):
        response = auth_client.get("/candidate/applications/next-steps")

    assert response.status_code == 200
    assert response.json()["message"] == "Next steps fetched successfully"
    assert response.json()["data"] == {"items": []}


def test_application_detail_success(auth_client):
    with patch(
        "app.controller.job_application.JobApplicationService.get_application_detail",
        new_callable=AsyncMock,
        return_value=DumpableResult(application_id="app-1"),
    ):
        response = auth_client.get("/candidate/applications/app-1")

    assert response.status_code == 200
    assert response.json()["data"] == {"application_id": "app-1"}


def test_application_detail_not_found(auth_client):
    with patch(
        "app.controller.job_application.JobApplicationService.get_application_detail",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Application not found"),
    ):
        response = auth_client.get("/candidate/applications/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["message"] == "Application not found"


@pytest.mark.parametrize(
    "method,path,body,service_name,expected_detail",
    [
        (
            "patch",
            "/candidate/applications/app-1/status",
            {"application_status": "ARCHIVED"},
            "update_status",
            "Status updated successfully",
        ),
        (
            "put",
            "/candidate/applications/app-1/next-step",
            {"next_step_text": "Follow up", "next_step_due": "2099-01-01"},
            "upsert_next_step",
            "Next step saved",
        ),
        (
            "patch",
            "/candidate/applications/app-1/interview-loop",
            {"interview_loop_date": "2099-01-01"},
            "set_interview_loop_date",
            "Interview loop date set",
        ),
    ],
)
def test_application_mutation_endpoints_success(auth_client, method, path, body, service_name, expected_detail):
    with patch(
        f"app.controller.job_application.JobApplicationService.{service_name}",
        new_callable=AsyncMock,
        return_value={"message": expected_detail, "application_id": "app-1"},
    ) as service:
        response = getattr(auth_client, method)(path, json=body)

    assert response.status_code == 200
    assert response.json()["message"] == expected_detail
    service.assert_awaited_once()


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("patch", "/candidate/applications/app-1/status", {"application_status": "APPLIED"}),
        ("put", "/candidate/applications/app-1/next-step", {}),
        ("patch", "/candidate/applications/app-1/interview-loop", {"interview_loop_date": "not-a-date"}),
    ],
)
def test_application_mutation_endpoints_validate_payload(auth_client, method, path, body):
    response = getattr(auth_client, method)(path, json=body)
    assert response.status_code == 422


def test_withdraw_application_success(auth_client):
    with patch(
        "app.controller.job_application.JobApplicationService.withdraw_application",
        new_callable=AsyncMock,
        return_value={
            "message": "Application withdrawn successfully",
            "application_id": "app-1",
            "application_status": "WITHDRAWN",
        },
    ):
        response = auth_client.delete("/candidate/applications/app-1")

    assert response.status_code == 200
    assert response.json()["message"] == "Application withdrawn successfully"
    assert response.json()["data"] == {}


def test_get_notes_success(auth_client):
    note = DumpableResult(note_id="note-1", note_text="Call recruiter")
    with patch(
        "app.controller.job_application.JobApplicationService.get_notes",
        new_callable=AsyncMock,
        return_value=[note],
    ):
        response = auth_client.get("/candidate/applications/app-1/notes")

    assert response.status_code == 200
    assert response.json()["message"] == "Notes fetched successfully"
    assert response.json()["data"] == [{"note_id": "note-1", "note_text": "Call recruiter"}]


def test_add_note_success(auth_client):
    with patch(
        "app.controller.job_application.JobApplicationService.add_note",
        new_callable=AsyncMock,
        return_value=DumpableResult(note_id="note-1", note_text="Call recruiter"),
    ):
        response = auth_client.post(
            "/candidate/applications/app-1/notes",
            json={"note_text": "Call recruiter"},
        )

    assert response.status_code == 201
    assert response.json()["message"] == "Note added successfully"
    assert response.json()["data"]["note_id"] == "note-1"


def test_add_note_validates_text(auth_client):
    response = auth_client.post("/candidate/applications/app-1/notes", json={"note_text": ""})
    assert response.status_code == 422


def test_update_note_success(auth_client):
    with patch(
        "app.controller.job_application.JobApplicationService.update_note",
        new_callable=AsyncMock,
        return_value={"message": "Note updated"},
    ):
        response = auth_client.patch(
            "/candidate/applications/app-1/notes/note-1",
            json={"note_text": "Updated note"},
        )

    assert response.status_code == 200
    assert response.json()["message"] == "Note updated"


def test_delete_note_success(auth_client):
    with patch(
        "app.controller.job_application.JobApplicationService.delete_note",
        new_callable=AsyncMock,
        return_value={"message": "Note deleted"},
    ):
        response = auth_client.delete("/candidate/applications/app-1/notes/note-1")

    assert response.status_code == 200
    assert response.json()["message"] == "Note deleted"



def test_note_endpoint_application_not_found(auth_client):
    with patch(
        "app.controller.job_application.JobApplicationService.add_note",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=404,
            detail="Application not found",
        ),
    ):
        response = auth_client.post(
            "/candidate/applications/missing/notes",
            json={"note_text": "Call recruiter"},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["message"] == "Application not found"