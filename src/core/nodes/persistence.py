"""Commit a turn before reporting a successful or terminal outcome."""

import copy
import sqlite3
from typing import Any, Dict
from src.core.state import ParrotGoGraphState
from src.core.validators import CORE_SLOTS
from src.db.sqlite_manager import PersistenceError, get_default_db_manager


def persistence_node(state: ParrotGoGraphState, db_manager=None) -> Dict[str, Any]:
    manager = db_manager or get_default_db_manager()
    candidate = copy.deepcopy(state)
    if candidate.get("booking_status") == "booking_pending":
        candidate["booking_status"] = "booked"
        candidate["is_terminal"] = True
    try:
        result = manager.persist_turn(candidate)
    except (PersistenceError, sqlite3.Error):
        status = state.get("booking_status", "collecting")
        if status in {"booking_pending", "booked"}:
            status = "confirming"
            action = {
                "action_type": "confirm_booking", "target_slots": list(CORE_SLOTS),
                "metadata": {"booking_revision": state.get("booking_revision", 0)},
            }
            text = "Dạ hiện tại em chưa lưu được yêu cầu. Mình xác nhận lại để em thử lưu một lần nữa ạ."
        elif status == "canceled":
            status = "cancel_pending"
            action = {"action_type": "confirm_cancel", "target_slots": [], "metadata": {}}
            text = "Dạ em chưa lưu được việc hủy yêu cầu. Mình xác nhận lại giúp em ạ."
        else:
            status = "collecting" if status == "operator_required" else status
            action = state.get("last_bot_action")
            text = "Dạ em chưa lưu được thông tin, thông tin vẫn được giữ trong phiên này. Mình thử lại giúp em ạ."
        messages = copy.deepcopy(state.get("messages", []))
        if messages and messages[-1].get("role") == "bot":
            messages[-1]["content"] = text
        return {
            "booking_status": status, "is_terminal": False,
            "last_bot_action": action, "final_response_text": text,
            "messages": messages, "persistence_error": "commit_failed",
        }
    return {
        "booking_id": result.get("booking_id"),
        "booking_status": candidate["booking_status"],
        "is_terminal": candidate.get("is_terminal", False),
        "persistence_error": None,
    }
