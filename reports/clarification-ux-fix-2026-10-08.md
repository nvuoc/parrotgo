**Sửa trải nghiệm làm rõ địa điểm — 08/10/2026**

Lỗi trước đó nằm ở renderer: bot đọc cả tên chi nhánh, phường, quận và thành phố của từng ứng viên. Map còn dùng loại câu hỏi A/B cho nhiều hơn hai ứng viên, trong khi lời thoại chỉ đọc hai địa điểm đầu. Cách này vừa dài vừa tạo ấn tượng rằng khách chỉ được chọn trong hai địa điểm đó.

Yêu cầu gốc: [map.md:14](../map.md#1-ranh-giới-và-nguyên-tắc) giới hạn tối đa hai lựa chọn; [planner.md:73](../planner.md#5-ngân-hàng-lời-thoại) yêu cầu câu hỏi mở một mục tiêu. Quy tắc đã được ghi rõ thêm trong hai tài liệu và triển khai trong mã.

Luồng sau sửa, từ lần kiểm tra live cuối:

- Khách: “đi vincom” → Bot: “Dạ địa điểm này thuộc tỉnh hoặc thành phố nào ạ?”
- Khách: “Hà Nội” → Bot: “Dạ mình muốn đến vincom chi nhánh nào ở Hà Nội ạ?”
- Khách: “ở Bà Triệu nhé” → Bot: “Dạ điểm đến Vincom Center Bà Triệu 191 Phố Bà Triệu em đã ghi nhận rồi ạ. Mình đang ở địa chỉ nào để xe đến đón ạ?”

Những phần đã sửa:

- Tên chuỗi nhiều chi nhánh và đã biết thành phố: hỏi mở một chi nhánh, giữ các ứng viên trong state.
- Hai đường trùng tên: chỉ dùng quận/phường khác nhau để phân biệt. Hơn hai ứng viên: hỏi một thuộc tính, giữ toàn bộ ứng viên.
- Ghi nhận địa điểm trước câu hỏi tiếp theo và hỏi cổng dùng tên ngắn. Xác nhận cuối vẫn đọc thông tin cần kiểm tra.
- Câu đáp “ở Bà Triệu”, “Bà Triệu nhé” cập nhật đúng địa chỉ đang được làm rõ; giữ nguyên điểm đón và các thông tin xe/giờ/số khách nói cùng câu. Chi nhánh ngoài seed vẫn có thể được tra cứu.
- Chỉ nhận lựa chọn theo thứ tự khi bot thực sự đã đọc A/B. Không chọn theo thứ tự ứng viên ẩn.
- Không gợi ý nhà/công ty bằng một địa điểm thường đến có label khác khi CRM thiếu địa chỉ.
- Xin nhắc lại chuyến đọc tóm tắt một lần; FAQ chưa đủ tin cậy trả câu thông báo ngắn để không tạo thêm một câu hỏi khi ghép với hỏi slot.
- Script kiểm tra live dừng sau hai lỗi NLU liên tiếp, tránh tiếp tục gọi API vô ích.

Kiểm chứng:

- Toàn bộ suite: **206 passed**, 41.42 giây; [kết quả test và lint](clarification-ux-tests-2026-10-08.json).
- Riêng renderer có **16 ca UX** trong [test_clarification_ux.py](../tests/test_clarification_ux.py): một câu hỏi, độ dài hợp lý, không đọc chuỗi hành chính, không liệt kê nhiều ứng viên hoặc làm mất dữ liệu.
- Sau thay đổi cuối về lời thoại FAQ, regression tập trung đạt **1 passed**; lint E9,F cuối trên src/scripts/tests đạt.
- Gemini + Vietmap thật: **31/31 kiểm tra đạt**, 18.997 giây; [transcript cuối](live-clarification-ux-2026-10-08.json). Các lượt trả lời thành phố/chi nhánh rõ ràng dùng guard ngữ cảnh cục bộ; các lượt cần LLM vẫn gọi Gemini thật.

Lần chạy live đầu đã xác nhận câu làm rõ ngắn và hiểu đúng chi nhánh, nhưng Gemini trả provider_error ở các bước sau nên toàn luồng thất bại. Đã giữ [bằng chứng lần lỗi](live-clarification-ux-2026-10-08-first-attempt.json); [một request chẩn đoán sau đó](gemini-ux-diagnostic-2026-10-08.json) trả đúng xe bốn chỗ và lần chạy lại toàn luồng đạt 31 kiểm tra. Điều này cho thấy demo vẫn phụ thuộc tính sẵn sàng của API; không dùng kết quả mock để che lỗi live.

Các file chính: [templates.py](../src/services/templates.py), [map_resolver.py](../src/services/map_resolver.py), [vietmap_client.py](../src/services/vietmap_client.py), [llm_extractor.py](../src/services/llm_extractor.py), [response_synthesizer.py](../src/core/nodes/response_synthesizer.py), [chroma_client.py](../src/db/chroma_client.py).
