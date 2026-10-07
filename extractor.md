# EXTRACTOR: NLU VÀ THỰC THỂ TỪ VĂN BẢN ASR

Schema chung: [architecture.md](./architecture.md). Địa chỉ: [map.md](./map.md). State và retry: [langgraph.md](./langgraph.md). Lời thoại: [planner.md](./planner.md).

## 1. Trách nhiệm

Nhận nguyên phát ngôn ASR, đọc ngữ cảnh, trích xuất mọi intent và thông tin đặt xe. Không sinh tọa độ, không tự đánh dấu booked, không tự trả chính sách/giá và không viết lời bot.

Giữ văn bản gốc trong user_current_input/source_text. Chuẩn hóa trên bản sao cho phân tích; không ép người dùng gõ lệnh, JSON, dấu câu hoặc số dạng chữ số.

Luồng đúng: Extractor → Map nếu có địa chỉ/city/stopover → Reducer → QA nếu có câu hỏi → Policy → Synthesizer.

## 2. Contract đầu vào/đầu ra

Import `Intent`, `ExtractedSlotUpdate`, `BotAction` từ `src/core/state.py`, không tạo schema lệch ở module khác.

~~~python
from typing import Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict
from src.core.state import BotAction, ExtractedSlotUpdate, Intent

class ExtractorInputContext(TypedDict):
    user_text: str
    session_city: Optional[str]
    timezone: str
    turn_received_at: str
    last_bot_action: Optional[BotAction]   # Đầy đủ metadata, target và revision
    existing_slots_summary: Dict[str, Any]
    recent_dialog_turns: List[Dict[str, str]]

class ExtractorOutput(TypedDict):
    intents: List[Intent]
    primary_intent: Intent
    extracted_slots: List[ExtractedSlotUpdate]
    addressed_slots: List[str]
    clarification_response: Optional[
        Literal["detail", "unknown", "reject_candidates"]
    ]
    confidence: float
~~~

`primary_intent` phục vụ audit; Policy quyết định theo toàn bộ intents, không chỉ primary. Chuẩn hóa thứ tự intents để ổn định, ưu tiên primary: operator → cancel → deny → change/provide → confirm → question → repeat → chat → unclear.

### Slot và operation

| slot_name | value |
| --- | --- |
| pickup, destination | Chuỗi địa chỉ/query. Metadata chứa nguyên địa chỉ, phần bổ sung và ghi chú. |
| pickup_time | `now`, `+15m`/`+2h`, `HH:MM` hoặc ISO có offset. Đây là kết quả NLU, chưa phải giá trị lưu DB. |
| vehicle_type | `xe_may`, `oto_4_cho`, `oto_7_cho`. |
| stopovers | List `{"value": str, "source_text": str, "metadata": {}}` theo thứ tự; Map dựng StopoverSlot chuẩn. |
| stopovers:i | Chuỗi bổ sung/sửa cho điểm dừng index i đang tồn tại (index bắt đầu 0). |
| passengers | Số nguyên dương; validator/reducer kiểm tra. |
| general_note | Chuỗi yêu cầu/ghi chú do khách nói. |
| session_city | Tỉnh/thành của điểm đón hoặc None khi yêu cầu xóa vùng. |

Metadata:
- `operation`: `replace` (mặc định), `augment` (chỉ bổ sung địa chỉ đang hỏi), `clear` (xóa slot được nêu rõ; value=None). Stopovers list còn hỗ trợ `append`. Không suy diễn “không” chung thành clear toàn bộ.
- `raw_full`, `head_alley`, `detail`, `direction_modifier`, `anchor_landmark`, `driver_note`.
- `component_type`, `action=disambiguation_resolve` khi bổ sung district/ward/city.
- `address_city` cho địa chỉ có tỉnh/thành được nói rõ; điểm đến khác tỉnh không tự sửa session_city.
- `is_mega_poi`, `sub_poi`; `is_crm_alias`, `crm_alias_type`.
- Metadata dict mặc định `{}`; normalize missing/null thành dict trước mọi `.get`.

`addressed_slots` cho biết khách **thực sự trả lời** slot nào trong action trước: cung cấp chi tiết, từ chối candidate hoặc nói không biết. FAQ/chit_chat/repeat đơn thuần không có addressed_slots. Slot mới tự nguyện không phải câu trả lời cho slot khác đang hỏi.

`clarification_response` chỉ mô tả phản hồi cho action `clarify_address`:
- detail: có bổ sung/thay thế/đáp án.
- unknown: “không biết số nhà/cổng”, “cứ đến cổng chính”, khi không từ chối địa điểm.
- reject_candidates: “không phải nơi đó”, “không phải cả hai”.
- None: không trả lời câu làm rõ.

Nếu câu nói từ chối và cung cấp địa chỉ mới rõ ràng, update replace mới được ưu tiên; không tự xóa lại giá trị mới. Nếu nói “loại xe sai” nhưng chưa có thay thế, xuất update vehicle_type với operation=clear để hỏi lại đúng loại xe.

## 3. Intent taxonomy

| Intent | Hành vi bóc tách |
| --- | --- |
| provide_info | Cung cấp giá trị mới; giữ mọi entity hợp lệ. |
| change_info | Sửa thông tin đang có; ghi đúng slot và giá trị sau cùng. |
| confirm | Chỉ xác nhận câu bot vừa hỏi; không biến câu cung cấp dữ liệu đầu tiên thành chốt cuốc. |
| deny | Từ chối mục tiêu của action trước; chỉ rõ slot sai nếu câu nói cho biết. |
| cancel | “Không đi nữa”, “hủy đặt xe”; không lẫn với “không đúng địa chỉ”. |
| ask_question | Hỏi FAQ, route, thông tin state; có thể đồng thời provide/change. |
| chit_chat | Chào hỏi, trò chuyện ngắn. |
| request_operator | Muốn gặp người thật/tổng đài viên. |
| repeat_request | Yêu cầu nhắc lại. |
| unclear | Không hiểu được nội dung; vẫn giữ entity nhận diện hợp lệ nếu có. |

“Không biết cổng” là phản hồi unknown cho slot đang hỏi, không phải noise và không tự tính vào chuỗi unclear. Fallback counter chỉ tăng khi kết quả sau chuẩn hóa là unclear đơn thuần, không có update; mọi lượt hiểu được (QA/chat/deny/repeat kể cả không có entity) reset về 0.

## 4. Bóc tách theo ngữ cảnh và ASR

- “Bốn chỗ”, “xe con” → oto_4_cho; “bảy chỗ”, “xe gia đình” → oto_7_cho; “xe ôm” → xe_may. Không đổi loại xe chỉ vì khách hỏi “7 chỗ chở được mấy người?”.
- Số nhà/ngõ/ngách đọc bằng chữ được chuẩn hóa theo ngữ cảnh. Giữ slash, suffix (148A, 34/56); không thay số điện thoại hoặc tên riêng bằng quy tắc số toàn cục.
- Thiếu dấu câu vẫn tách đón/đến qua “đón ở”, “từ”, “chở qua”, “về”, “sang”; nếu chưa rõ role thì hỏi, không tự gán cả hai.
- “Xe bốn… à thôi bảy chỗ” chỉ giữ giá trị sửa cuối cùng. Nhiều update cùng slot trong một lượt cần validator gộp theo sửa cuối cùng.
- Câu trả lời ngắn “Thanh Xuân”, “cổng sau”, “bảy chỗ” phải đọc target/metadata action trước.
- Khi đang hỏi “cần sửa gì” và khách nói “loại xe”, clear vehicle_type, không yêu cầu bot hỏi lại mục tiêu sửa.
- Địa danh trong câu hỏi route tạm (“nếu ra Bờ Hồ thì bao xa?”) là tham số QA, không tự ghi đè destination của cuốc.
- “Nhà/công ty/chỗ cũ” cần metadata CRM; Extractor không suy ra địa chỉ từ profile rồi coi khách đã nói địa chỉ đó.
- “Đối diện/cách 50 mét/cổng sau” thành driver_note, không sinh lat/lng.

## 5. Thời gian và đồng hồ tham chiếu

Context luôn có turn_received_at ISO có offset và timezone Asia/Ho_Chi_Minh. Validator thuần trong langgraph.md chuẩn hóa trước khi ghi PickupTimeSlot:

| Câu nói/kết quả NLU | Xử lý |
| --- | --- |
| “đi ngay” → now | Hợp lệ. |
| “sau mười lăm phút” → +15m | Neo tại turn_received_at, lưu ISO cụ thể. Lượt xác nhận không cộng thêm 15 phút. |
| “15 giờ 30” → 15:30 | Nếu giờ hôm nay còn phía trước thì dùng hôm nay; nếu đã qua thì hỏi ngày, không tự chuyển sang mai. |
| “mai lúc 8 giờ” | NLU dùng ngày mai so với đồng hồ nhận; trả ISO có offset, validator kiểm tra. |
| “tối”, “tầm chiều”, “mai” không giờ | Chưa đủ rõ → pickup_time needs_clarification; không mặc định now. |
| 25:99, ngày không tồn tại, +0m, thời gian quá khứ, ISO không offset | Không hợp lệ, hỏi làm rõ. |

Nếu khách không nêu thời gian, chỉ mặc định now khi bắt đầu có địa chỉ và pickup_time chưa có raw/giá trị. Nếu khách đã hẹn giờ nhưng hẹn sai hoặc mơ hồ, giữ raw để hỏi lại. TTS đọc ngày/giờ từ ISO đã neo, không phát raw ISO hoặc “+15m”.

## 6. Ma trận 12 tình huống NLU

| TH | Câu khách và context | Output/hợp đồng |
| --- | --- | --- |
| 1 | “Đón 12 Nguyễn Trãi, đổi 7 chỗ, giá bao nhiêu một cây?” | provide_info/change_info/ask_question; pickup và vehicle_type cùng lượt. |
| 2 | “Bốn chỗ… à thôi bảy chỗ” | Chỉ vehicle_type=oto_7_cho. |
| 3 | “12 Cầu Giấy sang viện 108” | Pickup và destination riêng; không bỏ một đầu. |
| 4 | “Thanh Xuân” sau hỏi quận | Pickup augment, component_type=district, action=disambiguation_resolve. |
| 5 | “12 ngách 34/56 ngõ 78 Cầu Giấy” | Value=query đầu ngõ, raw_full đầy đủ, driver_note chi tiết. |
| 6 | “Đối diện cổng bảo tàng” | Value=mốc, direction_modifier/note giữ nguyên. |
| 7 | “Ngã tư A giao B” | is_intersection, street_1/street_2, note góc đứng. |
| 8 | “Cột 9 sảnh E tầng 2 Nội Bài” | Value=POI, sub_poi đầy đủ, raw_full/note; không chỉ trả tên sân bay. |
| 9 | “Qua công ty anh” | is_crm_alias=true, crm_alias_type=work; Map hỏi xác nhận đề xuất. |
| 10 | “Không, bảy chỗ cơ” sau xác nhận nhiều slot | deny + provide/change; chỉ update vehicle_type, giữ slot khác. |
| 11 | Câu nhiễu nhưng “ra ga Hà Nội” rõ | Giữ destination; không bỏ entity vì unclear. |
| 12 | “Cho gặp người thật” | request_operator; Policy chuyển operator_required. |

Ví dụ ngõ sâu, metadata đủ để cả alias và API giữ đúng thông tin:

~~~json
{
  "intents": ["provide_info"],
  "primary_intent": "provide_info",
  "extracted_slots": [{
    "slot_name": "pickup",
    "value": "Ngõ 78 Cầu Giấy",
    "source_text": "số 12 ngách 34/56 ngõ 78 Cầu Giấy",
    "metadata": {
      "operation": "replace",
      "raw_full": "Số 12 ngách 34/56 ngõ 78 Cầu Giấy",
      "head_alley": "Ngõ 78 Cầu Giấy",
      "detail": "Số 12 ngách 34/56",
      "driver_note": "Bản đồ ghim đầu ngõ 78; khách ở số 12 ngách 34/56."
    }
  }],
  "addressed_slots": ["pickup"],
  "clarification_response": null,
  "confidence": 0.94
}
~~~

## 7. Prompt và validator

Prompt yêu cầu: multi-intent, recency, bảo toàn entity, không bịa tọa độ/chính sách, chỉ augment khi action đang hỏi làm rõ, chỉ confirm mục tiêu vừa hỏi, tách thông tin QA khỏi thay đổi cuốc, phân biệt unknown/reject_candidates. Đầu ra JSON theo schema, không Markdown.

Validator runtime:
- Bắt buộc danh sách intents hợp lệ, confidence hữu hạn [0,1], enum/slot/operation đúng, metadata dict sau normalize.
- Loại update không có căn cứ trong phát ngôn hoặc ngữ cảnh; không cho LLM ghi booking_status, coords hay ready.
- Index stopover phải tồn tại; clear/append/replace phải hợp lệ theo slot; primary thuộc intents.
- source_text giữ đoạn gốc; raw_full không được làm mất chi tiết. Dữ liệu tham chiếu từ state chỉ dùng khi augment/CRM đúng contract.
- Timeout và lỗi parse/schema → fallback dưới đây; tối đa retry có giới hạn trong adapter, không vòng gọi LLM vô hạn.

~~~json
{
  "intents": ["unclear"],
  "primary_intent": "unclear",
  "extracted_slots": [],
  "addressed_slots": [],
  "clarification_response": null,
  "confidence": 0.0
}
~~~

## 8. Kiểm thử

Bao phủ 12 tình huống; số bằng chữ, không dấu/dấu câu, câu cụt, self-correction, metadata null, deny chung/deny một slot, confirm kèm optional edit, named slot không replacement, unknown cổng và reject địa điểm, QA chen ngang không addressed, chỉ stopovers và stopovers:i, city-only, thời gian tương đối neo đồng hồ, hẹn quá khứ/ngày mơ hồ.

Test deterministic dùng extractor fake/fixtures; đánh giá NLU thật là suite riêng với model/config cố định, không coi mock pass là model đã hiểu ASR thật.
