"""Node 4: state_reducer_node. Single authority for mutating booking_slots, revision, and readiness."""

import copy
from typing import Any, Dict

from src.core.state import (
    AddressSlot,
    BookingSlots,
    ParrotGoGraphState,
    empty_address_slot,
    empty_value_slot,
)
from src.core.time_utils import normalize_pickup_time, valid_time
from src.core.validators import (
    CORE_SLOTS,
    VEHICLES,
    address_ready,
    address_targets,
    check_is_ready_to_book,
    get_target,
    relative_destination_known,
    set_target,
    target_role,
)
from src.db.in_memory_cache import geo_cache
from src.services.map_resolver import join_notes


def merge_map_results(slots: BookingSlots, map_res: Dict[str, Any]) -> None:
    """Apply map service address resolutions and stopover operations."""
    if not map_res:
        return

    addresses = map_res.get("addresses") or {}
    for target, addr_slot in addresses.items():
        if target in {"pickup", "destination"}:
            slots[target] = copy.deepcopy(addr_slot)
        elif target.startswith("stopovers:"):
            idx = int(target.split(":")[1])
            if idx < len(slots.get("stopovers", [])):
                slots["stopovers"][idx]["address"] = copy.deepcopy(addr_slot)

    stopover_op = map_res.get("stopover_operation")
    if stopover_op:
        op = stopover_op.get("operation")
        if op == "clear":
            slots["stopovers"] = []
        elif op == "replace":
            slots["stopovers"] = copy.deepcopy(stopover_op.get("items", []))


def invalidate_target(slots: BookingSlots, target: str) -> None:
    """Invalidate slot upon denial: keep raw for context but reset candidate/coords."""
    if target in {"pickup", "destination"} or target.startswith("stopovers:"):
        slot = get_target(slots, target)
        raw_val = slot.get("raw")
        inv = empty_address_slot()
        inv["raw"] = raw_val
        inv["status"] = "needs_clarification"
        set_target(slots, target, inv)
    elif target in {"vehicle_type", "passengers"}:
        set_target(slots, target, {"value": None, "status": "needs_clarification"})
    elif target == "pickup_time":
        slots["pickup_time"]["value"] = None
        slots["pickup_time"]["status"] = "needs_clarification"


def clear_booking_target(slots: BookingSlots, target: str) -> None:
    """Completely clear slot to empty schema."""
    if target in {"pickup", "destination"}:
        slots[target] = empty_address_slot()
    elif target == "stopovers":
        slots["stopovers"] = []
    elif target.startswith("stopovers:"):
        idx = int(target.split(":")[1])
        if idx < len(slots.get("stopovers", [])):
            slots["stopovers"].pop(idx)
            # Reorder
            for i, s in enumerate(slots["stopovers"]):
                s["order"] = i + 1
    elif target in {"vehicle_type", "passengers"}:
        slots[target] = empty_value_slot()
    elif target == "general_note":
        slots["general_note"] = None


def apply_verified_default_gate(slot: AddressSlot, gate: Dict[str, Any]) -> None:
    """Apply verified default gate record to Mega POI address slot."""
    slot["gate_id"] = gate["gate_id"]
    slot["coords"] = {"lat": gate["lat"], "lng": gate["lng"]}
    slot["location_precision"] = "anchor"
    slot["gate_resolved"] = True
    slot["default_point_used"] = True
    slot["status"] = "extracted"
    slot["note"] = join_notes(
        slot.get("note"),
        gate.get("driver_instruction"),
        f"Điểm đón mặc định tại {gate.get('gate_code')}.",
    )


def state_reducer_node(state: ParrotGoGraphState) -> Dict[str, Any]:
    """Execute state reduction logic: merge updates, handle deny/confirm, compute ready_to_book."""
    slots = copy.deepcopy(state["booking_slots"])
    before = copy.deepcopy(slots)
    updates = state.get("turn_extracted_slots", [])
    intents = set(state.get("intents", []))
    last = state.get("last_bot_action") or {}
    last_type = last.get("action_type")
    targets = last.get("target_slots") or []
    last_meta = last.get("metadata") or {}
    retry = dict(state.get("slot_retry_counts") or {})
    pending = state.get("pending_modify_target", False)
    reason = state.get("handoff_reason")
    status = state.get("booking_status", "collecting")
    city = state.get("session_city")
    edits = bool(updates)

    map_res = state.get("map_service_result") or {}
    merge_map_results(slots, map_res)

    for item in updates:
        name, val = item["slot_name"], item["value"]
        meta = item.get("metadata") or {}
        if meta.get("operation") == "clear":
            if name == "session_city":
                city = None
            elif name == "pickup_time":
                slots[name] = normalize_pickup_time(
                    None, item.get("source_text"), state["turn_received_at"], state["timezone"]
                )
            else:
                clear_booking_target(slots, name)
        elif name == "pickup_time":
            slots[name] = normalize_pickup_time(
                val, item.get("source_text"), state["turn_received_at"], state["timezone"]
            )
        elif name in {"vehicle_type", "passengers"}:
            valid = (isinstance(val, str) and val in VEHICLES) if name == "vehicle_type" else (
                isinstance(val, int) and not isinstance(val, bool) and val > 0
            )
            slots[name] = {
                "value": val,
                "status": "extracted" if valid else "needs_clarification",
            }
        elif name == "general_note":
            slots[name] = val
        elif name == "session_city":
            city = val

    if edits:
        pending = False
        if status not in {"cancel_pending", "canceled", "operator_required"}:
            status = "collecting"
        slots["distance_km"] = None
        slots["duration_minutes"] = None

    time_slot = slots["pickup_time"]
    if (
        time_slot["status"] == "empty"
        and time_slot["value"] is None
        and time_slot["raw"] is None
        and (slots["pickup"]["raw"] or slots["destination"]["raw"])
    ):
        slots["pickup_time"] = {
            "value": "now",
            "raw": None,
            "anchored_at": None,
            "status": "extracted",
        }
    elif time_slot["value"] is not None and not valid_time(time_slot, state["turn_received_at"]):
        time_slot["status"] = "needs_clarification"

    # Reset retry for voluntary replacements
    addressed = set(state.get("turn_addressed_slots", []))
    for item in updates:
        name = item["slot_name"]
        if (
            name in address_targets(slots)
            and name not in addressed
            and (item.get("metadata") or {}).get("operation", "replace") == "replace"
        ):
            retry[name] = 0

    if "change_info" in intents and not edits:
        pending = True

    # Deny without replacement
    replaced = {u["slot_name"] for u in updates}
    if "stopovers" in replaced:
        replaced.update(t for t in targets if t.startswith("stopovers:"))

    unknown_answer = (
        last_type == "clarify_address"
        and (state.get("clarification_response") == "unknown")
    )

    if "cancel" not in intents and "deny" in intents:
        if last_type == "confirm_cancel":
            status = "collecting"
        elif last_type in {"confirm_slots", "clarify_address"} and not unknown_answer:
            if len(targets) == 1 and targets[0] not in replaced:
                invalidate_target(slots, targets[0])
            elif not edits and len(targets) > 1:
                pending = True
        elif last_type == "confirm_booking":
            status = "collecting"
            pending = not edits

    # Address clarification response counting & retry
    response = state.get("clarification_response")
    if last_type == "clarify_address":
        for target in targets:
            if target not in addressed:
                continue
            slot = get_target(slots, target)
            role = target_role(target)
            if address_ready(slot, role):
                retry[target] = 0
                continue
            previous_slot = get_target(state["booking_slots"], target)
            previous_kind = previous_slot.get("clarification_kind")
            next_kind = slot.get("clarification_kind")
            advanced = bool(next_kind and previous_kind and next_kind != previous_kind)
            retry[target] = 0 if advanced else retry.get(target, 0) + 1
            if last_meta.get("type") == "mega_poi_gate" and response == "unknown":
                gate = geo_cache.lookup_default_gate(slot.get("place_id"), "pickup", allow_unverified=False)
                if gate:
                    apply_verified_default_gate(slot, gate)
                    retry[target] = 0
                else:
                    reason = "missing_safe_pickup"
            elif role == "destination":
                if response != "reject_candidates" and relative_destination_known(slot):
                    slot["status"] = "extracted"
                    slot["requires_confirmation"] = False
                    slot["note"] = join_notes(
                        slot.get("note"),
                        "Điểm đến tương đối; trao đổi chi tiết khi gần đến nơi.",
                    )
                    retry[target] = 0
                elif response in {"unknown", "reject_candidates"} or retry[target] > 3:
                    reason = "destination_unresolved"
            elif role == "stopover":
                if response in {"unknown", "reject_candidates"} or retry[target] > 3:
                    reason = "stopover_unresolved"
            elif slot.get("clarification_kind") == "landmark" or response == "reject_candidates":
                reason = "pickup_unresolved"

    for target in address_targets(slots):
        if address_ready(get_target(slots, target), target_role(target)):
            retry[target] = 0

    # Confirm handling
    if "confirm" in intents and "deny" not in intents and "cancel" not in intents:
        if last_type == "confirm_cancel":
            status = "canceled"
        elif last_type == "confirm_slots":
            for target in targets:
                if target not in replaced:
                    slot = get_target(slots, target)
                    candidate = {**slot, "requires_confirmation": False}
                    if relative_destination_known(candidate):
                        slot["requires_confirmation"] = False
                        if address_ready(candidate, target_role(target)):
                            slot["status"] = "confirmed"
                        else:
                            slot["status"] = "needs_clarification"
                            slot["clarification_kind"] = "narrow"
        elif last_type == "confirm_booking":
            revision_matches = (
                last_meta.get("booking_revision") == state.get("booking_revision", 0)
            )
            allowed = (
                not edits
                and "change_info" not in intents
                and revision_matches
                and not pending
                and not reason
                and "request_operator" not in intents
                and state.get("fallback_count", 0) < 2
                and state.get("tool_status") != "API_ERROR"
                and check_is_ready_to_book(slots, state["turn_received_at"])
            )
            if allowed:
                for name in CORE_SLOTS:
                    slots[name]["status"] = "confirmed"
                for stop in slots.get("stopovers", []):
                    stop["address"]["status"] = "confirmed"
                if slots["passengers"]["status"] != "empty":
                    slots["passengers"]["status"] = "confirmed"
                status = "booking_pending"
            elif status != "cancel_pending":
                status = "collecting"

    # Compute ready_to_book after all mutations
    ready = (
        check_is_ready_to_book(slots, state["turn_received_at"])
        and not pending
        and not reason
        and state.get("tool_status") != "API_ERROR"
    )
    if status in {"collecting", "ready_to_book", "confirming"}:
        status = "ready_to_book" if ready else "collecting"

    return {
        "map_retry_count": (state.get("map_retry_count", 0) + 1) if state.get("tool_status") == "API_ERROR" else (0 if state.get("tool_status") is not None else state.get("map_retry_count", 0)),
        "booking_slots": slots,
        "slot_retry_counts": retry,
        "pending_modify_target": pending,
        "handoff_reason": reason,
        "booking_revision": state.get("booking_revision", 0) + int(slots != before or city != state.get("session_city")),
        "session_city": city,
        "ready_to_book": ready,
        "booking_status": status,
    }
