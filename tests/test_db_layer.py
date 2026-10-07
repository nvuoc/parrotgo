"""Tests for persistence, in-memory cache, and Chroma empty-safe client."""

import pytest
from src.core.state import create_initial_state
from src.core.time_utils import now_iso
from src.db.sqlite_manager import PersistenceError


def test_sqlite_start_session_and_persist_turn(temp_db):
    session_id = "sess-001"
    phone = "0987654321"
    name = "Nguyễn Văn A"
    started_at = now_iso()

    # 1. Start session
    temp_db.start_session(session_id, phone, name, "Hà Nội", "Asia/Ho_Chi_Minh", started_at)

    # Verify CRM profile is initialized
    profile = temp_db.get_customer_crm_profile(phone)
    assert profile is not None
    assert profile["name"] == name
    assert profile["total_trips"] == 0

    # 2. Persist turn 1
    state = create_initial_state(session_id, phone, name, started_at, session_city="Hà Nội")
    state["turn_index"] = 1
    state["user_current_input"] = "Tôi muốn đặt xe"
    state["final_response_text"] = "Dạ mình muốn xe đón ở đâu ạ?"
    state["intents"] = ["provide_info"]
    state["last_bot_action"] = {"action_type": "ask_slot", "target_slots": ["pickup"], "metadata": {}}

    res = temp_db.persist_turn(state)
    assert res["booking_id"] is None

    # Verify replay idempotency with identical payload
    replay_res = temp_db.persist_turn(state)
    assert replay_res["booking_id"] is None

    # Verify conflict with different payload
    modified_state = dict(state)
    modified_state["user_current_input"] = "Câu nói khác"
    with pytest.raises(PersistenceError):
        temp_db.persist_turn(modified_state)


def test_sqlite_booked_updates_trips_and_favorites(temp_db):
    session_id = "sess-002"
    phone = "0912345678"
    name = "Trần Thị B"
    started_at = now_iso()

    temp_db.start_session(session_id, phone, name, None, "Asia/Ho_Chi_Minh", started_at)
    state = create_initial_state(session_id, phone, name, started_at, session_city=None)
    state["turn_index"] = 1
    state["user_current_input"] = "Đúng rồi"
    state["final_response_text"] = "Dạ em đã lưu yêu cầu đặt xe thành công ạ."
    state["intents"] = ["confirm"]
    state["booking_status"] = "booked"
    state["last_bot_action"] = {"action_type": "inform_success", "target_slots": [], "metadata": {}}
    state["booking_slots"]["vehicle_type"] = {"value": "oto_4_cho", "status": "confirmed"}
    state["booking_slots"]["pickup_time"] = {"value": "now", "raw": None, "anchored_at": None, "status": "confirmed"}
    state["booking_slots"]["pickup"] = {
        "raw": "12 Cầu Giấy",
        "formatted": "12 Cầu Giấy, Hà Nội",
        "coords": {"lat": 21.03, "lng": 105.79},
        "components": {"province_city": "Hà Nội"},
        "note": None,
        "place_id": "p1",
        "gate_id": None,
        "location_precision": "exact",
        "is_mega_poi": False,
        "default_point_used": False,
        "gate_resolved": False,
        "requires_confirmation": False,
        "clarification_kind": None,
        "candidates": [],
        "status": "confirmed",
    }
    state["booking_slots"]["destination"] = {
        "raw": "Bệnh viện Bạch Mai",
        "formatted": "78 Giải Phóng, Hà Nội",
        "coords": {"lat": 20.99, "lng": 105.84},
        "components": {"province_city": "Hà Nội"},
        "note": None,
        "place_id": "p2",
        "gate_id": None,
        "location_precision": "exact",
        "is_mega_poi": False,
        "default_point_used": False,
        "gate_resolved": False,
        "requires_confirmation": False,
        "clarification_kind": None,
        "candidates": [],
        "status": "confirmed",
    }

    res = temp_db.persist_turn(state)
    assert res["booking_id"] is not None

    # Check customer total_trips incremented
    profile = temp_db.get_customer_crm_profile(phone)
    assert profile["total_trips"] == 1
    assert len(profile["frequent_destinations"]) == 1


def test_geo_cache_validation_and_lookup(fresh_geo_cache):
    dataset = {
        "places": [{
            "place_id": "p_times_city",
            "canonical_name": "Vinhomes Times City",
            "formatted_address": "458 Minh Khai, Hà Nội",
            "city": "Hà Nội",
            "lat": 20.995,
            "lng": 105.867,
            "poi_type": "mega_poi",
            "is_mega_poi": True,
            "components": {"province_city": "Hà Nội"},
            "driver_note": None,
            "source": "test",
            "verified": True,
        }],
        "aliases": [{
            "alias_key": "times city",
            "place_id": "p_times_city",
        }],
        "gates": [{
            "gate_id": "g_times_main",
            "place_id": "p_times_city",
            "gate_code": "Cổng T1",
            "gate_key": "cong t1",
            "lat": 20.996,
            "lng": 105.868,
            "is_default_pickup": True,
            "is_default_dropoff": True,
            "driver_instruction": "Đón tại sảnh T1",
            "source": "test",
            "verified": True,
        }],
        "streets": [{
            "street_id": "s_minh_khai",
            "city": "Hà Nội",
            "street_name": "Minh Khai",
            "source": "test",
            "verified": True,
        }],
    }

    fresh_geo_cache.upsert_dataset(dataset)

    # 1. Alias lookup
    matches = fresh_geo_cache.lookup_poi_alias("Times City", city="Hà Nội")
    assert len(matches) == 1
    assert matches[0]["canonical_name"] == "Vinhomes Times City"
    assert matches[0]["is_mega_poi"] is True

    # 2. Gate lookup
    gate = fresh_geo_cache.lookup_sub_poi("p_times_city", "Cổng T1")
    assert gate is not None
    assert gate["driver_instruction"] == "Đón tại sảnh T1"

    # 3. Default gate lookup
    default_gate = fresh_geo_cache.lookup_default_gate("p_times_city", role="pickup")
    assert default_gate is not None
    assert default_gate["gate_code"] == "Cổng T1"

    # 4. Fuzzy street match
    fuzzy_matches = fresh_geo_cache.fuzzy_street_match("Min Khai", city="Hà Nội")
    assert len(fuzzy_matches) >= 1
    assert fuzzy_matches[0]["street_name"] == "Minh Khai"


def test_chroma_empty_safe(empty_faq_client):
    res = empty_faq_client.search_faq_policy("Giá cước xe máy là bao nhiêu?")
    assert res["success"] is False
    assert res["category"] == "static_faq"
    assert "chưa có thông tin" in res["answer_text"]
