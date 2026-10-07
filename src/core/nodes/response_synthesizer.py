"""Node 7: response_synthesizer_node. Renders TTS speech text and updates dialog messages."""

from typing import Any, Dict, List, cast
from src.core.state import BotAction, ParrotGoGraphState
from src.core.time_utils import format_pickup_time_display
from src.core.validators import validate_spoken_text
from src.services.templates import join_speech, render_template_by_action


def last_bot_text(messages: List[Dict[str, str]]) -> str:
    """Find the most recent bot message."""
    for m in reversed(messages):
        if m.get("role") == "bot":
            return m.get("content", "")
    return ""


def response_synthesizer_node(state: ParrotGoGraphState) -> Dict[str, Any]:
    """Render clean speech text, validate TTS suitability, and update message history."""
    qa = state.get("qa_response") or {}
    raw_action = state.get("last_bot_action") or {}
    action: BotAction = cast(BotAction, raw_action)
    prev_text = last_bot_text(state.get("messages", []))

    time_display = format_pickup_time_display(
        state["booking_slots"]["pickup_time"], state.get("timezone", "Asia/Ho_Chi_Minh")
    )
    action_text = render_template_by_action(
        action=action,
        slots=state["booking_slots"],
        customer_name=state.get("customer_name"),
        pickup_time_display=time_display,
        previous_bot_text=prev_text,
    )

    qa_text = qa.get("answer_text", "")
    if (
        action.get("action_type") == "confirm_booking"
        and (action.get("metadata") or {}).get("repeat_previous")
        and (qa.get("metadata") or {}).get("type") == "trip_summary"
    ):
        # The confirmation action already reads the current trip and its question.
        qa_text = ""
    text = join_speech(qa_text, action_text)
    validate_spoken_text(text)

    messages = list(state.get("messages", [])) + [
        {"role": "user", "content": state["user_current_input"]},
        {"role": "bot", "content": text},
    ]

    is_terminal = state.get("booking_status") in {
        "booked",
        "canceled",
        "operator_required",
    }

    return {
        "final_response_text": text,
        "messages": messages,
        "is_terminal": is_terminal,
    }
