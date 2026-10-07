"""Tests for QA Dispatcher: state inspection, route estimates, and FAQ routing."""

from src.core.state import get_initial_booking_slots
from src.services.qa_dispatcher import dispatch_questions


def test_qa_state_inspection():
    slots = get_initial_booking_slots()
    slots["destination"] = {
        "raw": "Viện 108",
        "formatted": "Bệnh viện 108, Hà Nội",
        "coords": {"lat": 21.0185, "lng": 105.8595},
        "components": {"province_city": "Hà Nội"},
        "note": None,
        "place_id": None,
        "gate_id": None,
        "location_precision": "exact",
        "is_mega_poi": False,
        "default_point_used": False,
        "gate_resolved": False,
        "requires_confirmation": False,
        "clarification_kind": None,
        "candidates": [],
        "status": "extracted",
    }
    slots["vehicle_type"] = {"value": "oto_4_cho", "status": "extracted"}

    # Query destination
    res_dest = dispatch_questions("Nãy tôi đặt đi đâu?", slots)
    assert res_dest["category"] == "session_state"
    assert "Bệnh viện 108" in res_dest["answer_text"]

    # Query vehicle
    res_veh = dispatch_questions("Tôi đang đi xe gì?", slots)
    assert res_veh["category"] == "session_state"
    assert "bốn chỗ" in res_veh["answer_text"]


def test_qa_dynamic_route_tool():
    slots = get_initial_booking_slots()
    slots["pickup"]["coords"] = {"lat": 21.0315, "lng": 105.7985}
    slots["destination"]["coords"] = {"lat": 21.0185, "lng": 105.8595}

    res = dispatch_questions("Từ đây ra đó bao xa và đi hết mấy phút?", slots)
    assert res["category"] == "dynamic_tool"
    assert res["success"] is True
    assert "cây số" in res["answer_text"]
    assert "phút" in res["answer_text"]


def test_qa_route_tool_without_coords():
    slots = get_initial_booking_slots()
    res = dispatch_questions("Quãng đường bao xa?", slots)
    assert res["category"] == "dynamic_tool"
    assert res["success"] is False
    assert "chưa ước tính được" in res["answer_text"]


def test_pickup_eta_does_not_use_trip_duration():
    slots = get_initial_booking_slots()
    slots["pickup"]["coords"] = {"lat": 21.0315, "lng": 105.7985}
    slots["destination"]["coords"] = {"lat": 21.0185, "lng": 105.8595}
    for text in ["Bao lâu tài xế tới?", "Đặt rồi thì bao giờ tài xế đến?"]:
        result = dispatch_questions(text, slots)
        assert result["source"] == "pickup_eta_unavailable"
        assert "cây số" not in result["answer_text"]


def test_supported_vehicle_question_reaches_faq(monkeypatch):
    from src.services.qa_dispatcher import chroma_faq_client
    monkeypatch.setattr(chroma_faq_client, "search_faq_policy", lambda query, vehicle_type: {"category": "static_faq", "success": True, "answer_text": "Có xe máy, bốn chỗ, bảy chỗ.", "source": "test", "metadata": {}})
    result = dispatch_questions("Có những loại xe nào?", get_initial_booking_slots())
    assert result["category"] == "static_faq"
    assert "bảy chỗ" in result["answer_text"]


def test_route_estimation_invalid_coords_is_safe():
    slots = get_initial_booking_slots()
    slots["pickup"]["coords"] = {"lat": "bad", "lng": 105.7985}
    slots["destination"]["coords"] = {"lat": 21.0185, "lng": 105.8595}
    result = dispatch_questions("Tuyến này bao xa?", slots)
    assert result["success"] is False


def test_trip_duration_query_is_not_pickup_eta():
    slots = get_initial_booking_slots()
    slots["pickup"]["coords"] = {"lat": 21.0315, "lng": 105.7985}
    slots["destination"]["coords"] = {"lat": 21.0185, "lng": 105.8595}
    result = dispatch_questions("Xe từ đây đến đó bao lâu?", slots)
    assert result["source"] == "route_tool"


def test_change_destination_how_to_reaches_faq_but_current_destination_is_state(monkeypatch):
    from src.services.qa_dispatcher import chroma_faq_client
    monkeypatch.setattr(chroma_faq_client, "search_faq_policy", lambda *args, **kwargs: {"category": "static_faq", "success": True, "answer_text": "Dạ mình nói địa chỉ mới muốn đến giúp em ạ.", "source": "test", "metadata": {}})
    slots = get_initial_booking_slots()
    slots["destination"].update(raw="Viện 108", formatted="Bệnh viện 108, Hà Nội", status="extracted")
    result = dispatch_questions("Tôi muốn thay điểm đến thì làm sao?", slots)
    assert result["category"] == "static_faq"
    assert "địa chỉ mới" in result["answer_text"]
    result = dispatch_questions("Điểm đến của tôi là đâu?", slots)
    assert result["category"] == "session_state"
    assert "Bệnh viện 108" in result["answer_text"]
