**Kết quả bổ sung dữ liệu và tối ưu demo ParrotGo — 08/10/2026**

Luồng làm rõ đã được sửa tiếp để hỏi một thuộc tính ngắn thay vì đọc địa chỉ của các chi nhánh. Kết quả mới: 206 test và 31 kiểm tra live đạt; xem [báo cáo UX](clarification-ux-fix-2026-10-08.md). Các số đo dưới đây thuộc lần kiểm tra trước đó.

Đã cập nhật mã nguồn, nạp dữ liệu địa điểm vào snapshot bền vững và nạp FAQ vào Chroma đang dùng. Cấu hình máy hiện tại là Vietmap live, Gemini live và RAG_ENABLED=true. API key giữ trong .env; các báo cáo không chứa key.

Trường hợp trong ảnh đã được kiểm tra bằng API thật. Khách nói “đi vincom” → bot hỏi tỉnh/thành phố → khách trả lời “Hà Nội” → bot hỏi Bà Triệu hay Royal City. Bot giữ trạng thái đang thu thập thông tin và chỉ ghi nhận chi nhánh sau khi khách chọn. Không tự lấy bản ghi đứng đầu của Vietmap.

| Dữ liệu | Kết quả đã nạp | Nguồn/bằng chứng |
|---|---|---|
| Địa điểm | Thêm Vincom Center Bà Triệu, Vincom Mega Mall Royal City và Vincom Plaza Thủ Đức; tổng 5 địa điểm, 20 alias | [Seed](../data/seed_data/places.json), [snapshot](../data/snapshot_places.json), [response Vietmap](../data/map_live_places_2026-10-08.json) |
| FAQ | Thêm 7 mục: loại xe, thông tin cần cung cấp, ý nghĩa lưu yêu cầu, hẹn giờ, điểm dừng, sửa thông tin và hủy trong phiên | [FAQ seed](../data/seed_data/policy_faqs.json) |
| Vector database | 9 FAQ chunks, 7 approved, 56 vector records; ONNX all-MiniLM-L6-v2, 384 chiều, cosine | [Kiểm tra Chroma sau khi nạp](rag_recall_verification.json) |

Hai FAQ mẫu cũ về thú cưng và ghế trẻ em được đặt approved=false vì chưa có chính sách được xác nhận. Hai cổng mẫu cũ cũng được đặt verified=false; code không dùng chúng làm cổng đón mặc định. Backup Chroma trước thay đổi nằm trong [data/backups](../data/backups/).

Các thay đổi chính đã hoàn tất:

- **Địa điểm và cổng đón:** xử lý địa danh nhiều chi nhánh, tên thành phố và số nhà; giữ candidate để khách chọn; không coi tọa độ của cả đường/phường là địa chỉ chính xác. Chỉ gộp bản ghi cùng chi nhánh mall ở điểm đến, giữ riêng cổng và điểm đón. Vietmap v3 không còn nhận tên thành phố trong tham số focus vốn dành cho tọa độ.
- **Hội thoại:** sửa tự đính chính “xe bảy chỗ à thôi bốn chỗ”, trả lời chỉ có thành phố, hẹn “mai 9 giờ”, thêm điểm dừng và xác nhận hủy. Câu hỏi hướng dẫn không ghi đè hoặc xóa thông tin chuyến. Hỏi FAQ khi đang chờ xác nhận không đọc lại cả tóm tắt; yêu cầu nhắc lại vẫn dựng tóm tắt từ thông tin hiện tại.
- **NLU và lỗi dịch vụ:** gửi đủ ngữ cảnh phiên cho LLM, giới hạn timeout/retry, báo lỗi live để thử lại thay vì âm thầm chuyển sang parser mock. Kiểm tra nghiêm kiểu dữ liệu và thao tác slot; output sửa thông tin thiếu hoặc sai không được dùng để xác nhận chuyến cũ.
- **Lưu giao dịch:** chỉ trả trạng thái booked sau khi SQLite commit thành công. Commit lỗi giữ phiên để xác nhận lại; kiểm thử chứng minh lần thử lại tạo đúng một booking. Mỗi runner dùng đúng DB được truyền vào.
- **RAG:** dùng cùng embedding cho nạp và truy vấn, kiểm tra manifest model/chiều/metric, giữ dữ liệu cũ khi nâng cấp. Bổ sung cách hỏi khác cho hẹn giờ, ghé thêm chỗ và đổi điểm đến. Sửa guard tiếng Việt nhầm “chó” với “chỗ”; giữ ngưỡng tin cậy 0.82/0.65, lọc approved và loại xe.
- **Vận hành demo:** runner hydrate snapshot khi khởi động; upsert địa điểm ghi snapshot atomic. Cấu hình mock/live khai báo rõ trong .env được tôn trọng; thêm timeout và giới hạn số khách theo đội xe demo.

Kết quả kiểm chứng:

| Kiểm tra | Kết quả |
|---|---|
| Toàn bộ pytest | **150 passed**, 39.90 giây |
| Ruff E9,F trên src, scripts, tests | **All checks passed** |
| Seed địa điểm, snapshot địa điểm, FAQ seed | Cả 3 lệnh CLI validate thành công |
| Luồng Gemini + Vietmap thật | **28/28 kiểm tra đạt**, 26.387 giây; [JSON hội thoại](live-demo-check-2026-10-08.json) |
| Chroma persistent sau bổ sung cách hỏi | **17/17 kiểm tra đạt**; [score và nguồn từng câu](rag_recall_verification.json) |

Luồng live đi qua chào hỏi, làm rõ Vincom/thành phố/chi nhánh, điểm đón 12 Cầu Giấy, sửa loại xe, hẹn ngày mai, hỏi lại điểm đến, hỏi loại xe, xác nhận lưu đúng một booking và xác nhận hủy trong một phiên khác. Dùng khách giả và SQLite tạm. 12 lượt hội thoại đo được khoảng 1.43–5.27 giây/lượt trong lần chạy này; đây là số đo một lần trên máy hiện tại. Báo cáo live ghi 41 vector ở thời điểm chạy; kiểm chứng Chroma cuối sau bổ sung cách hỏi ghi đúng 56 vector.

Pytest có hai warning không làm thất bại kiểm thử: deprecated API trong Chroma telemetry và tạo cache của pytest trên Windows. Phạm vi Ruff được kiểm tra là lỗi E9,F; chưa tuyên bố toàn bộ quy tắc style của repository đều sạch. [Bằng chứng tổng hợp](demo-verification-2026-10-08.json).

Chạy demo tại E:\ParrotGo:

~~~~powershell
.\run_demo.ps1
~~~~

Kiểm tra API thật lại khi cần (lệnh này phát sinh request tới nhà cung cấp):

~~~~powershell
.\.venv\Scripts\python.exe scripts/live_demo_check.py
~~~~

Script xuất báo cáo theo ngày chạy và dùng DB tạm. Hướng dẫn nạp lại seed có trong [README](../README.md).

Phạm vi hiện tại vẫn là ghi nhận yêu cầu đặt xe; chưa kết nối điều phối hoặc tài xế. Các cổng sân bay/khu lớn cần dữ liệu cổng thực đã xác minh trước khi demo đón tại cổng cụ thể. Giá cước, thú cưng và ghế trẻ em chưa có chính sách được xác nhận trong RAG.
