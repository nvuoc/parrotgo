# ĐỒ THỊ LANGGRAPH CHO MVP CLI

Nguồn schema duy nhất: [architecture.md](./architecture.md). Quy tắc hội thoại: [planner.md](./planner.md). Map/QA/DAL tương ứng: [map.md](./map.md), [ask.md](./ask.md), [database.md](./database.md).

## 1. Topology: 8 node, 3 conditional edge

~~~mermaid
flowchart TD
    START --> Init[1. session_init_node]
    Init --> Ext[2. extractor_node]
    Ext --> MapCheck{route_after_extractor}
    MapCheck -- địa chỉ / điểm dừng / city --> Map[3. map_service_node]
    MapCheck -- không cần map --> Reduce[4. state_reducer_node]
    Map --> Reduce
    Reduce --> QACheck{route_after_reducer}
    QACheck -- ask_question --> QA[5. qa_dispatcher_node]
    QACheck -- khác --> Policy[6. action_policy_node]
    QA --> Policy
    Policy --> Synth[7. response_synthesizer_node]
    Synth --> Persist[8. persistence_node]
    Persist --> Outcome{route_turn_outcome}
    Outcome -- tiếp tục --> EndTurn[END lượt]
    Outcome -- terminal --> EndSession[END phiên]
~~~

Mỗi invoke xử lý đúng một lượt, không có vòng tự hỏi lại trong graph. Cả hai nhánh cuối đi tới LangGraph END; CLI quyết định đọc lượt tiếp hay đóng phiên.

Các khối Python dưới đây là pseudocode có thể kiểm thử với adapter giả, chưa phải mã nguồn ứng dụng. Khi triển khai import schema từ `src/core/state.py`; không định nghĩa lại TypedDict trong từng node.

## 2. Helper thuần dùng chung

Múi giờ MVP là `Asia/Ho_Chi_Minh`. Python trên Windows cần `tzdata` để ZoneInfo hoạt động. Validator thời gian chạy trước khi ghi slot; không giao LLM quyết định tính hợp lệ.

~~~python
import copy
import math
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CORE = ["pickup", "destination", "vehicle_type", "pickup_time"]
VALID_STATUS = {"extracted", "confirmed"}
VEHICLES = {"xe_may", "oto_4_cho", "oto_7_cho"}
STATUS_SEVERITY = {"SUCCESS": 1, "AMBIGUOUS": 2, "NOT_FOUND": 3, "API_ERROR": 4}

def parse_aware(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Timestamp phải có múi giờ")
    return dt

def valid_coords(coords):
    if not isinstance(coords, dict):
        return False
    lat, lng = coords.get("lat"), coords.get("lng")
    return (
        isinstance(lat, (float, int)) and not isinstance(lat, bool)
        and isinstance(lng, (float, int)) and not isinstance(lng, bool)
        and math.isfinite(lat) and math.isfinite(lng)
        and -90 <= lat <= 90 and -180 <= lng <= 180
    )

def normalize_pickup_time(value, source_text, received_at, timezone):
    """HH:MM không tự sang ngày mai; thời gian tương đối neo đúng lượt nhận."""
    raw = source_text or (str(value) if value is not None else "")
    result = {"value": None, "raw": raw, "anchored_at": received_at,
              "status": "needs_clarification"}
    ref = parse_aware(received_at).astimezone(ZoneInfo(timezone))
    if value == "now":
        return {**result, "value": "now", "status": "extracted"}
    try:
        text = str(value).strip()
        relative = re.fullmatch(r"\+([1-9]\d*)(m|h)", text)
        clock = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
        if relative:
            amount = int(relative.group(1))
            dt = ref + (timedelta(minutes=amount) if relative.group(2) == "m"
                        else timedelta(hours=amount))
        elif clock:
            dt = ref.replace(hour=int(clock.group(1)), minute=int(clock.group(2)),
                             second=0, microsecond=0)
        else:
            dt = parse_aware(text).astimezone(ZoneInfo(timezone))
        if dt <= ref:
            return result
        return {**result, "value": dt.isoformat(), "status": "extracted"}
    except (TypeError, ValueError, OverflowError):
        return result

def valid_time(slot, received_at):
    if slot.get("status") not in VALID_STATUS:
        return False
    if slot.get("value") == "now":
        return True
    try:
        return parse_aware(slot["value"]) > parse_aware(received_at)
    except (TypeError, ValueError, KeyError):
        return False

def relative_destination_known(slot):
    """Không chấp nhận raw mơ hồ: dữ liệu phải do Map xác định tên và tỉnh/thành."""
    return (
        bool((slot.get("formatted") or "").strip())
        and bool((slot.get("components") or {}).get("province_city"))
        and slot.get("location_precision") in {"exact", "anchor", "road", "ward", "poi"}
    )

def address_ready(slot, role):
    if slot.get("status") not in VALID_STATUS or slot.get("requires_confirmation"):
        return False
    if role == "pickup":
        if not valid_coords(slot.get("coords")):
            return False
        if slot.get("location_precision") not in {"exact", "anchor"}:
            return False
    elif not relative_destination_known(slot):
        return False
    if role == "stopover" and not valid_coords(slot.get("coords")):
        return False
    if slot.get("is_mega_poi") and role in {"pickup", "stopover"}:
        if not slot.get("gate_resolved"):
            return False
    if slot.get("default_point_used"):
        if not (slot.get("gate_id") and valid_coords(slot.get("coords")) and slot.get("note")):
            return False
    return True

def get_target(slots, target):
    if target.startswith("stopovers:"):
        return slots["stopovers"][int(target.split(":")[1])]["address"]
    return slots[target]

def set_target(slots, target, value):
    if target.startswith("stopovers:"):
        slots["stopovers"][int(target.split(":")[1])]["address"] = value
    else:
        slots[target] = value

def address_targets(slots):
    return ["pickup", "destination"] + [
        f"stopovers:{i}" for i in range(len(slots["stopovers"]))
    ]

def target_role(target):
    return "stopover" if target.startswith("stopovers:") else target

def positive_passengers(slot):
    val = slot.get("value")
    return isinstance(val, int) and not isinstance(val, bool) and val > 0

def check_is_ready_to_book(slots, received_at):
    return (
        address_ready(slots["pickup"], "pickup")
        and address_ready(slots["destination"], "destination")
        and slots["vehicle_type"]["status"] in VALID_STATUS
        and slots["vehicle_type"]["value"] in VEHICLES
        and valid_time(slots["pickup_time"], received_at)
        and all(address_ready(s["address"], "stopover") for s in slots["stopovers"])
        and (slots["passengers"]["status"] == "empty"
             or (positive_passengers(slots["passengers"])
                 and slots["passengers"]["status"] in VALID_STATUS))
    )
~~~

`get_initial_booking_slots()` và `empty_address_slot()` trả schema mặc định ở architecture. Helper target phải được validator bảo vệ chỉ số stopover hợp lệ trước khi gọi.

## 3. Node 1 — reset lượt, giữ state phiên

Adapter đã gọi `db_start_session` trước lượt đầu; node này không tạo lại phiên hay mặc định lại city. `turn_received_at` do adapter cung cấp.

~~~python
def session_init_node(state):
    if state.get("is_terminal") or state.get("booking_status") in {
        "booked", "canceled", "operator_required"
    }:
        raise ValueError("Phiên đã kết thúc; cần session_id mới")
    parse_aware(state["turn_received_at"])
    return {
        "booking_slots": state.get("booking_slots") or get_initial_booking_slots(),
        "crm_profile": state.get("crm_profile") or
                       db_get_customer_crm_profile(state["customer_phone"]),
        "session_city": state.get("session_city"),
        "fallback_count": state.get("fallback_count", 0),
        "slot_retry_counts": state.get("slot_retry_counts") or {},
        "pending_modify_target": state.get("pending_modify_target", False),
        "handoff_reason": state.get("handoff_reason"),
        "booking_revision": state.get("booking_revision", 0),
        "booking_status": state.get("booking_status", "collecting"),
        "booking_id": state.get("booking_id"),
        "turn_index": state.get("turn_index", 0) + 1,
        "is_terminal": False,
        "intents": [], "primary_intent": None,
        "turn_extracted_slots": [], "turn_addressed_slots": [],
        "clarification_response": None, "map_service_result": None,
        "qa_response": None, "tool_status": None, "final_response_text": "",
    }
~~~

## 4. Node 2 — Extractor

`run_llm_extractor` trả contract trong extractor.md. `validate_extractor_output` kiểm tra enum, kiểu, chỉ số stopover, metadata, source và operation; gộp nhiều update cùng slot theo giá trị sửa cuối cùng. Lỗi schema/timeout có fallback, không làm sập graph. Đây là xử lý lỗi có giới hạn, không gọi `try/except` đơn lẻ là một circuit breaker hoàn chỉnh.

~~~python
def extractor_node(state):
    context = {
        "user_text": state["user_current_input"],
        "session_city": state.get("session_city"),
        "timezone": state["timezone"],
        "turn_received_at": state["turn_received_at"],
        "last_bot_action": state.get("last_bot_action"),
        "existing_slots_summary": extract_slots_summary(state["booking_slots"]),
        "recent_dialog_turns": state.get("messages", [])[-4:],
    }
    try:
        result = validate_extractor_output(run_llm_extractor(context), context)
    except Exception:
        result = {
            "intents": ["unclear"], "primary_intent": "unclear",
            "extracted_slots": [], "addressed_slots": [],
            "clarification_response": None, "confidence": 0.0,
        }
    misunderstood = (
        result["intents"] == ["unclear"] and not result["extracted_slots"]
    )
    return {
        "intents": result["intents"], "primary_intent": result["primary_intent"],
        "turn_extracted_slots": result["extracted_slots"],
        "turn_addressed_slots": result["addressed_slots"],
        "clarification_response": result["clarification_response"],
        "fallback_count": state.get("fallback_count", 0) + 1 if misunderstood else 0,
    }
~~~

## 5. Node 3 — Map, không bỏ qua đường alias

`resolve_address_update` thực hiện toàn bộ pipeline trong map.md: hợp nhất câu trả lời làm rõ, CRM, alias theo city, fuzzy, Vietmap, sub-POI, bảo toàn raw/note/components. Trả `{"slot": AddressSlot, "tool_status": ...}`; mọi đường alias cũng đi qua xử lý gate và metadata.

`prepare_address_updates` là helper của Map:
- Lấy pickup/destination và `stopovers:i` mới; expand `stopovers` thành các update theo thứ tự.
- Nếu có city mới, kiểm tra lại pickup hiện có và các địa chỉ phụ thuộc vùng cũ; đồng thời requery slot đang chờ trả lời city. Giữ city riêng của điểm đến được nói rõ.
- Operation `clear` không geocode. Với stopovers list, normalize append thành operation replace chứa danh sách items đầy đủ (điểm cũ + điểm mới); target stopovers:i trỏ vào danh sách này. Giữ các điểm không bị sửa.
- Không tạo địa chỉ từ những địa danh chỉ xuất hiện trong câu hỏi QA.

~~~python
def map_service_node(state):
    updates = state.get("turn_extracted_slots", [])
    city = next((s["value"] for s in reversed(updates)
                 if s["slot_name"] == "session_city"), state.get("session_city"))
    prepared, stopover_operation = prepare_address_updates(state, city)
    results, overall = {}, "SUCCESS"
    for target, update in prepared:
        result = resolve_address_update(
            update=update, target=target, session_city=city,
            existing_slots=state["booking_slots"],
            crm_profile=state.get("crm_profile"),
        )
        if stopover_operation and target.startswith("stopovers:"):
            index = int(target.split(":")[1])
            stopover_operation["items"][index]["address"] = result["slot"]
        else:
            results[target] = result["slot"]
        overall = max(overall, result["tool_status"],
                      key=lambda item: STATUS_SEVERITY[item])
    return {
        "map_service_result": {"addresses": results,
                               "stopover_operation": stopover_operation},
        "tool_status": overall, "session_city": city,
    }
~~~

`stopover_operation` là `None` hoặc `{"operation": "replace"|"clear", "items": List[StopoverSlot]}`. Input append được helper dựng thành danh sách replacement đầy đủ trước resolve. Khi expand danh sách mới, resolve từng điểm rồi đặt vào items; không đưa chỉ số chưa tồn tại vào `addresses`. Update `stopovers:i` chỉ áp dụng vào điểm đang tồn tại.

Không có dữ liệu local là miss bình thường. Mock không biết địa chỉ trả NOT_FOUND. Live timeout/HTTP lỗi/schema nhà cung cấp hỏng trả API_ERROR; không tự chuyển từ live sang mock để giả thành công.

## 6. Node 4 — nơi duy nhất thay booking_slots

`merge_map_results` copy đầy đủ AddressSlot, áp dụng stopover_operation và target hiện hữu. `invalidate_target` giữ raw để làm rõ nhưng bỏ formatted, coords, ID/gate/candidate bị từ chối, đặt precision unknown và status needs_clarification; slot giá trị bỏ value. `clear_booking_target` xóa theo schema mặc định. Các helper này thuộc reducer, không gọi mạng.

`apply_verified_default_gate` là helper thuần: nhận bản ghi cổng đã duyệt từ DAL; thay coords/gate_id/formatted, giữ raw/note khách, thêm chỉ dẫn cổng, đặt precision anchor, gate_resolved/default_point_used true và status extracted. Không có cổng thì không gán cờ thành công.

~~~python
def state_reducer_node(state):
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
    edits = bool(updates)              # Bao gồm cả optional slot và clear
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
                    None, item["source_text"], state["turn_received_at"], state["timezone"])
            else:
                clear_booking_target(slots, name)
        elif name == "pickup_time":
            slots[name] = normalize_pickup_time(
                val, item["source_text"], state["turn_received_at"], state["timezone"]
            )
        elif name in {"vehicle_type", "passengers"}:
            valid = val in VEHICLES if name == "vehicle_type" else (
                isinstance(val, int) and not isinstance(val, bool) and val > 0
            )
            slots[name] = {"value": val, "status": "extracted" if valid else "needs_clarification"}
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

    time = slots["pickup_time"]
    if time["status"] == "empty" and time["value"] is None and time["raw"] is None and (
        slots["pickup"]["raw"] or slots["destination"]["raw"]
    ):
        slots["pickup_time"] = {"value": "now", "raw": None, "anchored_at": None,
                                "status": "extracted"}
    elif time["value"] is not None and not valid_time(time, state["turn_received_at"]):
        time["status"] = "needs_clarification"

    # Địa chỉ thay thế tự nguyện mở episode mới; phản hồi cứu hộ vẫn tính episode cũ.
    addressed = set(state.get("turn_addressed_slots", []))
    for item in updates:
        name = item["slot_name"]
        if (name in address_targets(slots) and name not in addressed
                and (item.get("metadata") or {}).get("operation", "replace") == "replace"):
            retry[name] = 0

    # Deny không có thay thế: invalidate đúng mục tiêu, không xóa các slot khác.
    replaced = {u["slot_name"] for u in updates}
    if "stopovers" in replaced:
        replaced.update(t for t in targets if t.startswith("stopovers:"))
    unknown_answer = last_type == "clarify_address" and (
        state.get("clarification_response") == "unknown"
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

    # Chỉ đếm phản hồi thực sự cho câu hỏi slot; FAQ/xã giao chen ngang không tính.
    addressed = set(state.get("turn_addressed_slots", []))
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
            retry[target] = retry.get(target, 0) + 1
            if last_meta.get("type") == "mega_poi_gate" and response in {"unknown", "detail"}:
                gate = in_memory_lookup_default_gate(slot.get("place_id"), "pickup")
                if gate:
                    apply_verified_default_gate(slot, gate)
                    retry[target] = 0
                else:
                    reason = "missing_safe_pickup"
            elif role == "destination":
                if response != "reject_candidates" and relative_destination_known(slot):
                    slot["status"] = "extracted"
                    slot["requires_confirmation"] = False
                    slot["note"] = join_notes(slot.get("note"),
                        "Điểm đến tương đối; trao đổi chi tiết khi gần đến nơi.")
                    retry[target] = 0
                else:
                    reason = "destination_unresolved"
            elif role == "stopover":
                reason = "stopover_unresolved"
            elif slot.get("clarification_kind") == "landmark" or response == "reject_candidates":
                reason = "pickup_unresolved"
    for target in address_targets(slots):
        if address_ready(get_target(slots, target), target_role(target)):
            retry[target] = 0

    # Confirm chỉ tác động action còn hiệu lực; cancel/operator luôn chặn đặt.
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
            revision_matches = last_meta.get("booking_revision") == state.get("booking_revision", 0)
            allowed = (
                not edits and revision_matches and not pending and not reason
                and "request_operator" not in intents and state.get("fallback_count", 0) < 2
                and state.get("tool_status") != "API_ERROR"
                and check_is_ready_to_book(slots, state["turn_received_at"])
            )
            if allowed:
                for name in CORE:
                    slots[name]["status"] = "confirmed"
                for stop in slots["stopovers"]:
                    stop["address"]["status"] = "confirmed"
                if slots["passengers"]["status"] != "empty":
                    slots["passengers"]["status"] = "confirmed"
                status = "booked"
            elif status != "cancel_pending":
                status = "collecting"

    # Ready tính sau TẤT CẢ thay đổi, không để Policy fallback rồi dùng cờ cũ.
    ready = (
        check_is_ready_to_book(slots, state["turn_received_at"])
        and not pending and not reason and state.get("tool_status") != "API_ERROR"
    )
    if status in {"collecting", "ready_to_book", "confirming"}:
        status = "ready_to_book" if ready else "collecting"
    return {
        "booking_slots": slots, "slot_retry_counts": retry,
        "pending_modify_target": pending, "handoff_reason": reason,
        "booking_revision": state.get("booking_revision", 0) + int(slots != before),
        "session_city": city, "ready_to_book": ready, "booking_status": status,
    }
~~~

Retry reset khi slot được giải quyết. Địa chỉ thay thế tự nguyện (không trả lời câu clarify trước) mở episode mới; reducer reset retry đúng target trước tính readiness. Không reset chỉ vì câu hỏi chen ngang. City được Map requery trước khi Reducer áp dụng.

## 7. Node 5 — QA đọc state mới

~~~python
def qa_dispatcher_node(state):
    response = dispatch_questions(
        user_text=state["user_current_input"], slots=state["booking_slots"],
        session_city=state.get("session_city"), timezone=state["timezone"],
    )
    # dispatch_questions bắt lỗi tool/KB và luôn trả QAResponse có answer_text.
    return {"qa_response": response}
~~~

FAQ rỗng không gây handoff. Tool QA lỗi trả lời không có dữ liệu; chỉ lỗi định vị thiết yếu chặn đặt xe theo tool_status Map. Nếu câu có nhiều câu hỏi, dispatcher trả lời các phần có nguồn trong tối đa 1–2 câu; không làm mất entity vừa cập nhật.

## 8. Node 6 — Policy chỉ đọc slot

~~~python
def action_result(kind, targets, status, **metadata):
    return {
        "last_bot_action": {"action_type": kind, "target_slots": targets,
                            "metadata": metadata},
        "booking_status": status,
        "current_focus": targets[0] if targets else None,
    }

def action_policy_node(state):
    status = state["booking_status"]
    slots = state["booking_slots"]
    intents = set(state.get("intents", []))
    retry = state.get("slot_retry_counts") or {}

    if status == "canceled":
        return action_result("inform_canceled", [], status)
    if status == "booked":
        return action_result("inform_success", [], status)
    if status == "operator_required":
        return action_result("human_handoff", [], status, reason=state.get("handoff_reason"))
    reason = state.get("handoff_reason")
    if ("request_operator" in intents or reason or state.get("fallback_count", 0) >= 2
            or state.get("tool_status") == "API_ERROR" or retry.get("pickup", 0) >= 2):
        reason = reason or (
            "operator_requested" if "request_operator" in intents else
            "api_error" if state.get("tool_status") == "API_ERROR" else
            "pickup_retry_limit" if retry.get("pickup", 0) >= 2 else "fallback_limit"
        )
        return action_result("human_handoff", [], "operator_required", reason=reason)
    if "cancel" in intents or status == "cancel_pending":
        return action_result("confirm_cancel", [], "cancel_pending")
    if state.get("pending_modify_target"):
        return action_result("general_reply", [], "collecting", type="ask_modify_slot")
    if "repeat_request" in intents and not state.get("turn_extracted_slots"):
        previous = state.get("last_bot_action") or {}
        if previous:
            metadata = {**(previous.get("metadata") or {}), "repeat_previous": True}
            return action_result(previous["action_type"], previous.get("target_slots") or [],
                                 status, **metadata)

    for target in address_targets(slots):
        slot = get_target(slots, target)
        if slot["requires_confirmation"]:
            return action_result("confirm_slots", [target], "collecting", type="proposed_address")
    pickup = slots["pickup"]
    if pickup["is_mega_poi"] and not pickup["gate_resolved"]:
        return action_result("clarify_address", ["pickup"], "collecting", type="mega_poi_gate")
    for target in address_targets(slots):
        slot = get_target(slots, target)
        if slot["status"] == "needs_clarification":
            return action_result("clarify_address", [target], "collecting",
                                 type=slot["clarification_kind"] or "narrow")
    if state["ready_to_book"]:
        return action_result("confirm_booking", CORE, "confirming",
                             booking_revision=state["booking_revision"])
    if intents == {"unclear"}:
        return action_result("general_reply", [], status, type="unclear_prompt")
    if "chit_chat" in intents and slots["pickup"]["status"] == "empty":
        return action_result("general_reply", ["pickup"], status, type="greeting")

    # Không có fallback trả pickup khi thực ra chỉ lỗi giờ/loại xe/điểm dừng.
    missing = next_missing_requested_slot(slots, state["turn_received_at"])
    if missing is None:
        raise ValueError("State không ready nhưng không xác định được slot cần xử lý")
    return action_result("ask_slot", [missing], "collecting")
~~~

`next_missing_requested_slot` dùng cùng validator readiness: pickup → destination → vehicle_type → pickup_time → điểm dừng đã yêu cầu → passengers đã nêu nhưng lỗi. Không hỏi optional rỗng. Policy chỉ trả state updates, không mutate input.

## 9. Node 7 — văn bản thoại sạch

~~~python
def format_pickup_time_display(slot, timezone):
    if slot["value"] == "now":
        return "đón ngay bây giờ"
    if slot["value"] is None:
        return "thời gian đón chưa xác định"
    dt = parse_aware(slot["value"]).astimezone(ZoneInfo(timezone))
    minute = f" {dt.minute} phút" if dt.minute else ""
    return f"đón lúc {dt.hour} giờ{minute}, ngày {dt.day} tháng {dt.month} năm {dt.year}"

def response_synthesizer_node(state):
    qa = state.get("qa_response") or {}
    action = state["last_bot_action"]
    # Giữ action hiệu lực khi repeat; không chỉ gán general_reply rồi mất confirm context.
    action_text = last_bot_text(state.get("messages", [])) if (
        (action.get("metadata") or {}).get("repeat_previous")
    ) else render_template_by_action(
        action=state["last_bot_action"], slots=state["booking_slots"],
        customer_name=state["customer_name"],
        pickup_time_display=format_pickup_time_display(
            state["booking_slots"]["pickup_time"], state["timezone"]),
        previous_bot_text=last_bot_text(state.get("messages", [])),
    )
    text = join_speech(qa.get("answer_text", ""), action_text)
    validate_spoken_text(text)   # Không ANSI/JSON/Markdown/enum; số, địa chỉ đọc tự nhiên
    messages = list(state.get("messages", [])) + [
        {"role": "user", "content": state["user_current_input"]},
        {"role": "bot", "content": text},
    ]
    return {
        "final_response_text": text, "messages": messages,
        "is_terminal": state["booking_status"] in {"booked", "canceled", "operator_required"},
    }
~~~

Tóm tắt chứa cả điểm dừng/số khách/ghi chú đã yêu cầu. Template nhắc khác biệt giữa raw chi tiết và điểm ghim; không hứa tài xế vào ngách hay ETA khi chưa có khả năng điều xe. QA success=False vẫn được đọc answer_text.

## 10. Node 8 — một transaction, phát câu trả lời sau commit

~~~python
def persistence_node(state):
    # DAL lưu turn + audit + session + booking + CRM trong cùng transaction.
    # UNIQUE(session_id, turn_index) và UNIQUE(bookings.session_id) chống ghi trùng.
    result = db_persist_turn(state)
    return {"booking_id": result.get("booking_id")}
~~~

Nếu lỗi ghi DB: raise PersistenceError, graph không trả kết quả thành công cho adapter. CLI chưa phát final_response_text, báo “Dạ hiện tại em chưa thể xác nhận việc lưu yêu cầu, mình thử lại sau giúp em ạ.” và đóng lượt lỗi. Không retry bằng cách đưa cùng phát ngôn vào một lượt mới. Kiểm tra outcome bằng session/turn key rồi resume node persistence với payload cũ hoặc mở phiên mới khi đã xác định chưa lưu; không phát lại success trước khi biết kết quả commit.

## 11. Routing và lắp graph

~~~python
def route_after_extractor(state):
    if any(
        s["slot_name"] in {"pickup", "destination", "stopovers", "session_city"}
        or s["slot_name"].startswith("stopovers:")
        for s in state.get("turn_extracted_slots", [])
    ):
        return "map_service_node"
    return "state_reducer_node"

def route_after_reducer(state):
    return "qa_dispatcher_node" if "ask_question" in state["intents"] else "action_policy_node"

def route_turn_outcome(state):
    return "terminate_session" if state["is_terminal"] else "end_turn"
~~~

~~~python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from src.core.state import ParrotGoGraphState

def build_parrotgo_graph():
    builder = StateGraph(ParrotGoGraphState)
    nodes = {
        "session_init_node": session_init_node,
        "extractor_node": extractor_node,
        "map_service_node": map_service_node,
        "state_reducer_node": state_reducer_node,
        "qa_dispatcher_node": qa_dispatcher_node,
        "action_policy_node": action_policy_node,
        "response_synthesizer_node": response_synthesizer_node,
        "persistence_node": persistence_node,
    }
    for name, handler in nodes.items():
        builder.add_node(name, handler)
    builder.add_edge(START, "session_init_node")
    builder.add_edge("session_init_node", "extractor_node")
    builder.add_conditional_edges("extractor_node", route_after_extractor, {
        name: name for name in ["map_service_node", "state_reducer_node"]})
    builder.add_edge("map_service_node", "state_reducer_node")
    builder.add_conditional_edges("state_reducer_node", route_after_reducer, {
        name: name for name in ["qa_dispatcher_node", "action_policy_node"]})
    builder.add_edge("qa_dispatcher_node", "action_policy_node")
    builder.add_edge("action_policy_node", "response_synthesizer_node")
    builder.add_edge("response_synthesizer_node", "persistence_node")
    builder.add_conditional_edges("persistence_node", route_turn_outcome, {
        "end_turn": END, "terminate_session": END})
    return builder.compile(checkpointer=InMemorySaver())
~~~

Gọi với `config={"configurable": {"thread_id": session_id}}`. Lượt đầu truyền metadata + input; lượt tiếp chỉ truyền user_current_input và turn_received_at, không ghi đè state tích lũy.

`InMemorySaver` mất checkpoint khi process dừng. Khi nâng cấp persistent checkpointer phải thêm package, quản lý connection/lifecycle và kiểm thử resume cùng idempotency DAL; không coi là đổi một dòng đã đủ. Tham chiếu [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).
