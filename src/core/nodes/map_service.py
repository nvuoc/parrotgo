"""Node 3: map_service_node. Resolves pickup, destination, stopovers, and city updates."""

from typing import Any, Dict
from src.core.state import ParrotGoGraphState
from src.core.validators import STATUS_SEVERITY
from src.services.map_resolver import prepare_address_updates, resolve_address_update


def map_service_node(state: ParrotGoGraphState) -> Dict[str, Any]:
    """Resolve all address and location slots in the current turn."""
    updates = state.get("turn_extracted_slots", [])
    city = next(
        (s["value"] for s in reversed(updates) if s["slot_name"] == "session_city"),
        state.get("session_city"),
    )
    prepared, stopover_operation = prepare_address_updates(state, city)

    results: Dict[str, Any] = {}
    overall = "SUCCESS"

    for target, update in prepared:
        result = resolve_address_update(
            update=update,
            target=target,
            session_city=city,
            existing_slots=state["booking_slots"],
            crm_profile=state.get("crm_profile"),
        )
        if stopover_operation and target.startswith("stopovers:"):
            index = int(target.split(":")[1])
            if index < len(stopover_operation["items"]):
                stopover_operation["items"][index]["address"] = result["slot"]
        else:
            results[target] = result["slot"]

        tool_stat = result["tool_status"]
        if STATUS_SEVERITY.get(tool_stat, 1) > STATUS_SEVERITY.get(overall, 1):
            overall = tool_stat

    return {
        "map_service_result": {
            "addresses": results,
            "stopover_operation": stopover_operation,
        },
        "tool_status": overall,
        "session_city": city,
    }
