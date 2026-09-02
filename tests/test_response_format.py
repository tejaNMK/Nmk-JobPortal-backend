from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.exception_handlers import register_exception_handlers
from app.schema.common import ResponseSchema, created_response, success_response


class Payload(BaseModel):
    name: str


def build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/success", response_model=ResponseSchema, response_model_exclude_none=True)
    async def success():
        return success_response(data={"id": 1}, message="Fetched successfully")

    @app.post(
        "/created",
        status_code=201,
        response_model=ResponseSchema,
        response_model_exclude_none=True,
    )
    async def created(payload: Payload):
        return created_response(data=payload.model_dump(), message="Created successfully")

    @app.get("/forbidden")
    async def forbidden():
        raise HTTPException(status_code=403, detail="Access denied")

    @app.get("/failure")
    async def failure():
        raise RuntimeError("database password must not leak")

    return app


def test_success_response_format_and_status_match():
    client = TestClient(build_test_app())

    response = client.get("/success")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": 200,
        "message": "Fetched successfully",
        "data": {"id": 1},
    }


def test_created_response_format_and_status_match():
    client = TestClient(build_test_app())

    response = client.post("/created", json={"name": "Kaint"})

    assert response.status_code == response.json()["status"] == 201
    assert response.json()["success"] is True
    assert response.json()["data"] == {"name": "Kaint"}


def test_validation_error_uses_standard_422_format():
    client = TestClient(build_test_app())

    response = client.post("/created", json={})

    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["status"] == 422
    assert response.json()["message"] == "Request validation failed"
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "body.name" in response.json()["error"]["details"]


def test_http_and_framework_errors_use_standard_format():
    client = TestClient(build_test_app())

    forbidden = client.get("/forbidden")
    missing = client.get("/missing")
    method_not_allowed = client.put("/success")

    assert forbidden.json()["error"] == {
        "code": "FORBIDDEN",
        "details": "Access denied",
    }
    assert missing.status_code == missing.json()["status"] == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert method_not_allowed.status_code == method_not_allowed.json()["status"] == 405
    assert method_not_allowed.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_unhandled_error_is_standardized_without_leaking_details():
    client = TestClient(build_test_app(), raise_server_exceptions=False)

    response = client.get("/failure")

    assert response.status_code == 500
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "password" not in response.json()["error"]["details"]
