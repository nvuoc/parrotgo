# Q&A: FAQ/RAG, TOOL VÀ THÔNG TIN PHIÊN

Schema chung: [architecture.md](./architecture.md). Lưu/nạp RAG: [database.md](./database.md). Node QA luôn chạy sau Reducer theo [langgraph.md](./langgraph.md). Ghép lời thoại: [planner.md](./planner.md).

## 1. Vị trí và trách nhiệm

Luồng: Extractor → Map nếu cần → Reducer áp dụng thông tin mới → QA → Policy → Synthesizer.

Khách vừa đổi destination vừa hỏi thời gian: QA dùng destination mới. Khách chỉ hỏi “nếu ra sân bay thì sao?”: dùng địa danh đó làm tham số truy vấn tạm, không tự đổi cuốc. Tool QA không ghi booking_slots; nếu cần cache route, cache riêng theo toàn bộ waypoint/loại xe, không dùng kết quả tuyến cũ sau edit.

Phản hồi gồm câu trả lời QA + hành động hội thoại tiếp theo. `success=False` vẫn có answer_text được phát ra; thiếu dữ liệu không được làm biến mất câu trả lời.

## 2. Contract

Import `QAResponse` từ `src/core/state.py`:

~~~python
def dispatch_questions(user_text, slots, session_city, timezone):
    """Trả QAResponse, xử lý mọi câu hỏi nhận diện được trong giới hạn 1–2 câu."""

def query_chroma_faq(query, vehicle_type):
    """Trả QAResponse static_faq; kho rỗng không gọi embedding."""

def execute_route_qa_tool(query, slots):
    """Trả QAResponse dynamic_tool; dùng coords đủ/đã xác định, không suy đoán."""

def inspect_session_state(query, slots):
    """Trả QAResponse session_state từ dữ liệu phiên, không gọi RAG."""
~~~

QAResponse luôn gồm category, success, answer_text, source, metadata=dict. Metadata có thể chứa reason, source/version, score, route range, nhưng không đưa JSON kỹ thuật vào lời TTS.

Ví dụ khi kho rỗng:

~~~json
{
  "category": "static_faq",
  "success": false,
  "answer_text": "Dạ hiện tại em chưa có thông tin đã xác nhận về quy định này ạ.",
  "source": "empty_kb",
  "metadata": {"reason": "no_approved_data"}
}
~~~

Không có cờ should_handoff tự động cho mọi câu hỏi chưa trả lời được. Lỗi FAQ/tool QA không làm mất cuốc. Chỉ lỗi định vị thiết yếu hoặc yêu cầu gặp người thật đi luồng handoff trong Policy.

## 3. Nhóm 1 — Static FAQ/RAG

Chủ đề có thể hỗ trợ khi có dữ liệu: giá/km, sức chứa, hành lý, thú cưng, hàng hóa, ghế trẻ em, hút thuốc, hủy/phụ phí. Đây là danh mục câu hỏi, không phải khẳng định chính sách hiện có.

Kho runtime ban đầu rỗng hoặc RAG disabled đều hợp lệ. Không tạo/chèn giá cước mẫu, không tự khẳng định “chở được 6–7 khách”, “miễn phí hủy” hay chính sách thú cưng khi chưa có nguồn đã duyệt.

Retrieval:
1. Nếu disabled/count=0: trả fallback ngay, không cần tải model hay key embedding.
2. Query cùng embedding adapter/manifest với ingestion; metric cosine. Filter approved và vehicle_type phù hợp.
3. Match tốt: đọc canonical_answer của chunk đã duyệt.
4. Match trung bình: có thể tóm tắt tối đa 1–2 câu từ context đã duyệt; chỉ trả khi bằng chứng trực tiếp và nhất quán. Nếu không đủ hoặc mâu thuẫn → fallback.
5. Điểm thấp/không có hit/API embedding lỗi → fallback có reason; không dùng kiến thức model tự trả chính sách công ty.

Ngưỡng 0.82/0.65 chỉ là giá trị thử ban đầu, hiệu chỉnh bằng tập câu hỏi tiếng Việt/ASR và câu ngoài phạm vi. Score không phải xác suất chính sách đúng. Ingestion/upsert/delete và đổi model theo database.md. Nếu vehicle chưa chọn và bảng giá chia theo xe, hỏi ngắn loại xe hoặc trả những mức có nguồn; không suy ra mức của xe khác.

## 4. Nhóm 2 — Tools động

| Tool | Input và điều kiện |
| --- | --- |
| estimate_route_matrix | Origin/destination, ordered stopovers, vehicle_type; các điểm phải có coords hợp lệ. |
| check_point_on_route | Route endpoints và waypoint tạm; báo độ vòng thêm, không tự thêm stopover vào cuốc. |
| search_mega_poi_gate | place_id + role; chỉ trả gate đã duyệt. |
| get_weather_forecast | location + thời gian; adapter weather là tùy chọn, chưa cấu hình trả chưa có thông tin. |

“Từ đây/ra đấy” chỉ tham chiếu pickup/destination khi state có antecedent hợp lệ. Không có coords destination vẫn có thể đủ đặt cuốc tương đối, nhưng chưa đủ gọi route tool; phải nói chưa ước tính được, không dùng tọa độ 0/0.

Nhiều điểm: route theo đúng thứ tự pickup → stopovers → destination. Không bỏ stopover để báo quãng đường ngắn hơn. Vehicle thiếu thì hỏi hoặc báo chưa thể ước tính, không tự chọn xe khác.

### Quãng đường, thời gian và giá

- Chỉ báo route khi khách hỏi. Không chèn km/phút vào confirm_booking hoặc inform_success.
- Không tính tổng tiền cố định; đơn giá/km chỉ trả từ chính sách đã duyệt. Thiếu bảng giá thì nói chưa có thông tin giá.
- Route result phải nêu nguồn và khả năng traffic. Nếu nhà cung cấp không trả live traffic, không gọi đó là thời gian đến chính xác.
- Biên độ ban đầu: km `[floor(km*0.95), ceil(km*1.15)]`; phút `[floor(minutes), ceil(minutes*1.4)]` khi cần đệm giao thông. Đây là heuristic configurable, không cam kết chắc chắn; kiểm tra giá trị hữu hạn/dương trước format.
- Báo bằng văn nói “khoảng tám đến mười cây số”, “khoảng hai mươi lăm đến ba mươi lăm phút”; với chuyến ngắn formatter tránh khoảng vô nghĩa và số lẻ máy móc.
- Khi khách hỏi tổng cước: giải thích cước phụ thuộc đồng hồ/hành trình thực tế theo chính sách có nguồn; không tự nhân range thành số tiền cuối.
- Nếu destination là sân bay/ga/bến xe: chỉ thêm nhắc trừ hao khi **đang trả lời câu hỏi thời gian/hành trình**. Không tự gắn “35–45 phút” khi khách chỉ đặt xe.

Tool lỗi/timeout: trả “Dạ hiện tại em chưa ước tính được quãng đường/thời gian cho tuyến này ạ.”, tiếp tục hành động đặt xe nếu các slot cốt lõi vẫn hợp lệ. Không suy luận bảo trì hay lỗi đường truyền điện thoại từ một lỗi HTTP.

## 5. Nhóm 3 — State Inspector

“Nãy tôi đặt đi đâu?”, “xe gì?”, “hẹn giờ nào?”, “đọc lại chuyến đi” đọc thẳng state mới.

- extracted: “Em đang ghi nhận…”; không tạo thêm yêu cầu xác nhận ngoài BotAction.
- confirmed: đọc giá trị đã xác nhận.
- needs_clarification: nói rõ đang chờ làm rõ, không trình bày candidate chưa chọn như địa chỉ chắc chắn.
- empty: nói chưa có thông tin.
- Tóm tắt gồm bộ 4 và optional đã yêu cầu, giờ theo formatter chuẩn; không bịa booking_id/tài xế.
- “Đọc lại” không thay booking_status/revision và không xác nhận hộ khách.

## 6. Multi-intent và ưu tiên câu trả lời

Ví dụ “Đón 12 Cầu Giấy, bảy chỗ có chở chó không?”:
1. NLU chỉ ghi pickup nếu câu hỏi không chọn bảy chỗ.
2. Reducer cập nhật pickup.
3. QA tìm chính sách có nguồn; kho rỗng nói chưa có thông tin.
4. Synth ghép câu QA với hỏi destination hoặc action phù hợp hiện tại.

Khi đang cancel_pending: QA trả lời phí hủy nếu có nguồn; thiếu nguồn thì fallback; cuối câu nhắc confirm_cancel. Không đổi sang confirm_booking do QA chen ngang. Câu hỏi chen ngang không tăng slot_retry.

## 7. Kiểm thử hỏi đáp

| Test | Kết quả cần đạt |
| --- | --- |
| TC-QA-01: thú cưng | Chỉ trả chính sách fixture đã duyệt trong test; kho runtime rỗng fallback. |
| TC-QA-02: giá/km | Đúng loại xe/nguồn/version; không tính tổng tiền và không tự dùng giá mẫu. |
| TC-QA-03: route | Dùng coords/stopover mới, trả đúng phần khách hỏi. |
| TC-QA-04: weather chưa có adapter | Fallback thông tin, không giả trời mưa/nắng. |
| TC-QA-05: hỏi destination | Đọc state hiện tại, nói rõ nếu còn needs_clarification. |
| TC-QA-06: đọc lại | Đúng thời gian đã neo và optional, không thay state. |
| TC-QA-07: hỏi + sửa slot | Update trước QA, giữ mọi entity hợp lệ. |
| TC-QA-08: kho rỗng/disabled | Không embedding call, answer_text không bị Synth nuốt. |
| TC-QA-09: tool lỗi | Lời fallback có nghĩa, không tự handoff khi cuốc vẫn đủ dữ liệu. |
| TC-QA-10: địa danh QA tạm | Không ghi đè destination/stopovers. |
| TC-QA-11: nhiều câu hỏi | Trả phần có nguồn, chỉ rõ phần thiếu; không mất nhánh. |
| TC-QA-12: cancel_pending + FAQ | Giữ chờ hủy, không tiêu retry, nhắc xác nhận hủy. |
