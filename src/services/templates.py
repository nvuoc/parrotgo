"""Spoken text templates and response rendering for TTS."""

import re
from typing import Any, Dict, Optional
from src.core.state import BotAction, BookingSlots
from src.db.in_memory_cache import normalize_city_key, normalize_geo_key, strip_city_suffix
from src.services.vietmap_client import GENERIC_BRANDS

VEHICLE_DISPLAY = {
    "xe_may": "xe máy",
    "oto_4_cho": "ô tô bốn chỗ",
    "oto_7_cho": "ô tô bảy chỗ",
}

ROLE_DISPLAY = {
    "pickup": "đón",
    "destination": "đến",
    "stopover": "dừng chân",
}

RESPONSE_TEMPLATES = {
    "greeting": "Dạ em chào anh/chị. Mình muốn xe đón ở đâu ạ?",
    "ask_pickup": "Dạ mình cho em xin địa chỉ hoặc mốc cụ thể nơi đón ạ?",
    "ask_destination": "Dạ mình muốn đi đến đâu ạ?",
    "ask_vehicle_type": "Dạ mình muốn đi loại xe nào ạ?",
    "ask_pickup_time": "Dạ mình muốn đón vào ngày nào, lúc mấy giờ ạ?",
    "ask_passengers": "Dạ mình đi bao nhiêu người ạ?",
    "clarify_city": "Dạ địa điểm này thuộc tỉnh hoặc thành phố nào ạ?",
    "clarify_ab": "Dạ mình muốn {role_text} tại {area_a} hay {area_b} ạ?",
    "clarify_narrow": "Dạ mình cho em thêm số nhà hoặc mốc dễ tìm gần đó ạ?",
    "clarify_destination": "Dạ mình cho em một mốc dễ tìm gần điểm đến này ạ?",
    "clarify_stopover": "Dạ điểm dừng thứ {order} của mình ở địa chỉ hoặc mốc nào ạ?",
    "clarify_mega_gate": "Dạ ở {poi_name}, mình đang gần cổng, tòa nhà hoặc mốc nào dễ thấy ạ?",
    "confirm_proposed_address": "Dạ có phải mình muốn {role_text} tại {address} không ạ?",
    "ask_modify_slot": "Dạ mình muốn điều chỉnh thông tin nào của chuyến đi ạ?",
    "confirm_booking": (
        "Dạ em ghi nhận {vehicle_type} đón tại {pickup_address}, "
        "đi đến {destination_address}, {pickup_time_display}.{optional_summary} "
        "Thông tin này đã đúng chưa ạ?"
    ),
    "inform_success_immediate": "Dạ em đã lưu yêu cầu đặt xe của mình thành công ạ.",
    "inform_success_scheduled": "Dạ em đã lưu yêu cầu đặt xe theo giờ hẹn của mình thành công ạ.",
    "confirm_cancel": "Dạ mình có chắc muốn hủy yêu cầu đặt xe này không ạ?",
    "inform_canceled": "Dạ em đã hủy yêu cầu đặt xe trong phiên này ạ.",
    "human_handoff": "Dạ trường hợp này cần nhân viên hỗ trợ để xử lý chính xác ạ.",
    "unclear_prompt": "Dạ em chưa hiểu rõ, mình nói lại giúp em ạ?",
    "nlu_retry": "Dạ em chưa xử lý được câu vừa rồi. Mình thử nói lại giúp em ạ?",
    "nlu_unavailable": "Dạ hiện tại em chưa xử lý được yêu cầu. Mình thử lại sau ít phút giúp em ạ.",
    "map_retry": "Dạ em chưa tra được bản đồ lúc này. Mình thử lại địa chỉ giúp em ạ?",
    "capacity_conflict": "Dạ số khách vượt số chỗ của loại xe đã chọn. Mình chọn xe khác hoặc điều chỉnh số khách giúp em ạ?",
    "persistence_error": "Dạ hiện tại em chưa thể xác nhận việc lưu yêu cầu, mình thử lại sau giúp em ạ.",
}


def join_speech(qa_text: str, action_text: str) -> str:
    """Combine QA answer text and action text cleanly."""
    qa = (qa_text or "").strip()
    act = (action_text or "").strip()
    if qa and act:
        if not qa.endswith((".", "!", "?")):
            qa += "."
        return f"{qa} {act}"
    return qa or act or "Dạ em xin nghe ạ."


def _address_for_target(slots: BookingSlots, target: str) -> Dict[str, Any]:
    if target.startswith("stopovers:"):
        try:
            return slots.get("stopovers", [])[int(target.split(":", 1)[1])].get("address", {})
        except (IndexError, ValueError, TypeError):
            return {}
    return slots.get(target, {}) if target in {"pickup", "destination"} else {}


def _short_place_name(value: Any) -> str:
    """Read the place/street name, leaving the administrative hierarchy in state."""
    if not isinstance(value, str):
        return ""
    head = value.split(",", 1)[0].strip()
    head = re.split(r"\s+(?:phường|xã|quận|huyện|tỉnh|thành phố)\s+", head, maxsplit=1, flags=re.IGNORECASE)[0]
    return head.strip(" ,;")


def _short_address_label(slot: Dict[str, Any]) -> str:
    return _short_place_name(slot.get("formatted") or slot.get("raw")) or "địa điểm này"


def _candidate_label(candidate: Dict[str, Any]) -> str:
    return _short_place_name(candidate.get("name") or candidate.get("formatted") or candidate.get("formatted_address") or candidate.get("address"))


def _candidate_component(candidate: Dict[str, Any], field: str) -> str:
    components = candidate.get("components") or {}
    if field == "city":
        return str(candidate.get("city") or components.get("province_city") or "").strip()
    return str(candidate.get(field) or components.get(field) or "").strip()


def _city_label(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"^(?:thành phố|tp\.?|tỉnh)\s+", "", value.strip(), flags=re.IGNORECASE)


def _clarification_city(slot: Dict[str, Any], candidates: list[Dict[str, Any]], meta: Dict[str, Any]) -> str:
    city = _city_label((slot.get("components") or {}).get("province_city") or meta.get("city"))
    if city:
        return city
    cities = [_candidate_component(candidate, "city") for candidate in candidates]
    if cities and all(cities) and len({normalize_city_key(value) for value in cities}) == 1:
        return _city_label(cities[0])
    return ""


def _generic_branch_label(slot: Dict[str, Any], city: str) -> str:
    raw = str(slot.get("raw") or "").strip()
    if strip_city_suffix(raw, city or None) not in GENERIC_BRANDS:
        return ""
    label = _short_place_name(raw)
    if city:
        label = re.sub(r",?\s+(?:(?:thành phố|tp\.?)\s+)?" + re.escape(city) + r"\s*$", "", label, flags=re.IGNORECASE)
    return label or "địa điểm này"


def _open_clarification(slot: Dict[str, Any], target: str, candidates: list[Dict[str, Any]], city: str) -> str:
    """Ask for one useful attribute, even if the map supplied many candidates."""
    if not city:
        return RESPONSE_TEMPLATES["clarify_city"]
    for field, question in [
        ("district", "Dạ địa điểm này ở quận hoặc huyện nào ạ?"),
        ("ward", "Dạ địa điểm này ở phường hoặc xã nào ạ?"),
    ]:
        values = {_candidate_component(candidate, field) for candidate in candidates}
        values.discard("")
        if len(values) > 1:
            return question
    if target == "destination":
        return RESPONSE_TEMPLATES["clarify_destination"]
    if target.startswith("stopovers:"):
        order = int(target.split(":", 1)[1]) + 1
        return f"Dạ mình cho em một mốc dễ tìm tại điểm dừng thứ {order} ạ?"
    return "Dạ gần mình có mốc nào dễ tìm ạ?"


def _render_address_clarification(slot: Dict[str, Any], target: str, kind: str, meta: Dict[str, Any]) -> str:
    candidates = [candidate for candidate in (slot.get("candidates") or []) if isinstance(candidate, dict)]
    city = _clarification_city(slot, candidates, meta)
    if kind == "city":
        return RESPONSE_TEMPLATES["clarify_city"]
    brand = _generic_branch_label(slot, city)
    if brand:
        if not city:
            return RESPONSE_TEMPLATES["clarify_city"]
        role_text = ROLE_DISPLAY.get("stopover" if target.startswith("stopovers:") else target, "đón")
        return f"Dạ mình muốn {role_text} {brand} chi nhánh nào ở {city} ạ?"
    if kind != "ab" or len(candidates) != 2:
        return _open_clarification(slot, target, candidates, city)
    cities = {_candidate_component(candidate, "city") for candidate in candidates}
    cities.discard("")
    if len({normalize_city_key(value) for value in cities}) > 1:
        return RESPONSE_TEMPLATES["clarify_city"]
    # Two homonymous streets are distinguished by one district/ward, not a full chain.
    labels = []
    for field in ("district", "ward"):
        values = [_candidate_component(candidate, field) for candidate in candidates]
        if all(values) and normalize_geo_key(values[0]) != normalize_geo_key(values[1]):
            labels = values
            break
    if not labels:
        values = [_candidate_label(candidate) for candidate in candidates]
        if all(values) and normalize_geo_key(values[0]) != normalize_geo_key(values[1]):
            labels = values
    if not labels:
        return _open_clarification(slot, target, candidates, city)
    role_text = ROLE_DISPLAY.get("stopover" if target.startswith("stopovers:") else target, "đón")
    return RESPONSE_TEMPLATES["clarify_ab"].format(role_text=role_text, area_a=labels[0], area_b=labels[1])


def render_address_speech(addr_slot: Any, role: str = "pickup") -> str:
    """Include actual pickup details/instructions rather than silently losing them."""
    if not isinstance(addr_slot, dict) or not addr_slot:
        return "chưa có địa chỉ"
    raw = addr_slot.get("raw")
    formatted = addr_slot.get("formatted")
    note = addr_slot.get("note")
    base = formatted or raw or "địa chỉ chưa rõ"
    if note and "bản đồ ghim" in note.lower() and raw:
        return f"{raw}, bản đồ ghim tại {formatted or raw}"
    if addr_slot.get("default_point_used") and addr_slot.get("gate_id"):
        base = f"{base}, theo điểm đón mặc định"
    if note and (addr_slot.get("gate_resolved") or addr_slot.get("default_point_used")):
        base = f"{base}, lưu ý: {note}"
    return base


def render_optional_summary(slots: BookingSlots) -> str:
    """Render summary text for stopovers, passengers, and general notes."""
    parts = []
    stopovers = slots.get("stopovers", [])
    if stopovers:
        stop_strs = []
        for s in stopovers:
            addr_str = render_address_speech(s.get("address", {}), "stopover")
            stop_strs.append(f"điểm dừng thứ {s.get('order', 1)} tại {addr_str}")
        parts.append(" có " + ", ".join(stop_strs))

    passengers = slots.get("passengers", {})
    if passengers.get("status") in {"extracted", "confirmed"} and passengers.get("value"):
        parts.append(f" dành cho {passengers['value']} hành khách")

    note = slots.get("general_note")
    if note:
        parts.append(f", ghi chú: {note}")

    if parts:
        return "," + "".join(parts)
    return ""


def render_template_by_action(
    action: BotAction,
    slots: BookingSlots,
    customer_name: Optional[str] = None,
    pickup_time_display: Optional[str] = None,
    previous_bot_text: Optional[str] = None,
) -> str:
    """Render spoken text corresponding to chosen BotAction."""
    act_type = action.get("action_type")
    meta = action.get("metadata") or {}
    targets = action.get("target_slots") or []

    if meta.get("suppress_action_text") and not meta.get("repeat_previous"):
        return ""
    if meta.get("repeat_previous") and previous_bot_text and not meta.get("suppress_action_text"):
        return previous_bot_text

    if act_type == "answer_question":
        return ""

    if act_type == "inform_canceled":
        return RESPONSE_TEMPLATES["inform_canceled"]

    if act_type == "human_handoff":
        return RESPONSE_TEMPLATES["human_handoff"]

    if act_type == "confirm_cancel":
        return RESPONSE_TEMPLATES["confirm_cancel"]

    if act_type == "general_reply":
        subtype = meta.get("type")
        if subtype == "greeting":
            return RESPONSE_TEMPLATES["greeting"]
        if subtype in {"ask_modify_slot", "nlu_retry", "nlu_unavailable", "map_retry", "capacity_conflict"}:
            return RESPONSE_TEMPLATES[subtype]
        return RESPONSE_TEMPLATES["unclear_prompt"]

    if act_type == "inform_success":
        p_val = slots.get("pickup_time", {}).get("value")
        if p_val == "now":
            return RESPONSE_TEMPLATES["inform_success_immediate"]
        return RESPONSE_TEMPLATES["inform_success_scheduled"]

    if act_type == "ask_slot":
        target = targets[0] if targets else "pickup"
        subtype = meta.get("type")
        if target == "pickup":
            dest_slot = slots.get("destination", {})
            dest_name = _short_address_label(dest_slot) if dest_slot.get("formatted") or dest_slot.get("raw") else None
            if subtype == "explain_destination_ask_pickup" and dest_name:
                return f"Dạ điểm đến {dest_name} em đã ghi nhận rồi ạ. Mình đang ở địa chỉ nào để xe đến đón ạ?"
            if dest_name:
                return f"Dạ em đã ghi nhận điểm đến là {dest_name} rồi ạ. Cho em xin địa chỉ xe đón mình ở đâu ạ?"
            return RESPONSE_TEMPLATES["ask_pickup"]
        elif target == "destination":
            pickup_slot = slots.get("pickup", {})
            pickup_name = _short_address_label(pickup_slot) if pickup_slot.get("formatted") or pickup_slot.get("raw") else None
            if subtype == "explain_pickup_ask_destination" and pickup_name:
                return f"Dạ điểm đón tại {pickup_name} em đã ghi nhận rồi ạ. Mình muốn xe chở đến đâu ạ?"
            if pickup_name:
                return f"Dạ em đã ghi nhận điểm đón tại {pickup_name} rồi ạ. Mình muốn xe chở đến đâu ạ?"
            return RESPONSE_TEMPLATES["ask_destination"]
        elif target == "vehicle_type":
            return RESPONSE_TEMPLATES["ask_vehicle_type"]
        elif target == "pickup_time":
            return RESPONSE_TEMPLATES["ask_pickup_time"]
        elif target == "passengers":
            return RESPONSE_TEMPLATES["ask_passengers"]
        elif target.startswith("stopovers:"):
            order = int(target.split(":")[1]) + 1
            return RESPONSE_TEMPLATES["clarify_stopover"].format(order=order)
        return RESPONSE_TEMPLATES["ask_pickup"]

    if act_type == "clarify_address":
        target = targets[0] if targets else "pickup"
        kind = meta.get("type") or "narrow"
        slot = _address_for_target(slots, target)
        if kind == "mega_poi_gate":
            poi_name = _short_address_label(slot)
            return RESPONSE_TEMPLATES["clarify_mega_gate"].format(poi_name=poi_name)
        return _render_address_clarification(slot, target, kind, meta)

    if act_type == "confirm_slots":
        target = targets[0] if targets else "pickup"
        role_text = "đón" if target == "pickup" else ("đến" if target == "destination" else "dừng chân")
        slot = _address_for_target(slots, target)
        addr_text = _short_address_label(slot)
        return RESPONSE_TEMPLATES["confirm_proposed_address"].format(role_text=role_text, address=addr_text)

    if act_type == "confirm_booking":
        v_code = slots.get("vehicle_type", {}).get("value")
        v_disp = VEHICLE_DISPLAY.get(v_code, "xe")
        p_addr = render_address_speech(slots.get("pickup", {}), "pickup")
        d_addr = render_address_speech(slots.get("destination", {}), "destination")
        time_disp = pickup_time_display or "đón ngay"
        opt_summary = render_optional_summary(slots)
        return RESPONSE_TEMPLATES["confirm_booking"].format(
            vehicle_type=v_disp,
            pickup_address=p_addr,
            destination_address=d_addr,
            pickup_time_display=time_disp,
            optional_summary=opt_summary,
        )

    return RESPONSE_TEMPLATES["greeting"]
