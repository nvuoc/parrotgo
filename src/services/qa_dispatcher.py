"""QA Dispatcher: handles state inspection, dynamic route/weather tools, and static FAQ."""

import math
import re
from typing import Optional

from src.core.state import BookingSlots, QAResponse
from src.core.time_utils import format_pickup_time_display, valid_coords
from src.db.chroma_client import chroma_faq_client
from src.services.templates import VEHICLE_DISPLAY, render_address_speech, render_optional_summary
from src.services.llm_extractor import is_booking_guidance_question


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in kilometers."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def inspect_session_state(query: str, slots: BookingSlots, timezone: str = "Asia/Ho_Chi_Minh") -> Optional[QAResponse]:
    """Inspect and answer queries regarding current conversation booking state."""
    q_low = query.lower()
    if is_booking_guidance_question(q_low):
        return None

    # Destination query
    if any(k in q_low for k in ["đi đâu", "đến đâu", "điểm đến", "chở đến đâu"]):
        dest = slots.get("destination", {})
        status = dest.get("status", "empty")
        addr_str = render_address_speech(dest, "destination")
        if status == "empty":
            ans = "Dạ mình chưa cung cấp điểm đến ạ."
        elif status == "needs_clarification":
            ans = f"Dạ điểm đến em đang ghi nhận là {addr_str} nhưng cần làm rõ thêm ạ."
        else:
            ans = f"Dạ điểm đến mình đã chọn là {addr_str} ạ."
        return {
            "category": "session_state",
            "success": True,
            "answer_text": ans,
            "source": "session_state",
            "metadata": {"slot": "destination"},
        }

    # Pickup query
    if any(k in q_low for k in ["đón ở đâu", "điểm đón", "đón tại đâu"]):
        pickup = slots.get("pickup", {})
        status = pickup.get("status", "empty")
        addr_str = render_address_speech(pickup, "pickup")
        if status == "empty":
            ans = "Dạ mình chưa cung cấp điểm đón ạ."
        elif status == "needs_clarification":
            ans = f"Dạ điểm đón em đang ghi nhận là {addr_str} nhưng cần làm rõ thêm ạ."
        else:
            ans = f"Dạ điểm đón mình đã chọn là {addr_str} ạ."
        return {
            "category": "session_state",
            "success": True,
            "answer_text": ans,
            "source": "session_state",
            "metadata": {"slot": "pickup"},
        }

    # Vehicle query
    if "xe gì" in q_low or ("loại xe" in q_low and not any(k in q_low for k in ["nào", "có những", "có loại", "những loại"])):
        v_slot = slots.get("vehicle_type", {})
        v_code = v_slot.get("value")
        if v_code:
            ans = f"Dạ mình đang chọn {VEHICLE_DISPLAY.get(v_code, 'xe')} ạ."
        else:
            ans = "Dạ mình chưa chọn loại xe ạ."
        return {
            "category": "session_state",
            "success": True,
            "answer_text": ans,
            "source": "session_state",
            "metadata": {"slot": "vehicle_type"},
        }

    # Repeat entire trip
    if any(k in q_low for k in ["đọc lại", "nhắc lại", "thông tin chuyến"]):
        p_addr = render_address_speech(slots.get("pickup", {}), "pickup")
        d_addr = render_address_speech(slots.get("destination", {}), "destination")
        v_code = slots.get("vehicle_type", {}).get("value")
        v_disp = VEHICLE_DISPLAY.get(v_code, "xe chưa chọn")
        t_disp = format_pickup_time_display(slots.get("pickup_time", {}), timezone)
        ans = (
            f"Dạ chuyến đi của mình hiện gồm: đón tại {p_addr}, "
            f"đến {d_addr}, {v_disp}, {t_disp}{render_optional_summary(slots)} ạ."
        )
        return {
            "category": "session_state",
            "success": True,
            "answer_text": ans,
            "source": "session_state",
            "metadata": {"type": "trip_summary"},
        }

    if any(k in q_low for k in ["đón lúc mấy", "giờ đón", "thời gian đón"]):
        ans = "Dạ thời gian mình đã chọn là " + format_pickup_time_display(slots.get("pickup_time", {}), timezone) + " ạ."
        return {"category": "session_state", "success": True, "answer_text": ans, "source": "session_state", "metadata": {"slot": "pickup_time"}}
    if "mấy người" in q_low or "bao nhiêu người" in q_low:
        count = slots.get("passengers", {}).get("value")
        ans = f"Dạ em đã ghi nhận {count} hành khách ạ." if count else "Dạ mình chưa cung cấp số hành khách ạ."
        return {"category": "session_state", "success": True, "answer_text": ans, "source": "session_state", "metadata": {"slot": "passengers"}}
    return None


def execute_route_qa_tool(query: str, slots: BookingSlots) -> Optional[QAResponse]:
    """Estimate distance and duration between pickup and destination."""
    q_low = query.lower()

    # Dispatch/pickup ETA is different from the duration of the passenger trip.
    if re.search(r"tài xế.*(?:tới|đến|đón)|(?:bao giờ|khi nào|bao lâu).*(?:xe.*(?:tới|đến đón)|tài xế)|xe.*(?:tới đón|đến đón)", q_low):
        return {"category": "dynamic_tool", "success": False, "answer_text": "Dạ em chưa có thông tin tài xế được phân công nên chưa xác định được lúc xe đến đón ạ.", "source": "pickup_eta_unavailable", "metadata": {"reason": "dispatch_not_integrated"}}

    # Route estimation keywords
    if any(k in q_low for k in ["bao xa", "bao lâu", "mấy cây", "mấy km", "mấy phút", "khoảng cách"]):
        p_coords = slots.get("pickup", {}).get("coords")
        d_coords = slots.get("destination", {}).get("coords")

        if not valid_coords(p_coords) or not valid_coords(d_coords) or any(slots.get(name, {}).get("requires_confirmation") or slots.get(name, {}).get("status") == "needs_clarification" for name in ["pickup", "destination"]):
            return {
                "category": "dynamic_tool",
                "success": False,
                "answer_text": "Dạ hiện tại em chưa ước tính được quãng đường và thời gian cho tuyến này ạ.",
                "source": "route_tool",
                "metadata": {"reason": "missing_coords"},
            }

        # Calculate great-circle distance with road factor 1.3
        straight_km = haversine_distance_km(
            p_coords["lat"], p_coords["lng"], d_coords["lat"], d_coords["lng"]
        )
        est_km = max(straight_km * 1.3, 1.0)
        # Average speed 25 km/h in city
        est_mins = max(est_km / 25.0 * 60.0, 5.0)

        min_km = math.floor(est_km * 0.95)
        max_km = math.ceil(est_km * 1.15)
        min_mins = math.floor(est_mins)
        max_mins = math.ceil(est_mins * 1.4)

        ans = (
            f"Dạ em ước tính sơ bộ quãng đường khoảng từ {min_km} đến {max_km} cây số, "
            f"thời gian di chuyển dự kiến khoảng {min_mins} đến {max_mins} phút "
            f"tuỳ thuộc vào tình hình giao thông thực tế ạ."
        )
        return {
            "category": "dynamic_tool",
            "success": True,
            "answer_text": ans,
            "source": "route_tool",
            "metadata": {
                "distance_km_range": [min_km, max_km],
                "duration_min_range": [min_mins, max_mins],
            },
        }

    # Weather tool
    if any(k in q_low for k in ["thời tiết", "mưa", "nắng"]):
        return {
            "category": "dynamic_tool",
            "success": False,
            "answer_text": "Dạ hiện tại em chưa có thông tin thời tiết cho khu vực này ạ.",
            "source": "weather_tool",
            "metadata": {"reason": "not_integrated"},
        }

    return None


def dispatch_questions(
    user_text: str,
    slots: BookingSlots,
    session_city: Optional[str] = None,
    timezone: str = "Asia/Ho_Chi_Minh",
) -> QAResponse:
    """Route questions across session state, dynamic tools, and Chroma FAQ."""
    # 1. State inspection
    state_res = inspect_session_state(user_text, slots, timezone)
    if state_res:
        return state_res

    # 2. Dynamic route tools
    route_res = execute_route_qa_tool(user_text, slots)
    if route_res:
        return route_res

    # 3. Static FAQ via Chroma
    vehicle = slots.get("vehicle_type", {}).get("value")
    faq_res = chroma_faq_client.search_faq_policy(user_text, vehicle_type=vehicle)
    return faq_res
