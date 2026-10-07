"""Runtime validators and helper checks for state and NLU/Map components."""

import re
from typing import Any, Dict, List, Optional

from src.core.state import (
    BookingSlots,
    ExtractedSlotUpdate,
)
from src.core.time_utils import valid_coords, valid_time
from src.config import settings

CORE_SLOTS = ["pickup", "destination", "vehicle_type", "pickup_time"]
VALID_STATUS = {"extracted", "confirmed"}
VEHICLES = {"xe_may", "oto_4_cho", "oto_7_cho"}
STATUS_SEVERITY = {"SUCCESS": 1, "AMBIGUOUS": 2, "NOT_FOUND": 3, "API_ERROR": 4}

VALID_INTENTS = {
    "provide_info",
    "change_info",
    "confirm",
    "deny",
    "cancel",
    "ask_question",
    "chit_chat",
    "request_operator",
    "repeat_request",
    "unclear",
}

INTENT_PRIORITY_ORDER = [
    "request_operator",
    "cancel",
    "deny",
    "change_info",
    "provide_info",
    "confirm",
    "ask_question",
    "repeat_request",
    "chit_chat",
    "unclear",
]


def relative_destination_known(slot: Any) -> bool:
    """Check if destination has enough ground truth (name/formatted, province_city, valid precision)."""
    if not isinstance(slot, dict):
        return False
    formatted_value = slot.get("formatted")
    formatted = formatted_value.strip() if isinstance(formatted_value, str) else ""
    components = slot.get("components") or {}
    if not isinstance(components, dict):
        return False
    city = components.get("province_city")
    precision = slot.get("location_precision")
    return (
        bool(formatted)
        and isinstance(city, str) and bool(city.strip())
        and precision in {"exact", "anchor", "road", "ward", "poi"}
    )


def address_ready(slot: Any, role: str) -> bool:
    """Verify if an address slot is fully ready for booking."""
    if not isinstance(slot, dict):
        return False
    if slot.get("status") not in VALID_STATUS or slot.get("requires_confirmation"):
        return False

    if role == "pickup":
        if not valid_coords(slot.get("coords")):
            return False
        if slot.get("location_precision") not in {"exact", "anchor"}:
            return False
    elif role == "destination":
        if not relative_destination_known(slot):
            return False
    elif role == "stopover":
        if not valid_coords(slot.get("coords")) or slot.get("location_precision") not in {"exact", "anchor"}:
            return False

    if slot.get("is_mega_poi") and role in {"pickup", "stopover"}:
        if not slot.get("gate_resolved"):
            return False

    if slot.get("default_point_used"):
        if not (
            slot.get("gate_id")
            and valid_coords(slot.get("coords"))
            and slot.get("note")
        ):
            return False

    return True


def positive_passengers(slot: Any) -> bool:
    """Verify passengers slot has a positive integer."""
    if not isinstance(slot, dict):
        return False
    val = slot.get("value")
    return isinstance(val, int) and not isinstance(val, bool) and val > 0


def capacity_conflict(slots: BookingSlots) -> bool:
    """Check configured fleet limits without discarding the customer's count."""
    count = slots.get("passengers", {}).get("value")
    vehicle = slots.get("vehicle_type", {}).get("value")
    limits = {
        "xe_may": settings.MAX_PASSENGERS_XE_MAY,
        "oto_4_cho": settings.MAX_PASSENGERS_OTO_4_CHO,
        "oto_7_cho": settings.MAX_PASSENGERS_OTO_7_CHO,
    }
    return (
        isinstance(count, int) and not isinstance(count, bool)
        and isinstance(vehicle, str) and vehicle in limits
        and count > limits[vehicle]
    )


def check_is_ready_to_book(slots: BookingSlots, received_at: str) -> bool:
    """Determine if booking_slots meets all core requirements."""
    return (
        address_ready(slots["pickup"], "pickup")
        and address_ready(slots["destination"], "destination")
        and slots["vehicle_type"]["status"] in VALID_STATUS
        and isinstance(slots["vehicle_type"]["value"], str)
        and slots["vehicle_type"]["value"] in VEHICLES
        and not capacity_conflict(slots)
        and valid_time(slots["pickup_time"], received_at)
        and all(address_ready(s["address"], "stopover") for s in slots.get("stopovers", []))
        and (
            slots["passengers"]["status"] == "empty"
            or (
                positive_passengers(slots["passengers"])
                and slots["passengers"]["status"] in VALID_STATUS
            )
        )
    )


def get_target(slots: BookingSlots, target: str) -> Any:
    """Retrieve slot or stopover address by target string."""
    if target.startswith("stopovers:"):
        idx = int(target.split(":")[1])
        return slots["stopovers"][idx]["address"]
    return slots[target]


def set_target(slots: BookingSlots, target: str, value: Any) -> None:
    """Set slot or stopover address by target string."""
    if target.startswith("stopovers:"):
        idx = int(target.split(":")[1])
        slots["stopovers"][idx]["address"] = value
    else:
        slots[target] = value


def address_targets(slots: BookingSlots) -> List[str]:
    """List of all address targets (pickup, destination, stopovers)."""
    return ["pickup", "destination"] + [
        f"stopovers:{i}" for i in range(len(slots.get("stopovers", [])))
    ]


def target_role(target: str) -> str:
    """Extract role from target string."""
    return "stopover" if target.startswith("stopovers:") else target


def next_missing_requested_slot(slots: BookingSlots, received_at: str) -> Optional[str]:
    """Find the next missing or invalid slot in priority order.
    
    Order: pickup -> destination -> vehicle_type -> pickup_time -> stopovers -> passengers.
    """
    if not address_ready(slots["pickup"], "pickup"):
        return "pickup"
    if not address_ready(slots["destination"], "destination"):
        return "destination"
    if (
        slots["vehicle_type"]["status"] not in VALID_STATUS
        or not isinstance(slots["vehicle_type"]["value"], str)
        or slots["vehicle_type"]["value"] not in VEHICLES
    ):
        return "vehicle_type"
    if capacity_conflict(slots):
        return "vehicle_type"
    if not valid_time(slots["pickup_time"], received_at):
        return "pickup_time"

    # Stopovers that were requested but not ready
    for i, s in enumerate(slots.get("stopovers", [])):
        if not address_ready(s["address"], "stopover"):
            return f"stopovers:{i}"

    # Passengers if explicitly specified but invalid
    passengers = slots.get("passengers", {})
    if passengers.get("status") not in {"empty", "confirmed", "extracted"} or (
        passengers.get("status") in {"extracted", "confirmed", "needs_clarification"}
        and not positive_passengers(passengers)
    ):
        return "passengers"

    return None


def _valid_slot_name(name: Any, context: Optional[Dict[str, Any]] = None) -> bool:
    names = set(CORE_SLOTS) | {"stopovers", "passengers", "general_note", "session_city"}
    if not isinstance(name, str):
        return False
    if name in names:
        return True
    if not re.fullmatch(r"stopovers:[0-9]+", name):
        return False
    known = (context or {}).get("booking_slots") or (context or {}).get("existing_slots_summary") or {}
    stops = known.get("stopovers") or []
    return int(name.split(":")[1]) < len(stops)


def _valid_slot_value(name: str, value: Any, metadata: Dict[str, Any]) -> bool:
    operation = metadata.get("operation", "replace")
    if operation not in {"replace", "augment", "clear", "append"}:
        return False
    if operation == "append" and name != "stopovers":
        return False
    if operation == "clear":
        return value is None or isinstance(value, (str, int, list))
    if name == "passengers":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "stopovers":
        if not isinstance(value, list) or len(value) > 8:
            return False
        for item in value:
            if isinstance(item, str) and item.strip():
                continue
            if not isinstance(item, dict) or not isinstance(item.get("value"), str) or not item["value"].strip():
                return False
            if item.get("metadata") is not None and not isinstance(item["metadata"], dict):
                return False
        return True
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 2000


def validate_extractor_output(
    raw_output: Any, context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Validate and sanitize NLU output from LLM.
    
    Merges duplicate updates to the same slot preserving the last correction.
    """
    fallback_output = {
        "intents": ["unclear"],
        "primary_intent": "unclear",
        "extracted_slots": [],
        "addressed_slots": [],
        "clarification_response": None,
        "confidence": 0.0,
    }

    if not isinstance(raw_output, dict):
        return fallback_output

    try:
        raw_intents = raw_output.get("intents")
        if not isinstance(raw_intents, list) or not raw_intents:
            intents = ["unclear"]
        else:
            intents = [str(i) for i in raw_intents if str(i) in VALID_INTENTS]
            if not intents:
                intents = ["unclear"]

        # Sort intents consistently and pick primary_intent
        primary_intent = raw_output.get("primary_intent")
        if primary_intent not in intents:
            for prio in INTENT_PRIORITY_ORDER:
                if prio in intents:
                    primary_intent = prio
                    break
            else:
                primary_intent = intents[0]

        # Extract and sanitize slot updates
        raw_slots = raw_output.get("extracted_slots", [])
        if not isinstance(raw_slots, list):
            raw_slots = []

        # Group and merge updates for the same slot (keeping last updated value)
        merged_slots: Dict[str, ExtractedSlotUpdate] = {}
        invalid_update = not isinstance(raw_output.get("extracted_slots"), list)
        for item in raw_slots:
            if not isinstance(item, dict):
                invalid_update = True
                continue
            name = item.get("slot_name")
            if not _valid_slot_name(name, context):
                invalid_update = True
                continue

            metadata = item.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}

            if not _valid_slot_value(name, item.get("value"), metadata):
                invalid_update = True
                continue
            source = item.get("source_text")
            if source is not None and not isinstance(source, str):
                invalid_update = True
                continue
            metadata = dict(metadata)
            for key in ["raw_full", "driver_note", "sub_poi", "address_city", "component_type", "direction_modifier"]:
                if key in metadata and not isinstance(metadata[key], str):
                    metadata.pop(key)
            if "candidate_selection" in metadata:
                choice = metadata["candidate_selection"]
                if not isinstance(choice, int) or isinstance(choice, bool) or choice < 0:
                    metadata.pop("candidate_selection")

            update_obj: ExtractedSlotUpdate = {
                "slot_name": name,
                "value": item.get("value"),
                "source_text": str(item.get("source_text") or ""),
                "metadata": metadata,
            }
            merged_slots[name] = update_obj

        if (invalid_update or ("change_info" in intents and not merged_slots)) and "confirm" in intents:
            intents = [i for i in intents if i != "confirm"]
            if "unclear" not in intents:
                intents.append("unclear")
            primary_intent = next((i for i in INTENT_PRIORITY_ORDER if i in intents), "unclear")
        extracted_slots = list(merged_slots.values())
        if not extracted_slots and set(intents) <= {"provide_info", "unclear"}:
            intents = ["unclear"]
            primary_intent = "unclear"

        raw_addressed = raw_output.get("addressed_slots", [])
        addressed_slots = (
            [s for s in raw_addressed if _valid_slot_name(s, context)]
            if isinstance(raw_addressed, list)
            else []
        )

        clarification_response = raw_output.get("clarification_response")
        if clarification_response not in {"detail", "unknown", "reject_candidates"}:
            clarification_response = None

        confidence = raw_output.get("confidence", 1.0)
        try:
            confidence = float(confidence)
            if not (0.0 <= confidence <= 1.0):
                confidence = 0.0
        except (ValueError, TypeError):
            confidence = 0.0

        return {
            "intents": intents,
            "primary_intent": primary_intent,
            "extracted_slots": extracted_slots,
            "addressed_slots": addressed_slots,
            "clarification_response": clarification_response,
            "confidence": confidence,
        }
    except Exception:
        return fallback_output


def validate_spoken_text(text: str) -> None:
    """Ensure text is clean conversational Vietnamese for TTS (no markdown, json, ansi, enums)."""
    if not isinstance(text, str):
        raise ValueError("Spoken text must be a string")

    # Check for markdown code blocks or headings
    if "```" in text or re.search(r"^\s*#{1,6}\s", text, re.MULTILINE):
        raise ValueError("Spoken text contains markdown formatting")

    # Check for JSON structures
    if "{" in text and "}" in text and ":" in text:
        raise ValueError("Spoken text contains JSON structure")

    # Check for raw technical enum strings
    for enum_word in ["xe_may", "oto_4_cho", "oto_7_cho", "ready_to_book", "cancel_pending"]:
        if enum_word in text:
            raise ValueError(f"Spoken text contains raw enum identifier: {enum_word}")

    # Check for ANSI escape sequences
    if re.search(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", text):
        raise ValueError("Spoken text contains ANSI escape codes")
