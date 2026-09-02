from fastapi.testclient import TestClient
import pytest
from unittest.mock import AsyncMock, patch

from app.main import init_app


@pytest.fixture(scope="function")
def client():
    with patch("app.main.db") as mock_db:
        mock_db.init.return_value = None
        mock_db.close = AsyncMock(return_value=None)
        mock_db.session = None

        app = init_app()
        return TestClient(app)


class TestCompanyController:

    def test_get_company_details_success(self, client):

        company_data = {
            "company_id": "COMP001",
            "company_name": "Pineapple",
            "website": "https://pineapple.com",
            "logo_path": "/logos/pineapple.png",
            "description": "Sample company",
            "industry": "Information Technology",
            "size": "100-500",
            "location": "Hyderabad",
            "company_email": "khethankalluru@gmail.com",
            "company_mobile": "9876543210",
            "open_jobs": [
                {
                    "job_id": "JOB001",
                    "title": "Python Developer",
                    "location": "Hyderabad"
                }
            ]
        }

        with patch(
            "app.controller.company.CompanyService.get_company_details",
            new_callable=AsyncMock,
            return_value=company_data
        ) as mock_service:

            async def mock_jwt_bearer(request):
                return "jwt-token"

            with patch(
                "app.controller.company.JWTBearer.__call__",
                new=mock_jwt_bearer,
            ):

                response = client.get(
                    "/company/COMP001",
                    headers={
                        "Authorization": "Bearer jwt-token"
                    }
                )

                assert response.status_code == 200

                data = response.json()

                assert (
                    data["message"]
                    == "Successfully fetched company details"
                )

                assert (
                    data["data"]["company_name"]
                    == "Pineapple"
                )

                mock_service.assert_awaited_once()

    def test_company_not_found(self, client):

        with patch(
            "app.controller.company.CompanyService.get_company_details",
            new_callable=AsyncMock,
            return_value=None
        ):

            async def mock_jwt_bearer(request):
                return "jwt-token"

            with patch(
                "app.controller.company.JWTBearer.__call__",
                new=mock_jwt_bearer,
            ):

                response = client.get(
                    "/company/INVALID",
                    headers={
                        "Authorization": "Bearer jwt-token"
                    }
                )

                assert response.status_code == 404

                body = response.json()
                assert body["success"] is False
                assert body["status"] == 404
                assert body["message"] == "Company not found"
                assert body["error"]["code"] == "NOT_FOUND"

    def test_company_requires_jwt(self, client):

        response = client.get(
            "/company/COMP001"
        )

        assert response.status_code == 401

    def test_company_invalid_auth_scheme(self, client):

        response = client.get(
            "/company/COMP001",
            headers={
                "Authorization": "Basic abc"
            }
        )

        assert response.status_code == 401
