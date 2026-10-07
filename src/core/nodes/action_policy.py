"""Node 6: action_policy_node. Read-only policy selecting the next bot action."""

from typing import Any, Dict, List
from src.core.state import BotAction, ParrotGoGraphState
from src.core.validators import (
    CORE_SLOTS,
    capacity_conflict,
    address_ready,
    address_targets,
    get_target,
    next_missing_requested_slot,
)


def action_result(kind: str, targets: List[str], status: str, **metadata: Any) -> Dict[str, Any]:
    """Helper formatting policy output."""
    action: BotAction = {
        "action_type": kind,  # type: ignore
        "target_slots": targets,
        "metadata": metadata,
    }
    return {
        "last_bot_action": action,
        "booking_status": status,
        "current_focus": targets[0] if targets else None,
    }


def action_policy_node(state: ParrotGoGraphState) -> Dict[str, Any]:
    """Select next bot action purely from read-only inspection of state."""
    status = state["booking_status"]
    slots = state["booking_slots"]
    intents = set(state.get("intents", []))
    retry = state.get("slot_retry_counts") or {}

    # Terminal states preservation
    if status == "canceled":
        return action_result("inform_canceled", [], status)
    if status in {"booked", "booking_pending"}:
        return action_result("inform_success", [], status)
    if status == "operator_required":
        return action_result("human_handoff", [], status, reason=state.get("handoff_reason"))

    if state.get("nlu_error"):
        subtype = "nlu_unavailable" if state.get("nlu_retry_count", 0) >= 2 else "nlu_retry"
        return action_result("general_reply", [], status, type=subtype)

    if state.get("tool_status") == "API_ERROR" and state.get("map_retry_count", 0) < 2:
        return action_result("general_reply", [], status, type="map_retry")

    reason = state.get("handoff_reason")
    if (
        "request_operator" in intents
        or reason
        or state.get("fallback_count", 0) >= 2
        or state.get("tool_status") == "API_ERROR"
        or retry.get("pickup", 0) >= 2
    ):
        reason = reason or (
            "operator_requested"
            if "request_operator" in intents
            else "api_error"
            if state.get("tool_status") == "API_ERROR"
            else "pickup_retry_limit"
            if retry.get("pickup", 0) >= 2
            else "fallback_limit"
        )
        return action_result("human_handoff", [], "operator_required", reason=reason)

    if "cancel" in intents or status == "cancel_pending":
        return action_result("confirm_cancel", [], "cancel_pending")

    if state.get("pending_modify_target"):
        return action_result("general_reply", [], "collecting", type="ask_modify_slot")

    if "repeat_request" in intents and not state.get("turn_extracted_slots"):
        previous = state.get("last_bot_action") or {}
        if previous:
            meta = {**(previous.get("metadata") or {}), "repeat_previous": True}
            return action_result(
                previous["action_type"],
                previous.get("target_slots") or [],
                status,
                **meta,
            )

    if capacity_conflict(slots):
        return action_result(
            "general_reply", ["vehicle_type"], "collecting", type="capacity_conflict",
            passengers=slots["passengers"]["value"],
            vehicle_type=slots["vehicle_type"]["value"],
        )

    # Proposals requiring confirmation (CRM / Fuzzy)
    for target in address_targets(slots):
        slot = get_target(slots, target)
        if slot.get("requires_confirmation"):
            return action_result(
                "confirm_slots", [target], "collecting", type="proposed_address"
            )

    # Mega POI gate clarification
    pickup = slots["pickup"]
    if pickup.get("is_mega_poi") and not pickup.get("gate_resolved"):
        return action_result("clarify_address", ["pickup"], "collecting", type="mega_poi_gate")

    # Address slots needing clarification
    for target in address_targets(slots):
        slot = get_target(slots, target)
        if slot.get("status") == "needs_clarification":
            return action_result(
                "clarify_address",
                [target],
                "collecting",
                type=slot.get("clarification_kind") or "narrow",
            )

    # Ready to book -> Confirm booking
    if state.get("ready_to_book"):
        return action_result(
            "confirm_booking",
            CORE_SLOTS,
            "confirming",
            booking_revision=state.get("booking_revision", 0),
            suppress_action_text=(
                "ask_question" in intents
                and not state.get("turn_extracted_slots")
                and (state.get("last_bot_action") or {}).get("action_type") == "confirm_booking"
                and ((state.get("last_bot_action") or {}).get("metadata") or {}).get("booking_revision") == state.get("booking_revision", 0)
            ),
        )

    if intents == {"unclear"}:
        return action_result("general_reply", [], status, type="unclear_prompt")

    if "chit_chat" in intents and slots["pickup"]["status"] == "empty":
        return action_result("general_reply", ["pickup"], status, type="greeting")

    # Ask missing slot
    missing = next_missing_requested_slot(slots, state["turn_received_at"])
    if missing is None:
        raise ValueError("State không ready nhưng không xác định được slot cần xử lý")

    turn_updates = state.get("turn_extracted_slots", [])
    if missing == "pickup" and address_ready(slots["destination"], "destination"):
        if any(u.get("slot_name") == "destination" for u in turn_updates):
            # Customer reiterated destination while bot was waiting for pickup
            return action_result("ask_slot", ["pickup"], "collecting", type="explain_destination_ask_pickup")

    if missing == "destination" and address_ready(slots["pickup"], "pickup"):
        if any(u.get("slot_name") == "pickup" for u in turn_updates):
            # Customer reiterated pickup while bot was waiting for destination
            return action_result("ask_slot", ["destination"], "collecting", type="explain_pickup_ask_destination")

    return action_result("ask_slot", [missing], "collecting")
