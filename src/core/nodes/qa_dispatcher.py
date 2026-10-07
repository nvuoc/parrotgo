"""Node 5: qa_dispatcher_node. Answers queries using newly reduced state."""

from typing import Any, Dict
from src.core.state import ParrotGoGraphState
from src.services.qa_dispatcher import dispatch_questions


def qa_dispatcher_node(state: ParrotGoGraphState) -> Dict[str, Any]:
    """Dispatch QA questions based on current user utterance and reduced state."""
    response = dispatch_questions(
        user_text=state["user_current_input"],
        slots=state["booking_slots"],
        session_city=state.get("session_city"),
        timezone=state.get("timezone", "Asia/Ho_Chi_Minh"),
    )
    return {"qa_response": response}
