"""Node 2: extract NLU with complete context and recoverable provider diagnostics."""

from typing import Any, Dict
from src.core.state import ParrotGoGraphState
from src.services.llm_extractor import ExtractorServiceError, run_llm_extractor


def extract_slots_summary(slots: Any) -> Dict[str, Any]:
    return {
        "pickup": slots.get("pickup", {}).get("formatted") or slots.get("pickup", {}).get("raw"),
        "destination": slots.get("destination", {}).get("formatted") or slots.get("destination", {}).get("raw"),
        "vehicle_type": slots.get("vehicle_type", {}).get("value"),
        "pickup_time": slots.get("pickup_time", {}).get("value"),
    }


def extractor_node(state: ParrotGoGraphState) -> Dict[str, Any]:
    context = {
        "user_text": state["user_current_input"],
        "session_city": state.get("session_city"),
        "timezone": state["timezone"],
        "turn_received_at": state["turn_received_at"],
        "last_bot_action": state.get("last_bot_action"),
        "booking_status": state.get("booking_status"),
        "booking_slots": state.get("booking_slots") or {},
        "existing_slots_summary": extract_slots_summary(state.get("booking_slots") or {}),
        "recent_dialog_turns": state.get("messages", [])[-6:],
    }
    error = None
    try:
        result = run_llm_extractor(context)
    except ExtractorServiceError as exc:
        error = {"provider": exc.provider, "code": exc.code}
        result = {"intents": ["unclear"], "primary_intent": "unclear", "extracted_slots": [], "addressed_slots": [], "clarification_response": None, "confidence": 0.0}
    except Exception:
        error = {"provider": "extractor", "code": "internal_error"}
        result = {"intents": ["unclear"], "primary_intent": "unclear", "extracted_slots": [], "addressed_slots": [], "clarification_response": None, "confidence": 0.0}
    misunderstood = result["intents"] == ["unclear"] and not result["extracted_slots"]
    return {
        "intents": result["intents"],
        "primary_intent": result["primary_intent"],
        "turn_extracted_slots": result["extracted_slots"],
        "turn_addressed_slots": result["addressed_slots"],
        "clarification_response": result["clarification_response"],
        "nlu_error": error,
        "nlu_retry_count": state.get("nlu_retry_count", 0) + 1 if error else 0,
        "fallback_count": state.get("fallback_count", 0) if error else state.get("fallback_count", 0) + 1 if misunderstood else 0,
    }
