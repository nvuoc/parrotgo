"""Regression coverage for customer utterances, live contract and service failures."""

import json
import sys
from types import SimpleNamespace

import pytest

from src.config import settings
from src.core.nodes.extractor import extractor_node
from src.core.state import (
    create_initial_state,
    empty_address_slot,
    get_initial_booking_slots,
)
from src.core.time_utils import normalize_pickup_time
from src.services.llm_extractor import ExtractorServiceError, run_llm_extractor
from src.services.templates import render_template_by_action


def extract(text, action=None, slots=None):
    return run_llm_extractor({"user_text": text, "last_bot_action": action, "booking_slots": slots or {}, "turn_received_at": "2026-10-07T09:00:00+07:00", "timezone": "Asia/Ho_Chi_Minh"})


def values(result):
    return {u["slot_name"]: u["value"] for u in result["extracted_slots"]}


@pytest.mark.parametrize("text,expected", [
    ("cho tôi đi bảy chỗ à thôi bốn chỗ", "oto_4_cho"),
    ("không cần xe bảy chỗ, bốn chỗ thôi", "oto_4_cho"),
    ("bốn chỗ à thôi bảy chỗ", "oto_7_cho"),
])
def test_last_positive_vehicle_correction(text, expected):
    assert values(extract(text))["vehicle_type"] == expected


@pytest.mark.parametrize("text", ["Nãy tôi đặt đi đâu?", "điểm đến là đâu?", "đón ở đâu?", "mấy km vậy", "thời tiết có mưa không?", "xe bảy chỗ giá bao nhiêu?", "Có những loại xe nào?", "Đặt xe thành công nghĩa là gì?", "Có thể hẹn giờ đón không?", "Tôi có thể thêm điểm dừng không?", "Cần cung cấp thông tin gì để đặt xe?"])
def test_questions_never_overwrite_booking(text):
    result = extract(text)
    assert "ask_question" in result["intents"]
    assert result["extracted_slots"] == []
    assert "deny" not in result["intents"]
    assert "confirm" not in result["intents"]


@pytest.mark.parametrize("text", ["Đón ở 12 Cầu Giấy Sang Viện 108", "Từ 12 Cầu Giấy Đến Viện 108", "Đón ở 12 Cầu Giấy sang Viện 108 bằng xe bốn chỗ"])
def test_case_insensitive_route_and_bundled_slots(text):
    data = values(extract(text))
    assert data["pickup"] == "12 Cầu Giấy"
    assert data["destination"] == "Viện 108"
    if "bốn chỗ" in text:
        assert data["vehicle_type"] == "oto_4_cho"


def test_bundle_destination_and_vehicle():
    data = values(extract("Cho tôi đi Vincom bằng xe bốn chỗ"))
    assert data["destination"] == "Vincom"
    assert data["vehicle_type"] == "oto_4_cho"


def test_alley_and_gate_metadata_are_actual_customer_values():
    result = extract("đón tôi ở số 99 ngách 5 ngõ 200 Hoàng Hoa Thám")
    update = result["extracted_slots"][0]
    assert update["value"] == "Ngõ 200 Hoàng Hoa Thám"
    assert "99 ngách 5" in update["metadata"]["detail"]
    assert "34/56" not in json.dumps(update, ensure_ascii=False)
    result = extract("đón tôi ở cột 3 sảnh A tầng 1 Nội Bài")
    update = next(u for u in result["extracted_slots"] if u["slot_name"] == "pickup")
    assert update["metadata"]["sub_poi"] == "cột 3 sảnh A tầng 1"
    assert "Cột 9" not in update["metadata"]["driver_note"]


@pytest.mark.parametrize("text,expected", [("đúng rồi hủy xe giúp tôi", "confirm"), ("không hủy xe nữa", "deny"), ("không cần hủy xe", "deny")])
def test_cancel_confirmation_and_negation(text, expected):
    result = extract(text, {"action_type": "confirm_cancel", "target_slots": [], "metadata": {}})
    assert result["intents"] == [expected]


def test_clarification_city_augments_existing_address():
    result = extract("ở Hà Nội", {"action_type": "clarify_address", "target_slots": ["destination"], "metadata": {"type": "city"}})
    assert values(result)["session_city"] == "Hà Nội"
    update = next(u for u in result["extracted_slots"] if u["slot_name"] == "destination")
    assert update["metadata"]["operation"] == "augment"
    assert update["metadata"]["component_type"] == "city"


@pytest.mark.parametrize("text,expected", [
    ("10:00 ngày mai", "2026-10-08T10:00:00+07:00"),
    ("mai 9 giờ", "2026-10-08T09:00:00+07:00"),
    ("sau 30 phút", "2026-10-07T09:30:00+07:00"),
    ("hai tiếng nữa", "2026-10-07T11:00:00+07:00"),
    ("mười lăm phút nữa", "2026-10-07T09:15:00+07:00"),
    ("ngày 9/10 lúc 8 giờ tối", "2026-10-09T20:00:00+07:00"),
    ("mai 8 giờ rưỡi sáng", "2026-10-08T08:30:00+07:00"),
])
def test_spoken_appointment_date_and_relative_time(text, expected):
    result = extract(text, {"action_type": "ask_slot", "target_slots": ["pickup_time"], "metadata": {}})
    update = next(u for u in result["extracted_slots"] if u["slot_name"] == "pickup_time")
    normalized = normalize_pickup_time(update["value"], update["source_text"], "2026-10-07T09:00:00+07:00")
    assert normalized["value"] == expected


@pytest.mark.parametrize("text", ["08:00", "mai", "ngày 31/2 lúc 10 giờ", "25:80", "sau 0 phút"])
def test_invalid_or_incomplete_time_is_clarified(text):
    result = normalize_pickup_time(text, text, "2026-10-07T09:00:00+07:00")
    assert result["status"] == "needs_clarification"
    assert result["value"] is None


def test_live_contract_contains_state_and_does_not_fallback(monkeypatch):
    captured = {}
    class Client:
        def __init__(self, **kwargs):
            captured["options"] = kwargs
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def create(self, **kwargs):
            captured.update(kwargs)
            output = {"intents": ["ask_question"], "primary_intent": "ask_question", "extracted_slots": [], "addressed_slots": [], "clarification_response": None, "confidence": 1}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))])
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=Client))
    monkeypatch.setattr(settings, "LLM_MODE", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-stub")
    state = create_initial_state("audit", "0999", "Audit", "2026-10-07T09:00:00+07:00", session_city="Hà Nội")
    state["booking_slots"]["destination"]["formatted"] = "Vincom Bà Triệu"
    state["messages"] = [{"role": "bot", "content": "Ở tỉnh nào?"}]
    state["last_bot_action"] = {"action_type": "clarify_address", "target_slots": ["destination"], "metadata": {"type": "city"}}
    state["user_current_input"] = "Hà Nội, có những loại xe nào?"
    result = extractor_node(state)
    prompt = captured["messages"][0]["content"]
    assert "Vincom Bà Triệu" in prompt and "2026-10-07T09:00:00+07:00" in prompt
    assert "Ở tỉnh nào?" in prompt and '"type": "city"' in prompt
    assert captured["options"]["timeout"] <= 20
    assert captured["options"]["max_retries"] == 0
    assert result["nlu_error"] is None
    def fail(self, **_):
        raise TimeoutError("private-provider-body")
    monkeypatch.setattr(Client, "create", fail)
    state["user_current_input"] = "đi Viện 108"
    state["fallback_count"] = 1
    result = extractor_node(state)
    assert result["turn_extracted_slots"] == []
    assert result["nlu_error"] == {"provider": "groq", "code": "timeout"}
    assert result["fallback_count"] == 1
    assert result["nlu_retry_count"] == 1


def test_missing_live_key_is_explicit(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MODE", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    with pytest.raises(ExtractorServiceError, match="missing_api_key"):
        run_llm_extractor({"user_text": "đi Vincom"})


def test_stopover_confirmation_reads_actual_address():
    state = create_initial_state("audit", "0999", "Audit", "2026-10-07T09:00:00+07:00")
    state["booking_slots"]["stopovers"] = [{"order": 1, "address": {"formatted": "Bệnh viện 108", "raw": "Viện 108"}}]
    action = {"action_type": "confirm_slots", "target_slots": ["stopovers:0"], "metadata": {}}
    assert "Bệnh viện 108" in render_template_by_action(action, state["booking_slots"])


def test_candidate_question_distinguishes_two_places_in_same_city():
    state = create_initial_state("audit", "0999", "Audit", "2026-10-07T09:00:00+07:00")
    state["booking_slots"]["destination"]["candidates"] = [{"formatted": "Vincom Bà Triệu", "city": "Hà Nội"}, {"formatted": "Vincom Nguyễn Chí Thanh", "city": "Hà Nội"}]
    action = {"action_type": "clarify_address", "target_slots": ["destination"], "metadata": {"type": "ab"}}
    text = render_template_by_action(action, state["booking_slots"])
    assert "Bà Triệu" in text and "Nguyễn Chí Thanh" in text


def test_note_and_scheduled_request_are_not_mistaken_for_question():
    assert values(extract("ghi chú chở chó nhỏ"))["general_note"] == "chở chó nhỏ"
    assert "pickup_time" in values(extract("tôi muốn hẹn giờ 9 giờ ngày mai"))
    assert values(extract("điểm đến là Vincom"))["destination"] == "Vincom"


def test_city_augment_live_preserves_city_value(monkeypatch):
    import src.services.llm_extractor as service
    class Client:
        def __init__(self, **_):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def create(self, **_):
            output = {"intents": ["provide_info"], "extracted_slots": [
                {"slot_name": "session_city", "value": "Hà Nội", "source_text": "Hà Nội", "metadata": {"operation": "replace"}},
                {"slot_name": "destination", "value": "Vincom", "source_text": "Vincom", "metadata": {"operation": "augment", "component_type": "city", "address_city": "Hà Nội"}},
            ]}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))])
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=Client))
    monkeypatch.setattr(settings, "LLM_MODE", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-stub")
    result = service.run_llm_extractor({"user_text": "ở Hà Nội"})
    assert values(result)["destination"] == "Hà Nội"


def test_spoken_clock_in_bundled_booking_does_not_pollute_address():
    data = values(extract("đón ở 12 Cầu Giấy chín giờ tối"))
    assert data["pickup"] == "12 Cầu Giấy"
    assert "pickup_time" in data


@pytest.mark.parametrize("text,expected", [("mai 9h30", "2026-10-08T09:30:00+07:00"), ("sau 2 giờ", "2026-10-07T11:00:00+07:00")])
def test_common_short_clock_and_delay(text, expected):
    update = next(u for u in extract(text)["extracted_slots"] if u["slot_name"] == "pickup_time")
    assert normalize_pickup_time(update["value"], update["source_text"], "2026-10-07T09:00:00+07:00")["value"] == expected


def test_stops_and_notes_do_not_pollute_destination():
    data = values(extract("đón ở 12 Cầu Giấy sang Vincom rồi ghé Viện 108"))
    assert data["pickup"] == "12 Cầu Giấy"
    assert data["destination"] == "Vincom"
    assert data["stopovers"] == ["Viện 108"]


def test_vehicle_reply_does_not_invent_destination():
    result = extract("Đi ô tô bốn chỗ nhé", {"action_type": "ask_slot", "target_slots": ["vehicle_type"], "metadata": {}})
    assert values(result) == {"vehicle_type": "oto_4_cho"}


def test_bundled_vehicle_clause_keeps_destination_clean():
    result = extract("Đón ở 12 Cầu Giấy sang Viện 108, đi bốn chỗ bây giờ")
    assert values(result)["destination"] == "Viện 108"


def test_cancel_confirmation_accepts_huy_giup_toi():
    result = extract("Đúng rồi, hủy giúp tôi", {"action_type": "confirm_cancel", "target_slots": [], "metadata": {}})
    assert result["intents"] == ["confirm"]


@pytest.mark.parametrize("text", [
    "Tôi muốn thay điểm đến thì làm sao?",
    "Muốn hẹn đón vào ngày mai có được không?",
    "Trên đường tôi muốn ghé thêm một chỗ được không?",
    "Có thể xóa điểm dừng không?",
    "Hủy xe có mất phí không?",
])
def test_feature_questions_preserve_all_slots(text):
    result = extract(text, {"action_type": "confirm_booking", "target_slots": ["pickup", "destination", "vehicle_type", "pickup_time"], "metadata": {}})
    assert result["intents"] == ["ask_question"]
    assert result["extracted_slots"] == []


def test_live_feature_question_drops_unrequested_clear_updates(monkeypatch):
    class Client:
        def __init__(self, **_):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def create(self, **_):
            output = {"intents": ["change_info"], "extracted_slots": [
                {"slot_name": "pickup_time", "value": None, "source_text": "ngày mai", "metadata": {"operation": "clear"}},
                {"slot_name": "destination", "value": None, "source_text": "", "metadata": {"operation": "clear"}},
            ]}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))])
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=Client))
    monkeypatch.setattr(settings, "LLM_MODE", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-stub")
    result = extract("Muốn hẹn đón vào ngày mai có được không?")
    assert result["intents"] == ["ask_question"]
    assert result["extracted_slots"] == []


@pytest.mark.parametrize("target", ["pickup", "destination", "stopovers:0"])
@pytest.mark.parametrize("text", ["ở Bà Triệu", "tại Nguyễn Chí Thanh", "Bà Triệu ạ"])
def test_bare_place_reply_updates_only_the_clarification_target(target, text):
    slots = get_initial_booking_slots()
    slots["stopovers"] = [{"order": 1, "address": empty_address_slot()}]
    action = {"action_type": "clarify_address", "target_slots": [target], "metadata": {"type": "ab"}}
    result = extract(text, action, slots)
    assert set(values(result)) == {target}
    update = result["extracted_slots"][0]
    assert update["metadata"]["operation"] == "augment"
    assert result["addressed_slots"] == [target]
    assert result["clarification_response"] == "detail"


@pytest.mark.parametrize("kind", ["ab", "city", "narrow"])
def test_explicit_pickup_keeps_its_role_while_destination_is_being_clarified(kind):
    action = {"action_type": "clarify_address", "target_slots": ["destination"], "metadata": {"type": kind}}
    result = extract("đón tôi tại 12 Cầu Giấy", action, get_initial_booking_slots())
    assert values(result) == {"pickup": "12 Cầu Giấy"}
    assert result["addressed_slots"] == ["pickup"]


def test_explicit_destination_keeps_its_role_while_pickup_is_being_clarified():
    action = {"action_type": "clarify_address", "target_slots": ["pickup"], "metadata": {"type": "ab"}}
    result = extract("đi đến Viện 108", action, get_initial_booking_slots())
    assert values(result) == {"destination": "Viện 108"}
    assert result["addressed_slots"] == ["destination"]


def test_explicit_both_addresses_are_preserved_during_a_clarification():
    action = {"action_type": "clarify_address", "target_slots": ["destination"], "metadata": {"type": "ab"}}
    result = extract("đón tôi tại 12 Cầu Giấy sang Vincom Bà Triệu", action, get_initial_booking_slots())
    assert values(result) == {"pickup": "12 Cầu Giấy", "destination": "Vincom Bà Triệu"}


@pytest.mark.parametrize("text", ["cái 2", "địa điểm B", "số một"])
def test_open_branch_prompt_does_not_expose_hidden_candidate_order(text):
    slots = get_initial_booking_slots()
    slots["destination"]["candidates"] = [{"name": "Vincom Bà Triệu"}, {"name": "Vincom Nguyễn Chí Thanh"}]
    context = {
        "user_text": text, "booking_slots": slots,
        "last_bot_action": {"action_type": "clarify_address", "target_slots": ["destination"], "metadata": {"type": "ab"}},
        "recent_dialog_turns": [{"role": "bot", "content": "Mình muốn đến Vincom ở đường nào ạ?"}],
    }
    result = run_llm_extractor(context)
    assert result["extracted_slots"] == []
    assert result["intents"] == ["unclear"]
    assert len(slots["destination"]["candidates"]) == 2
    context["recent_dialog_turns"] = [{"role": "bot", "content": "Mình muốn đến Vincom Bà Triệu hay Vincom Nguyễn Chí Thanh ạ?"}]
    result = run_llm_extractor(context)
    assert result["extracted_slots"][0]["metadata"]["candidate_selection"] == (0 if text == "số một" else 1)


def test_live_bare_branch_reply_uses_focus_without_calling_provider(monkeypatch):
    class UnusedClient:
        def __init__(self, **_):
            raise AssertionError("A clear focus reply should not need a provider request")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=UnusedClient))
    monkeypatch.setattr(settings, "LLM_MODE", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-stub")
    action = {"action_type": "clarify_address", "target_slots": ["destination"], "metadata": {"type": "ab"}}
    assert values(extract("ở Bà Triệu", action, get_initial_booking_slots())) == {"destination": "Bà Triệu"}


def test_live_provider_cannot_select_unspoken_candidate_order(monkeypatch):
    class Client:
        def __init__(self, **_):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def create(self, **_):
            output = {"intents": ["provide_info"], "extracted_slots": [
                {"slot_name": "destination", "value": "Vincom Bà Triệu", "source_text": "cái một",
                 "metadata": {"operation": "augment", "candidate_selection": 0}},
            ], "addressed_slots": ["destination"]}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))])
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=Client))
    monkeypatch.setattr(settings, "LLM_MODE", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-stub")
    slots = get_initial_booking_slots()
    slots["destination"]["candidates"] = [{"name": "Vincom Bà Triệu"}, {"name": "Vincom Nguyễn Chí Thanh"}]
    result = run_llm_extractor({
        "user_text": "cái một đúng không?", "booking_slots": slots,
        "last_bot_action": {"action_type": "clarify_address", "target_slots": ["destination"], "metadata": {"type": "ab"}},
        "recent_dialog_turns": [{"role": "bot", "content": "Mình muốn đến Vincom ở đường nào ạ?"}],
    })
    assert result["extracted_slots"] == []
    assert result["intents"] == ["unclear"]


@pytest.mark.parametrize("target", ["destination", "stopovers:0"])
def test_bare_clarification_reply_can_include_other_booking_information(target):
    slots = get_initial_booking_slots()
    slots["stopovers"] = [{"order": 1, "address": empty_address_slot()}]
    action = {"action_type": "clarify_address", "target_slots": [target], "metadata": {"type": "ab"}}
    result = extract("ở Bà Triệu, xe bốn chỗ, 2 người", action, slots)
    assert values(result) == {"vehicle_type": "oto_4_cho", "passengers": 2, target: "Bà Triệu"}
    assert "pickup" not in values(result)
    assert next(update for update in result["extracted_slots"] if update["slot_name"] == target)["metadata"]["operation"] == "augment"



def test_live_mixed_branch_reply_preserves_role_and_other_entities(monkeypatch):
    class Client:
        def __init__(self, **_):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def create(self, **_):
            output = {"intents": ["provide_info"], "extracted_slots": [
                {"slot_name": "pickup", "value": "Bà Triệu", "source_text": "ở Bà Triệu", "metadata": {"operation": "replace"}},
                {"slot_name": "vehicle_type", "value": "oto_4_cho", "source_text": "bốn chỗ", "metadata": {}},
                {"slot_name": "pickup_time", "value": "+30m", "source_text": "sau 30 phút", "metadata": {}},
            ], "addressed_slots": ["pickup", "vehicle_type", "pickup_time"]}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))])
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=Client))
    monkeypatch.setattr(settings, "LLM_MODE", "groq")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-stub")
    action = {"action_type": "clarify_address", "target_slots": ["destination"], "metadata": {"type": "ab"}}
    result = extract("ở Bà Triệu, xe bốn chỗ, sau 30 phút", action, get_initial_booking_slots())
    assert values(result) == {"destination": "Bà Triệu", "vehicle_type": "oto_4_cho", "pickup_time": "+30m"}
    assert "pickup" not in result["addressed_slots"]
