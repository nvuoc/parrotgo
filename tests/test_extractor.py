"""Tests for NLU extractor covering key scenarios from extractor.md."""

from src.core.time_utils import normalize_pickup_time
from src.services.llm_extractor import run_llm_extractor


def test_extractor_operator_and_cancel():
    res1 = run_llm_extractor({"user_text": "Cho tôi gặp người thật"})
    assert "request_operator" in res1["intents"]
    assert res1["primary_intent"] == "request_operator"

    res2 = run_llm_extractor({"user_text": "Thôi tôi không đi nữa, hủy xe giúp tôi"})
    assert "cancel" in res2["intents"]
    assert res2["primary_intent"] == "cancel"


def test_extractor_self_correction_vehicle():
    # "Bốn chỗ... à thôi bảy chỗ"
    res = run_llm_extractor({"user_text": "Tôi muốn đi bốn chỗ... à thôi bảy chỗ"})
    assert "change_info" in res["intents"] or "provide_info" in res["intents"]
    v_updates = [u for u in res["extracted_slots"] if u["slot_name"] == "vehicle_type"]
    assert len(v_updates) == 1
    assert v_updates[0]["value"] == "oto_7_cho"


def test_extractor_deep_alley():
    text = "đón tôi ở số 12 ngách 34/56 ngõ 78 Cầu Giấy"
    res = run_llm_extractor({"user_text": text})
    p_updates = [u for u in res["extracted_slots"] if u["slot_name"] == "pickup"]
    assert len(p_updates) == 1
    meta = p_updates[0]["metadata"]
    assert meta["head_alley"] == "Ngõ 78 Cầu Giấy"
    assert "12 ngách 34/56" in meta["detail"]


def test_extractor_airport_sub_poi():
    text = "đón tôi ở Cột 9 sảnh E tầng 2 Nội Bài"
    res = run_llm_extractor({"user_text": text})
    p_updates = [u for u in res["extracted_slots"] if u["slot_name"] == "pickup"]
    assert len(p_updates) == 1
    assert p_updates[0]["metadata"]["sub_poi"] == "Cột 9 sảnh E tầng 2"


def test_extractor_time_normalization():
    received_at = "2026-10-07T10:00:00+07:00"
    tz = "Asia/Ho_Chi_Minh"

    # now
    t_now = normalize_pickup_time("now", "đi ngay", received_at, tz)
    assert t_now["value"] == "now"
    assert t_now["status"] == "extracted"

    # +15m
    t_rel = normalize_pickup_time("+15m", "sau 15 phút", received_at, tz)
    assert t_rel["status"] == "extracted"
    assert "10:15:00" in t_rel["value"]

    # Past time (09:00 vs 10:00)
    t_past = normalize_pickup_time("09:00", "9 giờ", received_at, tz)
    assert t_past["status"] == "needs_clarification"
    assert t_past["value"] is None


def test_extractor_both_pickup_and_destination():
    text = "đón ở 12 Cầu Giấy sang Viện 108"
    res = run_llm_extractor({"user_text": text})
    slot_names = {u["slot_name"] for u in res["extracted_slots"]}
    assert "pickup" in slot_names
    assert "destination" in slot_names
