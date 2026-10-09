"""Tests for ParrotGo Web API."""

import pytest
from fastapi.testclient import TestClient
from src.web.server import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "llm_mode" in data


def test_session_lifecycle():
    # 1. Create Session
    create_resp = client.post(
        "/api/sessions",
        json={"name": "Nguyễn Văn Test", "phone": "0911223344", "city": "Hồ Chí Minh"},
    )
    assert create_resp.status_code == 200
    s_data = create_resp.json()
    session_id = s_data["session_id"]
    assert session_id is not None
    assert "Nguyễn Văn Test" in s_data["greeting"]

    # 2. Get Session details
    get_resp = client.get(f"/api/sessions/{session_id}")
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["phone"] == "0911223344"

    # 3. Process a Turn
    turn_resp = client.post(
        f"/api/sessions/{session_id}/turns",
        json={"message": "Chào bạn, tôi muốn đặt xe 4 chỗ từ Chợ Bến Thành đi Sân bay Tân Sơn Nhất"},
    )
    assert turn_resp.status_code == 200
    turn_data = turn_resp.json()
    assert "bot_response" in turn_data
    assert len(turn_data["bot_response"]) > 0
    assert "booking_state" in turn_data

    # 4. End Session
    del_resp = client.delete(f"/api/sessions/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "success"


def test_static_index():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "ParrotGo" in response.text
