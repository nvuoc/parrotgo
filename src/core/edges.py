"""Conditional edge routing functions for ParrotGo LangGraph."""

from src.core.state import ParrotGoGraphState


def route_after_extractor(state: ParrotGoGraphState) -> str:
    """Route to map_service_node if any location or city slots were updated."""
    turn_slots = state.get("turn_extracted_slots", [])
    if any(
        s.get("slot_name") in {"pickup", "destination", "stopovers", "session_city"}
        or str(s.get("slot_name", "")).startswith("stopovers:")
        for s in turn_slots
    ):
        return "map_service_node"
    return "state_reducer_node"


def route_after_reducer(state: ParrotGoGraphState) -> str:
    """Route to qa_dispatcher_node if user asked questions."""
    intents = state.get("intents", [])
    if "ask_question" in intents:
        return "qa_dispatcher_node"
    return "action_policy_node"


def route_turn_outcome(state: ParrotGoGraphState) -> str:
    """Determine whether turn terminates the session or continues."""
    if state.get("is_terminal"):
        return "terminate_session"
    return "end_turn"
