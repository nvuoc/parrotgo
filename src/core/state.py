"""ParrotGo unified state schema and factories.

Single source of truth for graph state, slots, actions, intents and responses.
Refer to architecture.md and langgraph.md.
"""

from typing import Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict

Intent = Literal[
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
]

SlotStatus = Literal["empty", "extracted", "confirmed", "needs_clarification"]
Precision = Literal["exact", "anchor", "road", "ward", "poi", "unknown"]
BookingStatus = Literal[
    "collecting",
    "ready_to_book",
    "confirming",
    "booking_pending",
    "booked",
    "cancel_pending",
    "canceled",
    "operator_required",
]
ToolStatus = Literal["SUCCESS", "NOT_FOUND", "AMBIGUOUS", "API_ERROR"]


class Coordinates(TypedDict):
    lat: float
    lng: float


class AddressComponents(TypedDict, total=False):
    detail: Optional[str]
    street: Optional[str]
    ward: Optional[str]
    district: Optional[str]
    province_city: Optional[str]


class AddressSlot(TypedDict):
    raw: Optional[str]  # Original speech/detail from user
    formatted: Optional[str]  # Standardized address/name from geocoding
    coords: Optional[Coordinates]
    components: AddressComponents
    note: Optional[str]
    place_id: Optional[str]  # Stable place key, not joined by display name
    gate_id: Optional[str]
    location_precision: Precision
    is_mega_poi: bool
    default_point_used: bool
    gate_resolved: bool
    requires_confirmation: bool  # Suggestion pending user confirmation
    clarification_kind: Optional[str]  # city, ab, narrow, landmark, mega_poi_gate
    candidates: List[Dict[str, Any]]  # Kept across turns; speech max 2 options
    status: SlotStatus


class ValueSlot(TypedDict):
    value: Any
    status: SlotStatus


class PickupTimeSlot(TypedDict):
    value: Optional[str]  # "now" or ISO with offset
    raw: Optional[str]  # Original user appointment string
    anchored_at: Optional[str]  # turn_received_at when time was interpreted
    status: SlotStatus


class StopoverSlot(TypedDict):
    address: AddressSlot
    order: int  # Sequential starting at 1


class BookingSlots(TypedDict):
    pickup: AddressSlot
    destination: AddressSlot
    pickup_time: PickupTimeSlot
    vehicle_type: ValueSlot
    stopovers: List[StopoverSlot]
    passengers: ValueSlot
    general_note: Optional[str]
    distance_km: Optional[float]
    duration_minutes: Optional[float]


class ExtractedSlotUpdate(TypedDict):
    slot_name: str
    value: Any
    source_text: str
    metadata: Dict[str, Any]


class BotAction(TypedDict):
    action_type: Literal[
        "ask_slot",
        "confirm_slots",
        "confirm_booking",
        "clarify_address",
        "answer_question",
        "inform_success",
        "general_reply",
        "confirm_cancel",
        "inform_canceled",
        "human_handoff",
    ]
    target_slots: List[str]  # pickup, destination, stopovers:0, etc.
    metadata: Dict[str, Any]  # confirm_booking holds booking_revision


class QAResponse(TypedDict):
    category: Literal["static_faq", "dynamic_tool", "session_state"]
    success: bool
    answer_text: str
    source: str
    metadata: Dict[str, Any]


class ParrotGoGraphState(TypedDict):
    session_id: str
    customer_phone: str
    customer_name: str
    session_city: Optional[str]  # None = unknown; never forced to Hà Nội
    timezone: str  # MVP: Asia/Ho_Chi_Minh
    turn_received_at: str  # ISO with offset, recorded once per turn by adapter
    crm_profile: Optional[Dict[str, Any]]
    messages: List[Dict[str, str]]
    user_current_input: str
    intents: List[Intent]
    primary_intent: Optional[Intent]
    turn_extracted_slots: List[ExtractedSlotUpdate]
    turn_addressed_slots: List[str]  # Which slots this turn actually answered
    clarification_response: Optional[Literal["detail", "unknown", "reject_candidates"]]
    map_service_result: Optional[Dict[str, Any]]
    qa_response: Optional[QAResponse]
    nlu_error: Optional[Dict[str, str]]
    nlu_retry_count: int
    map_retry_count: int
    persistence_error: Optional[str]
    tool_status: Optional[ToolStatus]
    booking_slots: BookingSlots
    current_focus: Optional[str]
    last_bot_action: Optional[BotAction]
    fallback_count: int  # Consecutive unclear turns without valid entity
    slot_retry_counts: Dict[str, int]  # Only integer counts; no coordination flags
    pending_modify_target: bool
    handoff_reason: Optional[str]
    booking_revision: int
    ready_to_book: bool  # Computed by Reducer, read-only in Policy
    booking_status: BookingStatus
    booking_id: Optional[str]  # Assigned by DAL after commit
    final_response_text: str
    is_terminal: bool
    turn_index: int


BotState = ParrotGoGraphState


# Factory helpers
def empty_address_slot() -> AddressSlot:
    return {
        "raw": None,
        "formatted": None,
        "coords": None,
        "components": {},
        "note": None,
        "place_id": None,
        "gate_id": None,
        "location_precision": "unknown",
        "is_mega_poi": False,
        "default_point_used": False,
        "gate_resolved": False,
        "requires_confirmation": False,
        "clarification_kind": None,
        "candidates": [],
        "status": "empty",
    }


def empty_value_slot() -> ValueSlot:
    return {
        "value": None,
        "status": "empty",
    }


def empty_pickup_time_slot() -> PickupTimeSlot:
    return {
        "value": None,
        "raw": None,
        "anchored_at": None,
        "status": "empty",
    }


def get_initial_booking_slots() -> BookingSlots:
    return {
        "pickup": empty_address_slot(),
        "destination": empty_address_slot(),
        "pickup_time": empty_pickup_time_slot(),
        "vehicle_type": empty_value_slot(),
        "stopovers": [],
        "passengers": empty_value_slot(),
        "general_note": None,
        "distance_km": None,
        "duration_minutes": None,
    }


def create_initial_state(
    session_id: str,
    customer_phone: str,
    customer_name: str,
    turn_received_at: str,
    session_city: Optional[str] = None,
    timezone: str = "Asia/Ho_Chi_Minh",
    crm_profile: Optional[Dict[str, Any]] = None,
) -> ParrotGoGraphState:
    return {
        "session_id": session_id,
        "customer_phone": customer_phone,
        "customer_name": customer_name,
        "session_city": session_city,
        "timezone": timezone,
        "turn_received_at": turn_received_at,
        "crm_profile": crm_profile,
        "messages": [],
        "user_current_input": "",
        "intents": [],
        "primary_intent": None,
        "turn_extracted_slots": [],
        "turn_addressed_slots": [],
        "clarification_response": None,
        "map_service_result": None,
        "qa_response": None,
        "nlu_error": None,
        "nlu_retry_count": 0,
        "map_retry_count": 0,
        "persistence_error": None,
        "tool_status": None,
        "booking_slots": get_initial_booking_slots(),
        "current_focus": None,
        "last_bot_action": None,
        "fallback_count": 0,
        "slot_retry_counts": {},
        "pending_modify_target": False,
        "handoff_reason": None,
        "booking_revision": 0,
        "ready_to_book": False,
        "booking_status": "collecting",
        "booking_id": None,
        "final_response_text": "",
        "is_terminal": False,
        "turn_index": 0,
    }
