# KIẾN TRÚC MVP CLI PARROTGO

Tài liệu này chốt phạm vi và schema dùng chung. Luồng thực thi nằm trong [langgraph.md](./langgraph.md), quy tắc hội thoại trong [planner.md](./planner.md), NLU trong [extractor.md](./extractor.md), địa chỉ trong [map.md](./map.md), hỏi đáp trong [ask.md](./ask.md), lưu trữ trong [database.md](./database.md), lộ trình triển khai trong [plan.md](./plan.md).

## 1. Phạm vi và giao tiếp ASR → Core → TTS

MVP là bot đặt xe qua CLI. Mỗi lượt nhận một phát ngôn văn bản hoàn chỉnh như ASR trả về: có thể thiếu dấu câu, có số viết bằng chữ, câu cụt hoặc tự sửa giữa câu. Không cần triển khai ASR/TTS để chạy MVP.

- `user_current_input` giữ nguyên văn bản nhận được. Chuẩn hóa tìm kiếm trên bản sao; không sửa transcript.
- Core trả `final_response_text: str` chỉ gồm lời bot có thể truyền thẳng sang TTS: không JSON, Markdown, ANSI, tên enum, log hay debug state.
- Tên, số điện thoại, UUID phiên, thành phố cấu hình và đồng hồ tham chiếu là metadata phiên/lượt, không phải câu đặt xe.
- Chế độ CLI thuần dùng stdout cho lời bot, stderr cho prompt nhập, log và giao diện Rich. Dòng trống/EOF là thao tác CLI, không gửi vào NLU.
- Mỗi phiên xử lý tuần tự một lượt tại một thời điểm. Khi terminal, tạo phiên mới nếu muốn đặt tiếp; không tiếp tục invoke thread cũ.

RAG và dữ liệu địa danh được phép rỗng. Xây adapter, schema và công cụ nạp dữ liệu trước; không bắt buộc tạo 30–50 chính sách hoặc danh mục địa danh thật để chạy MVP.

`booked` trong MVP nghĩa là **khách đã xác nhận và yêu cầu đã được lưu thành công vào SQLite**. Chưa có hệ thống điều xe, tài xế, tổng đài chuyển cuộc gọi hay cam kết thời gian tài xế tới. Mẫu thoại phải phản ánh đúng khả năng này. Tích hợp dispatch và chuyển máy thật là giai đoạn sau.

## 2. Thông tin cuốc xe

Bốn thông tin cốt lõi:

| Slot | Điều kiện nghiệp vụ |
| --- | --- |
| `pickup` | Tọa độ hợp lệ và điểm đón có thể tìm được: địa chỉ cụ thể, mốc cố định kèm ghi chú, hoặc cổng Mega POI đã giải quyết. Không dùng tâm phường hay tâm khu rộng để giả làm điểm đón. |
| `destination` | Địa chỉ, địa danh, trục đường hoặc xã/phường có tỉnh/thành đã xác định. `raw` khác rỗng chưa đủ chứng minh hợp lệ. |
| `vehicle_type` | `xe_may`, `oto_4_cho` hoặc `oto_7_cho`. |
| `pickup_time` | `now` hoặc ISO 8601 có múi giờ, đã qua kiểm tra ngữ nghĩa. |

`stopovers`, `passengers`, `general_note` là tùy chọn; không hỏi nếu khách không nêu. Khi khách đã yêu cầu điểm dừng thì phải giải quyết và đưa vào tóm tắt, không âm thầm bỏ qua. Không tự gán số khách bằng sức chứa xe.

Giá/km và chính sách chỉ lấy từ dữ liệu đã duyệt. Không tự nhân thành tổng tiền cố định. Quãng đường/thời gian hành trình chỉ trả khi khách hỏi, dưới dạng khoảng và nói rõ phụ thuộc hành trình/giao thông thực tế. Lịch hẹn đón khác với thời gian hành trình.

## 3. Schema chuẩn

Khi triển khai, đặt định nghĩa duy nhất trong `src/core/state.py`; các module import từ đây. `BotState` và `ParrotGoGraphState` là cùng một kiểu. TypedDict chỉ mô tả kiểu; đầu vào LLM, seed và dữ liệu tool cần validator runtime.

`metadata` trong contract là dict, mặc định `{}`. Adapter chấp nhận trường thiếu hoặc `null` và chuẩn hóa bằng `value or {}` trước khi dùng.

~~~python
from typing import Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict

Intent = Literal[
    "provide_info", "change_info", "confirm", "deny", "cancel",
    "ask_question", "chit_chat", "request_operator", "repeat_request", "unclear",
]
SlotStatus = Literal["empty", "extracted", "confirmed", "needs_clarification"]
Precision = Literal["exact", "anchor", "road", "ward", "poi", "unknown"]
BookingStatus = Literal[
    "collecting", "ready_to_book", "confirming", "booked",
    "cancel_pending", "canceled", "operator_required",
]

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
    raw: Optional[str]                   # Toàn bộ địa chỉ/chi tiết khách nói
    formatted: Optional[str]             # Tên/địa chỉ chuẩn từ nguồn địa lý
    coords: Optional[Coordinates]
    components: AddressComponents
    note: Optional[str]
    place_id: Optional[str]              # Khóa địa điểm ổn định, không join bằng tên
    gate_id: Optional[str]
    location_precision: Precision
    is_mega_poi: bool
    default_point_used: bool
    gate_resolved: bool
    requires_confirmation: bool          # Đề xuất CRM/fuzzy chưa được khách chấp nhận
    clarification_kind: Optional[str]    # city, ab, narrow, landmark, mega_poi_gate
    candidates: List[Dict[str, Any]]       # Giữ xuyên lượt; lời thoại tối đa 2 lựa chọn
    status: SlotStatus

class ValueSlot(TypedDict):
    value: Any
    status: SlotStatus

class PickupTimeSlot(TypedDict):
    value: Optional[str]                 # now hoặc ISO có offset
    raw: Optional[str]                   # Chuỗi hẹn gốc; có raw lỗi thì không mặc định now
    anchored_at: Optional[str]           # turn_received_at lúc giải nghĩa thời gian
    status: SlotStatus

class StopoverSlot(TypedDict):
    address: AddressSlot
    order: int                           # Liên tiếp từ 1, theo thứ tự khách yêu cầu

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
        "ask_slot", "confirm_slots", "confirm_booking", "clarify_address",
        "answer_question", "inform_success", "general_reply",
        "confirm_cancel", "inform_canceled", "human_handoff",
    ]
    target_slots: List[str]               # pickup, destination, stopovers:0, ...
    metadata: Dict[str, Any]              # confirm_booking chứa booking_revision

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
    session_city: Optional[str]           # None = chưa biết; không tự ép thành Hà Nội
    timezone: str                        # MVP: Asia/Ho_Chi_Minh
    turn_received_at: str                 # ISO có offset, do adapter ghi một lần/lượt
    crm_profile: Optional[Dict[str, Any]]
    messages: List[Dict[str, str]]
    user_current_input: str
    intents: List[Intent]
    primary_intent: Optional[Intent]
    turn_extracted_slots: List[ExtractedSlotUpdate]
    turn_addressed_slots: List[str]       # Lượt này thực sự trả lời slot nào
    clarification_response: Optional[
        Literal["detail", "unknown", "reject_candidates"]
    ]
    map_service_result: Optional[Dict[str, Any]]
    qa_response: Optional[QAResponse]
    tool_status: Optional[Literal["SUCCESS", "NOT_FOUND", "AMBIGUOUS", "API_ERROR"]]
    booking_slots: BookingSlots
    current_focus: Optional[str]
    last_bot_action: Optional[BotAction]
    fallback_count: int                   # Số lượt unclear liên tiếp, không có entity hợp lệ
    slot_retry_counts: Dict[str, int]       # Chỉ số nguyên; không chứa cờ điều phối
    pending_modify_target: bool
    handoff_reason: Optional[str]
    booking_revision: int
    ready_to_book: bool                   # Reducer tính lại, Policy chỉ đọc
    booking_status: BookingStatus
    booking_id: Optional[str]             # DAL cấp sau khi transaction commit
    final_response_text: str
    is_terminal: bool
    turn_index: int

BotState = ParrotGoGraphState
~~~

Khởi tạo địa chỉ: chuỗi/tọa độ/ID/note = `None`, components = `{}`, candidates = `[]`, precision = `unknown`, mọi cờ = `False`, status = `empty`. Slot giá trị = `{"value": None, "status": "empty"}`. Thời gian thêm raw/anchored_at = `None`. Stopovers rỗng; dữ liệu hành trình = `None`.

## 4. Bất biến của state và xác nhận

1. Extractor chỉ bóc tách; Map chỉ trả kết quả đã kiểm chứng; **Reducer là nơi duy nhất sửa booking_slots, retry và ready_to_book**. Policy không sửa trực tiếp dict đầu vào.
2. Áp dụng thông tin mới trước Q&A. Q&A đọc state sau Reducer và không tự thay điểm đến khi khách chỉ hỏi về địa danh khác.
3. `confirmed` chỉ dùng sau xác nhận rõ của khách. Geocode thành công và fallback hợp lệ có status `extracted`, không tự đóng vai xác nhận.
4. Mọi thay đổi nội dung cuốc, kể cả điểm dừng/số khách/ghi chú, làm mất hiệu lực tóm tắt trước đó. `confirm_booking.metadata.booking_revision` phải khớp phiên bản hiện tại.
5. Xác nhận kèm sửa đổi luôn đọc lại tóm tắt. Chỉ chuyển `booked` khi không có sửa đổi cùng lượt, ready còn đúng, không có yêu cầu hủy/chuyển hỗ trợ hoặc lỗi chặn.
6. `deny` một slot không có thay thế: invalidate đúng slot, giữ raw để làm rõ nhưng không dùng tọa độ/giá trị đã bị từ chối để đặt xe. `deny` tóm tắt nhiều slot không rõ mục tiêu: đặt `pending_modify_target=True`; không tự đổ lỗi cho destination.
7. Cờ pending được xóa khi khách chỉ rõ/cập nhật/xóa một thông tin cuốc. Nếu khách chỉ hỏi FAQ hoặc nói “ừ” với câu hỏi cần sửa gì, vẫn hỏi mục tiêu sửa.
8. `cancel_pending` được giữ qua Q&A/xã giao. Confirm hủy → `canceled`; deny hủy → quay lại thu thập/xác nhận.
9. Terminal (`booked/canceled/operator_required`) không bị node lượt mới mở lại.

## 5. Điều kiện ready_to_book

Reducer kiểm tra cuối mỗi lượt, sau merge, deny, fallback và xác nhận:

- Pickup status hợp lệ; coords hữu hạn trong giới hạn lat/lng; precision `exact` hoặc `anchor`; đề xuất CRM/fuzzy đã được chấp nhận. Mega POI phải `gate_resolved=True`; điểm mặc định phải có gate ID, tọa độ cổng và note.
- Destination status hợp lệ; formatted có nội dung; components.province_city xác định; precision thuộc `exact/anchor/road/ward/poi`; không còn đề xuất chờ xác nhận.
- Loại xe đúng enum và status hợp lệ.
- Giờ đón là `now` hoặc ISO có offset còn trong tương lai so với `turn_received_at`; status hợp lệ. Giờ hẹn đã qua cần hỏi lại.
- Các stopover được khách yêu cầu có coords hợp lệ, status hợp lệ, không còn đề xuất chờ xác nhận; Mega POI có điểm cổng đã giải quyết. Số khách nếu đã nêu là số nguyên dương.
- Không có `pending_modify_target`, `handoff_reason` hay `API_ERROR`.

## 6. Đồng hồ và địa lý

`turn_received_at` do adapter ghi trước invoke, không thay đổi khi retry cùng lượt. Giờ tương đối được neo một lần tại lượt nhận; không tính lại ở lượt xác nhận. Hẹn giờ không rõ ngày hoặc giờ đã qua không được tự đẩy sang ngày mai. Chi tiết trong [extractor.md](./extractor.md).

`session_city` là vùng điểm đón. Cấu hình mặc định chỉ gán khi tạo phiên; nếu không cấu hình thì giữ `None` và hỏi tỉnh/thành khi cần. Điểm đến có tỉnh/thành khác dùng địa lý riêng của điểm đến. Khi thay vùng điểm đón, Map phải kiểm tra lại những địa chỉ bị ảnh hưởng, không chỉ sửa một chuỗi city rồi giữ tọa độ cũ.

## 7. Lưu trữ và kết thúc phiên

Trước lượt đầu: upsert khách hàng và tạo `call_sessions` trong một transaction. Mỗi lượt lưu message, audit, trạng thái phiên và booking/CRM (nếu chốt) trong **một transaction**. Chỉ phát lời thành công ra CLI/TTS sau commit. Ràng buộc uniqueness bảo vệ khi chạy lại cùng lượt; không tăng tổng cuốc/favorite hai lần.

MVP dùng checkpointer RAM để giữ state trong cùng tiến trình; SQLite giữ lịch sử nghiệp vụ. Sau restart tạo phiên mới, chưa phục hồi hội thoại dở dang. Phục hồi state/checkpoint bền vững là nâng cấp riêng, không suy ra từ việc đã có transcript SQLite.
