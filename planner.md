# PLANNER: REDUCER, POLICY VÀ LỜI THOẠI

Schema: [architecture.md](./architecture.md). Pseudocode thực thi duy nhất: [langgraph.md](./langgraph.md). Địa chỉ: [map.md](./map.md). QA: [ask.md](./ask.md).

## 1. Trách nhiệm không chồng chéo

Reducer copy và cập nhật booking_slots, retry, revision, pending_modify_target và ready_to_book. Policy chỉ đọc state đã reduce và chọn action/status/current_focus; không sửa slot tại chỗ. Synthesizer chỉ render lời thoại và tích lũy messages. Persistence commit trước khi CLI/TTS phát lời success.

NLU không xác nhận hộ; Map không tự booked; QA không tự thay slot. Tất cả module import schema duy nhất từ src/core/state.py.

## 2. Vòng đời slot

~~~mermaid
stateDiagram-v2
    [*] --> empty
    empty --> extracted: dữ liệu mới hợp lệ
    empty --> needs_clarification: dữ liệu mới chưa rõ
    extracted --> confirmed: khách xác nhận action còn hiệu lực
    extracted --> needs_clarification: khách từ chối / giá trị không còn hợp lệ
    needs_clarification --> extracted: giải quyết địa chỉ / fallback hợp lệ
    confirmed --> extracted: khách thay đổi hợp lệ
    confirmed --> needs_clarification: sửa đổi chưa giải quyết
    extracted --> empty: khách yêu cầu xóa
    needs_clarification --> empty: khách yêu cầu xóa
    confirmed --> empty: khách yêu cầu xóa
~~~

Geocode thành công/fallback hợp lệ dùng extracted; confirmed chỉ khi khách xác nhận. Raw giữ phát ngôn đầy đủ; note/gate/components không bị mất qua alias hoặc merge.

## 3. Confirm, deny, cancel nhiều lượt

| Action trước | Phản hồi khách | Reducer/Policy |
| --- | --- | --- |
| confirm_slots một địa chỉ đề xuất | Đồng ý, không sửa | Chấp nhận đề xuất nếu candidate còn hợp lệ; nếu mới xác nhận tên đường thì vẫn hỏi mốc pickup, không coi tâm đường là điểm đón. |
| confirm_slots/clarify một slot | “Không”, không thay thế | Invalidate đúng slot; giữ raw làm ngữ cảnh, bỏ tọa độ/candidate bị từ chối. |
| confirm_slots nhiều slot | Deny không rõ mục tiêu | pending_modify_target=True; không xóa toàn bộ. |
| confirm_booking | “Đúng” | Booked chỉ khi revision khớp, dữ liệu vẫn ready, không có edit/cancel/handoff cùng lượt. |
| confirm_booking | “Ừ nhưng đổi xe/giờ/điểm dừng/ghi chú” | Áp dụng edit, tăng revision, đọc lại tóm tắt mới, không booked ngay. |
| confirm_booking | “Không” | pending_modify_target=True; hỏi khách muốn sửa gì. |
| ask_modify_slot | “Loại xe” | Clear vehicle_type và pending; hỏi xe mới. |
| ask_modify_slot | “Đổi bảy chỗ” | Cập nhật xe, clear pending; đủ điều kiện thì đọc tóm tắt mới. |
| ask_modify_slot | Chỉ hỏi FAQ hoặc “ừ” | Giữ pending, tiếp tục hỏi mục tiêu sửa. |
| confirm_cancel | Đồng ý | canceled, inform_canceled, terminal. |
| confirm_cancel | Từ chối | Quay lại thu thập/tóm tắt theo readiness. |
| confirm_cancel | FAQ/xã giao | Trả QA nếu có, giữ cancel_pending, nhắc xác nhận hủy. |

Sửa đổi rõ ràng luôn có ưu tiên so với việc invalidate do deny: “không, bảy chỗ” không được xóa xe bảy chỗ vừa nhận. Named slot không replacement dùng operation=clear. Thay đổi city/optional cũng vô hiệu tóm tắt cũ.

`pending_modify_target` là bool riêng, không nhét vào Dict[str,int] retry. Retry chỉ tăng khi khách thực sự trả lời slot đang clarify, reset khi giải quyết hoặc mở episode địa chỉ mới. Unclear đơn thuần đếm liên tiếp; QA/chat/deny hiểu được reset fallback_count.

## 4. Thứ tự quyết định action

Các bước apply entity/confirm/deny thuộc Reducer, QA đã chạy trước Policy. Không trộn các bước đó thành một cây action thứ hai.

| Ưu tiên | Điều kiện | Action |
| --- | --- | --- |
| 1 | Trạng thái đã canceled/booked/operator_required | inform_canceled/inform_success/human_handoff; bảo toàn terminal. |
| 2 | Khách yêu cầu hỗ trợ, lỗi định vị thiết yếu, fallback >=2, pickup retry >=2, không có điểm fallback an toàn | human_handoff. |
| 3 | Cancel mới hoặc cancel_pending | confirm_cancel. |
| 4 | Chưa biết khách muốn sửa slot nào | general_reply, type=ask_modify_slot. |
| 5 | Yêu cầu đọc lại không kèm edit | Đọc lời trước, giữ action hiệu lực để khách có thể xác nhận câu vừa nhắc. |
| 6 | Đề xuất CRM/fuzzy cần chấp nhận | confirm_slots đúng địa chỉ đề xuất. |
| 7 | Pickup chưa giải quyết, gồm Mega gate | clarify_address pickup, hỏi theo dữ liệu thật. |
| 8 | Destination/stopover đã yêu cầu còn chưa rõ | clarify_address đúng target; fallback đã được Reducer xử lý. |
| 9 | Đủ ready, không pending/lỗi | confirm_booking chứa booking_revision. |
| 10 | Unclear đơn thuần lần đầu hoặc chào hỏi đầu phiên | general_reply ngắn. |
| 11 | Chưa đủ thông tin | ask_slot theo validator: pickup → destination → vehicle_type → pickup_time → optional đã yêu cầu nhưng lỗi. |

Không có “next slot mặc định = pickup” khi tất cả đều có giá trị nhưng thời gian/xe không hợp lệ. Không đọc tóm tắt bằng cờ ready của lượt cũ.

## 5. Ngân hàng lời thoại

Các placeholder lấy từ slot đã kiểm tra; tên xe dùng mapping văn nói. Câu hỏi mở một mục tiêu, tối đa hai ứng viên địa chỉ thực tế. Khi làm rõ, chỉ nói phần cần phân biệt (chi nhánh, quận hoặc phường), không đọc cả chuỗi địa chỉ. Khi đã ghi nhận một điểm rồi hỏi điểm tiếp theo, dùng lời ghi nhận ngắn. Mẫu sau có thể điều chỉnh cách xưng hô, không được thêm thông tin thiếu nguồn.

~~~python
VEHICLE_DISPLAY = {
    "xe_may": "xe máy",
    "oto_4_cho": "ô tô bốn chỗ",
    "oto_7_cho": "ô tô bảy chỗ",
}
RESPONSE_TEMPLATES = {
    "greeting": "Dạ em chào anh/chị. Mình muốn xe đón ở đâu ạ?",
    "ask_pickup": "Dạ mình cho em xin địa chỉ hoặc mốc cụ thể nơi đón ạ?",
    "ask_destination": "Dạ mình muốn đi đến đâu ạ?",
    "ask_vehicle_type": "Dạ mình muốn đi loại xe nào ạ?",
    "ask_pickup_time": "Dạ mình muốn đón vào ngày nào, lúc mấy giờ ạ?",
    "ask_passengers": "Dạ mình đi bao nhiêu người ạ?",
    "clarify_city": "Dạ địa điểm này thuộc tỉnh hoặc thành phố nào ạ?",
    "clarify_ab": "Dạ mình ở {area_a} hay {area_b} ạ?",
    "clarify_narrow": "Dạ mình cho em thêm số nhà hoặc mốc dễ tìm gần đó ạ?",
    "clarify_destination": "Dạ mình cho em biết thêm đường hoặc xã, phường thuộc tỉnh, thành phố nào ạ?",
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
    "persistence_error": "Dạ hiện tại em chưa thể xác nhận việc lưu yêu cầu, mình thử lại sau giúp em ạ.",
}
~~~

`human_handoff` trong CLI là đánh dấu operator_required và kết thúc phiên tự động; không hứa “đã nối máy” khi chưa có tổng đài. `inform_success` chỉ sau transaction commit; không hứa có tài xế hay ETA. `inform_canceled` hủy yêu cầu trong phiên MVP, không giả hủy cuốc đã dispatch ở hệ thống ngoài.

### Render địa chỉ và thời gian

- Ưu tiên raw đầy đủ để đọc đúng số nhà/ngách khách cung cấp; dùng formatted để đọc tên chuẩn và city khi cần.
- Pickup ghim đầu ngõ/mốc lân cận: nói ngắn “bản đồ ghim tại đầu ngõ…” khi khác với nơi khách đứng; giữ note cho dữ liệu cuốc. Không hứa tài xế đi vào ngách.
- Default Mega gate: đọc tên cổng thật từ gate record, không luôn nói “cổng chính”. Ghi rõ đang dùng điểm ghim mặc định để khách kiểm tra trong tóm tắt.
- ISO đã neo được đọc thành giờ/ngày bằng formatter; không gửi ISO, +15m, enum hoặc ký hiệu kỹ thuật cho TTS.
- Summary gồm điểm dừng theo thứ tự, số khách/ghi chú khi đã nêu. Optional rỗng không được tạo câu hỏi.
- Không thêm km/phút hành trình, giá hay chính sách vào tóm tắt nếu khách chưa hỏi.

Ví dụ làm rõ chi nhánh theo từng lượt:

- Khách: “Đi Vincom” → Bot: “Dạ Vincom ở tỉnh hoặc thành phố nào ạ?”
- Khách: “Hà Nội” → Bot: “Dạ mình muốn đến Vincom chi nhánh nào ở Hà Nội ạ?”
- Khách: “Bà Triệu nhé” → Bot ghi nhận chi nhánh và hỏi ngắn địa chỉ đón.

### Repeat và ghép lời

Nếu repeat_request không kèm edit, giữ action trước (target và revision), thêm metadata.repeat_previous=True và đọc lại lời trước. Ví dụ đọc lại confirm_booking vẫn là confirm_booking, nên “đúng” ở lượt sau chốt đúng phiên bản. Nếu vừa edit vừa xin đọc lại thì render tóm tắt hiện tại, không phát nội dung cũ.

`join_speech` ghép QA answer_text kể cả success=False với action, loại khoảng trắng thừa/câu lặp. Không cắt chuỗi cơ học làm rơi câu hỏi hoặc điều kiện quan trọng. Thông thường 1–3 câu; tóm tắt nhiều điểm có thể dài hơn nhưng phải giữ các yêu cầu khách cần xác nhận.

## 6. Guardrails thoại

Không đọc từ ba địa chỉ trở lên. Không tự bịa gate A/B. Không suy diễn “bảo trì”, “đường truyền kém” từ một timeout. Không hứa điều xe/chuyển máy thật trong MVP. Không trả chính sách mẫu khi KB rỗng.

Điểm đến sân bay/ga/bến xe chỉ được thêm nhắc trừ hao khi trả lời câu hỏi thời gian/route theo ask.md. TTS nhận lời thoại thuần; log/Panel/JSON state chỉ ở stderr/kênh debug.

## 7. Ma trận nghiệm thu Planner

| Test | Kịch bản | Kết quả |
| --- | --- | --- |
| TC-PLN-01 | Happy path tuần tự | Hỏi đúng slot thiếu, mặc định now khi khách không hẹn, confirm rồi commit một booking. |
| TC-PLN-02 | One-shot đầy đủ | extracted → confirm_booking, chưa booked ở lượt đầu. |
| TC-PLN-03 | Entity + QA | Cập nhật trước QA, ghép answer + action. |
| TC-PLN-04 | Tự sửa bốn → bảy chỗ | Chỉ giữ xe sau cùng. |
| TC-PLN-05 | Deny + replacement | Giữ slot khác; không invalidate giá trị mới. |
| TC-PLN-06 | Yêu cầu người thật | operator_required, không hứa nối máy. |
| TC-PLN-07 | Unclear hai lượt liên tiếp | Handoff; unclear → QA → unclear thì counter chỉ là 1. |
| TC-PLN-08 | Chưa city, đường trùng | Hỏi city mở, không đoán A/B hai tỉnh. |
| TC-PLN-09 | Ngõ sâu | Raw/note đủ, không hứa xe vào ngách. |
| TC-PLN-10 | Mega pickup unknown | Cổng default đã duyệt có coords khác tâm; thiếu gate → hỗ trợ. |
| TC-PLN-11 | Hỏi km/giá | Range và thông tin có nguồn; không tổng cước. |
| TC-PLN-12 | Cancel → confirm | canceled terminal được Policy bảo toàn. |
| TC-PLN-13 | Destination sân bay | Không tự đọc ETA; cảnh báo khi có câu hỏi thời gian. |
| TC-PLN-14 | API_ERROR + slot success | Lỗi Map không bị che. |
| TC-PLN-15 | Hỏi lại phiên | Đọc state mới nhất, không tự xác nhận. |
| TC-PLN-16 | Confirm + edit core | Đọc lại tóm tắt mới, không booked. |
| TC-PLN-17 | Deny chung → đổi xe → confirm | Cờ pending được xóa; chốt đúng xe mới. |
| TC-PLN-18 | Cancel_pending + QA | Giữ chờ hủy, fallback KB nếu cần. |
| TC-PLN-19 | Deny confirm_slots một pickup | Không chốt địa chỉ bị từ chối. |
| TC-PLN-20 | Metadata null | Normalize dict, không AttributeError. |
| TC-PLN-21 | Destination mơ hồ | Raw “đâu đó” không ready; ward/road + city đã xác định mới được fallback. |
| TC-PLN-22 | Hai QA chen clarify | Retry pickup không tăng. |
| TC-PLN-23 | Giờ 25:99/quá khứ/mơ hồ | Hỏi giờ; không default now hay đọc ISO. |
| TC-PLN-24 | +15m rồi confirm sau hai phút | Giữ giờ tuyệt đối ban đầu, không cộng thêm 15 phút. |
| TC-PLN-25 | Confirm + optional edit | Thêm stopover/note/passengers đều đọc lại summary. |
| TC-PLN-26 | Chỉ có stopovers | Chạy Map, giữ thứ tự, không bỏ điểm lỗi. |
| TC-PLN-27 | Repeat summary → confirm | Giữ action/revision, xác nhận đúng summary vừa nhắc. |
| TC-PLN-28 | CRM/fuzzy bị deny | Chỉ invalidate đề xuất đó; giữ thông tin khác. |
| TC-PLN-29 | Persistence lỗi/replay | Không phát success trước commit; không trùng booking/message/CRM. |
| TC-PLN-30 | Session terminal nhận input mới | Bị chặn, cần UUID mới. |
