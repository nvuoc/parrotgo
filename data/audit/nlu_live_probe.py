"""Bounded live NLU acceptance probe. Never prints configuration secrets/provider bodies."""
import json
import sys
import time
from copy import deepcopy

from src.config import settings
from src.core.state import get_initial_booking_slots
from src.core.time_utils import normalize_pickup_time
from src.services.llm_extractor import ExtractorServiceError, run_llm_extractor

sys.stdout.reconfigure(encoding="utf-8")
slots = get_initial_booking_slots()
slots["destination"].update(raw="Vincom", formatted="Vincom Bà Triệu, Hà Nội")
base = {"session_city": None, "timezone": "Asia/Ho_Chi_Minh", "turn_received_at": "2026-10-08T10:00:00+07:00", "recent_dialog_turns": [], "booking_slots": slots, "booking_status": "collecting"}
cases = [
    ("đi vincom", None, get_initial_booking_slots()),
    ("ở Hà Nội", {"action_type": "clarify_address", "target_slots": ["destination"], "metadata": {"type": "city"}}, slots),
    ("Nãy tôi đặt đi đâu?", {"action_type": "confirm_booking", "target_slots": ["pickup", "destination", "vehicle_type", "pickup_time"], "metadata": {}}, slots),
    ("mai 9 giờ", {"action_type": "ask_slot", "target_slots": ["pickup_time"], "metadata": {}}, slots),
    ("không cần xe bảy chỗ, bốn chỗ thôi", {"action_type": "ask_slot", "target_slots": ["vehicle_type"], "metadata": {}}, slots),
]
print(json.dumps({"provider": settings.LLM_MODE, "model": settings.GEMINI_MODEL if settings.LLM_MODE == "gemini" else settings.GROQ_MODEL, "timeout_seconds": settings.LLM_TIMEOUT_SECONDS}, ensure_ascii=False), flush=True)
for text, action, current_slots in cases:
    context = deepcopy(base)
    context.update(user_text=text, last_bot_action=action, booking_slots=current_slots)
    started = time.monotonic()
    try:
        result = run_llm_extractor(context)
        for update in result["extracted_slots"]:
            if update["slot_name"] == "pickup_time":
                result["normalized_time"] = normalize_pickup_time(update["value"], update["source_text"], context["turn_received_at"], context["timezone"])
        output = {"text": text, "elapsed_seconds": round(time.monotonic() - started, 2), "result": result}
    except ExtractorServiceError as exc:
        output = {"text": text, "elapsed_seconds": round(time.monotonic() - started, 2), "error": {"provider": exc.provider, "code": exc.code}}
    print(json.dumps(output, ensure_ascii=False), flush=True)
    if "error" in output:
        break
