from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controller.master_data_controller import router
from app.utils.timezones import validate_iana_timezone_name


def test_master_data_timezones_returns_frontend_dropdown_options():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/master-data/timezones")

    assert response.status_code == 200
    payload = response.json()
    items = payload["data"]["items"]
    values = [item["value"] for item in items]

    assert items
    assert "UTC" in values
    assert "Asia/Kolkata" in values

    for item in items:
        assert item["label"] == item["value"]
        assert validate_iana_timezone_name(item["value"]) == item["value"]
