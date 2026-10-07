"""Regressions for malformed NLU, storage recovery and independent sessions."""

import pytest

from src.config import Settings
from src.cli.runner import SessionRunner
from src.core.state import create_initial_state, empty_address_slot
from src.core.nodes.action_policy import action_policy_node
from src.core.nodes.state_reducer import state_reducer_node
from src.core.validators import capacity_conflict, check_is_ready_to_book, validate_extractor_output
from src.db.sqlite_manager import PersistenceError


@pytest.mark.parametrize("item", [
    {"slot_name": "vehicle_type", "value": {"type": "oto_4_cho"}},
    {"slot_name": "passengers", "value": True},
    {"slot_name": "pickup", "value": ["12 Cầu Giấy"]},
    {"slot_name": "general_note", "value": {"note": "help"}},
    {"slot_name": "unknown_field", "value": "text"},
    {"slot_name": "stopovers:-1", "value": "12 Cầu Giấy"},
    {"slot_name": "stopovers:999", "value": "12 Cầu Giấy"},
    {"slot_name": "stopovers", "value": [{"value": {"raw": "12 Cầu Giấy"}}]},
])
def test_invalid_edit_cannot_turn_into_confirmation(item):
    output = validate_extractor_output({"intents": ["confirm", "change_info"], "extracted_slots": [item]})
    assert not output["extracted_slots"]
    assert "confirm" not in output["intents"]
    state = create_initial_state("typed", "0000000000", "Test", "2026-10-08T09:00:00+07:00")
    state["intents"] = output["intents"]
    state["turn_extracted_slots"] = output["extracted_slots"]
    assert state_reducer_node(state)["booking_status"] != "booking_pending"


def test_explicit_dotenv_mock_is_respected(tmp_path, monkeypatch):
    for key in ["MAP_MODE", "LLM_MODE", "VIETMAP_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"]:
        monkeypatch.delenv(key, raising=False)
    config = tmp_path / "test.env"
    config.write_text("MAP_MODE=mock\nLLM_MODE=mock\nVIETMAP_API_KEY=placeholder\nGROQ_API_KEY=placeholder\n", encoding="utf-8")
    loaded = Settings(_env_file=config)
    assert loaded.MAP_MODE == "mock"
    assert loaded.LLM_MODE == "mock"


def _ready_state():
    state = create_initial_state("capacity", "0000000000", "Test", "2026-10-08T09:00:00+07:00", session_city="Hà Nội")
    for role in ["pickup", "destination"]:
        address = empty_address_slot()
        address.update(raw=role, formatted=role, coords={"lat": 21.03, "lng": 105.8},
                       components={"province_city": "Hà Nội"}, location_precision="exact", status="extracted")
        state["booking_slots"][role] = address
    state["booking_slots"]["pickup_time"] = {"value": "now", "raw": None, "anchored_at": None, "status": "extracted"}
    state["booking_slots"]["vehicle_type"] = {"value": "xe_may", "status": "extracted"}
    state["booking_slots"]["passengers"] = {"value": 5, "status": "extracted"}
    return state


def test_capacity_conflict_blocks_booking_and_keeps_customer_count():
    state = _ready_state()
    assert capacity_conflict(state["booking_slots"])
    assert not check_is_ready_to_book(state["booking_slots"], state["turn_received_at"])
    action = action_policy_node(state)
    assert action["last_bot_action"]["metadata"]["type"] == "capacity_conflict"
    assert state["booking_slots"]["passengers"]["value"] == 5


def _collect_ready(runner):
    runner.handle_turn("Đón tôi ở 12 Cầu Giấy")
    runner.handle_turn("Đi đến Viện 108")
    text = runner.handle_turn("Xe bốn chỗ")
    assert "đúng chưa" in text.lower()


def test_failed_booking_commit_remains_retryable_and_books_once(tmp_path, monkeypatch):
    runner = SessionRunner("0000000001", "Test", city="Hà Nội", db_path=str(tmp_path / "retry.db"))
    _collect_ready(runner)
    persist = runner.db.persist_turn
    def fail_once(state):
        monkeypatch.setattr(runner.db, "persist_turn", persist)
        raise PersistenceError("injected failure")
    monkeypatch.setattr(runner.db, "persist_turn", fail_once)
    response = runner.handle_turn("Đúng rồi em")
    assert "chưa lưu" in response
    assert not runner.is_session_terminal()
    state = runner.graph.get_state({"configurable": {"thread_id": runner.session_id}}).values
    assert state["booking_status"] == "confirming"
    assert state["persistence_error"] == "commit_failed"
    with runner.db.get_connection() as conn:
        assert conn.execute("SELECT count(*) FROM bookings").fetchone()[0] == 0
    response = runner.handle_turn("Đúng rồi em")
    assert "thành công" in response
    assert runner.is_session_terminal()
    with runner.db.get_connection() as conn:
        assert conn.execute("SELECT count(*) FROM bookings").fetchone()[0] == 1
        assert conn.execute("SELECT total_trips FROM customers WHERE phone=?", (runner.phone,)).fetchone()[0] == 1


def test_runners_with_different_databases_are_independent(tmp_path):
    first = SessionRunner("0000000002", "First", city="Hà Nội", db_path=str(tmp_path / "first.db"))
    first.start_new_session()
    second = SessionRunner("0000000003", "Second", city="Hà Nội", db_path=str(tmp_path / "second.db"))
    second.start_new_session()
    first.handle_turn("Xin chào")
    second.handle_turn("Xin chào")
    for runner in [first, second]:
        with runner.db.get_connection() as conn:
            assert conn.execute("SELECT count(*) FROM session_messages WHERE session_id=?", (runner.session_id,)).fetchone()[0] == 1


def test_first_map_error_does_not_end_session():
    state = _ready_state()
    state["booking_slots"]["passengers"] = {"value": None, "status": "empty"}
    state["tool_status"] = "API_ERROR"
    state["map_retry_count"] = 1
    result = action_policy_node(state)
    assert result["last_bot_action"]["metadata"]["type"] == "map_retry"
    assert result["booking_status"] != "operator_required"


def test_nlu_service_failure_does_not_book_ready_state():
    state = _ready_state()
    state["booking_slots"]["passengers"] = {"value": None, "status": "empty"}
    state["ready_to_book"] = True
    state["nlu_error"] = {"provider": "groq", "code": "service_error"}
    state["nlu_retry_count"] = 1
    result = action_policy_node(state)
    assert result["last_bot_action"]["metadata"]["type"] == "nlu_retry"
    assert result["booking_status"] != "booking_pending"


@pytest.mark.parametrize("raw_slots", [None, {}, "bad", []])
def test_malformed_or_missing_change_payload_cannot_confirm(raw_slots):
    state = _ready_state()
    state["booking_slots"]["passengers"] = {"value": None, "status": "empty"}
    state["last_bot_action"] = {"action_type": "confirm_booking", "target_slots": ["pickup", "destination", "vehicle_type", "pickup_time"], "metadata": {"booking_revision": 0}}
    state["booking_status"] = "confirming"
    output = validate_extractor_output({"intents": ["confirm", "change_info"], "extracted_slots": raw_slots})
    state["intents"] = output["intents"]
    state["turn_extracted_slots"] = output["extracted_slots"]
    reduced = state_reducer_node(state)
    assert reduced["booking_status"] != "booking_pending"
    assert reduced["pending_modify_target"]


def test_reducer_blocks_unresolved_change_even_without_nlu_validator():
    state = _ready_state()
    state["booking_slots"]["passengers"] = {"value": None, "status": "empty"}
    state["last_bot_action"] = {"action_type": "confirm_booking", "target_slots": ["pickup"], "metadata": {"booking_revision": 0}}
    state["intents"] = ["confirm", "change_info"]
    assert state_reducer_node(state)["booking_status"] != "booking_pending"


def test_city_to_branch_clarification_is_progress_not_handoff():
    state = create_initial_state("branch", "0000000000", "Test", "2026-10-08T09:00:00+07:00")
    previous = empty_address_slot()
    previous.update(raw="vincom", status="needs_clarification", clarification_kind="city")
    state["booking_slots"]["destination"] = previous
    resolved = empty_address_slot()
    resolved.update(raw="vincom, Hà Nội", status="needs_clarification", clarification_kind="ab",
                    candidates=[{"formatted": "Vincom Bà Triệu"}, {"formatted": "Vincom Royal City"}])
    state["map_service_result"] = {"addresses": {"destination": resolved}}
    state["turn_extracted_slots"] = [{"slot_name": "session_city", "value": "Hà Nội", "source_text": "Hà Nội", "metadata": {}}]
    state["last_bot_action"] = {"action_type": "clarify_address", "target_slots": ["destination"], "metadata": {"type": "city"}}
    state["turn_addressed_slots"] = ["destination"]
    state["clarification_response"] = "detail"
    state.update(state_reducer_node(state))
    assert state["handoff_reason"] is None
    assert state["slot_retry_counts"]["destination"] == 0
    action = action_policy_node(state)
    assert action["last_bot_action"]["action_type"] == "clarify_address"
    assert action["last_bot_action"]["metadata"]["type"] == "ab"


def test_explicit_nationwide_overrides_default_city(tmp_path, monkeypatch):
    from src.config import settings
    monkeypatch.setattr(settings, "DEFAULT_SESSION_CITY", "Hà Nội")
    runner = SessionRunner("0000000000", "Test", city="toàn quốc", db_path=str(tmp_path / "nationwide.db"))
    assert runner.city is None
