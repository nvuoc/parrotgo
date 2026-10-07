"""Node 1: session_init_node. Resets turn-level fields while preserving session state."""

from typing import Any, Dict
from src.core.state import ParrotGoGraphState, get_initial_booking_slots
from src.core.time_utils import parse_aware
from src.db.sqlite_manager import get_default_db_manager


def session_init_node(state: ParrotGoGraphState, db_manager=None) -> Dict[str, Any]:
    """Initialize turn state, check terminal invariant, advance turn index."""
    if state.get("is_terminal") or state.get("booking_status") in {
        "booked", "canceled", "operator_required"
    }:
        raise ValueError("Phiên đã kết thúc; cần session_id mới")

    # Validate timestamp format
    parse_aware(state["turn_received_at"])

    crm = state.get("crm_profile")
    if crm is None and state.get("customer_phone"):
        try:
            db_manager = db_manager or get_default_db_manager()
            crm = db_manager.get_customer_crm_profile(state["customer_phone"])
        except Exception:
            crm = None

    return {
        "booking_slots": state.get("booking_slots") or get_initial_booking_slots(),
        "crm_profile": crm,
        "session_city": state.get("session_city"),
        "fallback_count": state.get("fallback_count", 0),
        "slot_retry_counts": state.get("slot_retry_counts") or {},
        "pending_modify_target": state.get("pending_modify_target", False),
        "handoff_reason": state.get("handoff_reason"),
        "booking_revision": state.get("booking_revision", 0),
        "booking_status": state.get("booking_status", "collecting"),
        "booking_id": state.get("booking_id"),
        "turn_index": state.get("turn_index", 0) + 1,
        "is_terminal": False,
        "intents": [],
        "primary_intent": None,
        "turn_extracted_slots": [],
        "turn_addressed_slots": [],
        "clarification_response": None,
        "map_service_result": None,
        "qa_response": None,
        "nlu_error": None,
        "nlu_retry_count": state.get("nlu_retry_count", 0),
        "map_retry_count": state.get("map_retry_count", 0),
        "persistence_error": None,
        "tool_status": None,
        "final_response_text": "",
    }
