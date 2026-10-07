# KẾ HOẠCH TRIỂN KHAI MVP CLI PARROTGO

Đây là kế hoạch triển khai mã nguồn tiếp theo, chưa phải các file/chức năng đã tồn tại. Bộ đặc tả dùng chung: [architecture.md](./architecture.md), [langgraph.md](./langgraph.md), [extractor.md](./extractor.md), [map.md](./map.md), [ask.md](./ask.md), [planner.md](./planner.md), [database.md](./database.md).

## 1. Mục tiêu và phạm vi chốt

Xây core hội thoại nhận nguyên văn ASR và trả lời bot thuần để truyền thẳng TTS, chạy thử qua CLI. Hoàn chỉnh cung cấp thông tin, sửa đổi, hỏi đáp, xác nhận, hủy và đánh dấu cần nhân viên hỗ trợ.

Bao gồm:
- LangGraph 8 node, 3 conditional edge, một invoke mỗi phát ngôn.
- SQLite lịch sử nghiệp vụ 6 bảng; cache địa lý in-memory; RAG Chroma có thể rỗng/disabled.
- Extractor structured output có validator và fallback; Map mock/live tách rõ.
- Reducer, Policy chỉ đọc slot, templates TTS sạch, DAL transaction/idempotency.
- Công cụ validate/upsert/delete dữ liệu FAQ và địa danh để nạp khi người dùng có dữ liệu.
- CLI thuần và debug Rich tùy chọn; kiểm thử deterministic offline và đánh giá adapter thật riêng.

Giai đoạn sau: ASR/TTS/audio streaming thật, WebRTC/LiveKit, SIP/PBX, dashboard/mobile, dispatch tài xế và chuyển cuộc gọi thật, persistent checkpoint/resume sau restart.

`booked` MVP là yêu cầu đã được khách xác nhận và lưu SQLite. CLI không hứa đã điều xe/tài xế đang tới. Không đợi có RAG/địa danh thật mới xây core; không bịa data để lấp kho rỗng.

## 2. Cấu trúc mã nguồn dự kiến

~~~text
ParrotGo/
├── data/
│   ├── parrotgo.db
│   ├── chroma_data/
│   └── seed_data/                    # Runtime có thể dùng [] lúc đầu
│       ├── places.json
│       ├── poi_aliases.json
│       ├── mega_poi_gates.json
│       ├── city_streets.json
│       └── policy_faqs.json
├── src/
│   ├── config.py
│   ├── core/
│   │   ├── state.py                  # Schema duy nhất
│   │   ├── validators.py
│   │   ├── time_utils.py
│   │   ├── graph.py
│   │   ├── edges.py
│   │   └── nodes/
│   │       ├── session_init.py
│   │       ├── extractor.py
│   │       ├── map_service.py
│   │       ├── state_reducer.py
│   │       ├── qa_dispatcher.py
│   │       ├── action_policy.py
│   │       ├── response_synthesizer.py
│   │       └── persistence.py
│   ├── db/
│   │   ├── sqlite_manager.py
│   │   ├── in_memory_cache.py
│   │   └── chroma_client.py
│   ├── services/
│   │   ├── llm_extractor.py
│   │   ├── vietmap_client.py
│   │   ├── map_resolver.py
│   │   ├── qa_dispatcher.py
│   │   ├── embedding_adapter.py
│   │   └── templates.py
│   └── cli/
│       ├── runner.py
│       └── data.py                   # Lệnh ingestion/validation
├── tests/
│   ├── fixtures/                    # Mock địa lý/FAQ, không tự nạp runtime
│   ├── conftest.py
│   ├── test_db_layer.py
│   ├── test_extractor.py
│   ├── test_map_service.py
│   ├── test_qa.py
│   ├── test_planner.py
│   └── test_e2e_cli.py
├── pyproject.toml                   # Dependencies và tool config
├── dependency lock                # Pin bộ phiên bản đã kiểm thử
├── .env.example
└── README.md
~~~

Mỗi package Python có __init__.py khi cần. Không import từ tên file Markdown như `from architecture import ...`.

## 3. Các giai đoạn triển khai

### Giai đoạn 1 — schema, validator và storage

1. Viết state.py từ architecture.md, default factories cho dict/list mới mỗi phiên.
2. Runtime validator cho NLU, Map, seed và state; xử lý metadata thiếu/null.
3. Helper thời gian nhận đồng hồ inject được: ISO offset, relative neo một lần, giờ mơ hồ/đã qua hỏi lại. Cài tzdata cho Windows.
4. SQLite DDL, schema version, foreign_keys, db_start_session và db_persist_turn một transaction.
5. Cache địa lý với connection giữ suốt tiến trình, FK place/gate, lookup theo city.
6. Chroma client disabled/empty-safe và manifest embedding; chưa cần model khi không có dữ liệu.
7. Ingestion theo ID ổn định, validate trước ghi, upsert/delete riêng; fixtures tách runtime.

**Hoàn thành khi:** tạo session/lưu turn/rollback/replay đúng, kho địa lý/RAG rỗng không chặn khởi động, ingestion sai không làm mất kho hợp lệ.

### Giai đoạn 2 — adapter và mock

1. Extractor fake deterministic cho tests, LLM thật qua interface chung, timeout/validator/fallback có giới hạn.
2. Vietmap mock fixture cho 17 tình huống; địa chỉ lạ → NOT_FOUND. Live adapter validate schema/coords và không tự fallback mock.
3. Map resolver xử lý raw/augment/CRM/alias/fuzzy/gate trước khi trả đủ AddressSlot.
4. EmbeddingAdapter cấu hình rõ model/manifest, thống nhất ingestion/query; phiên bản phụ thuộc theo lock.
5. QA dispatcher: state inspector, RAG có nguồn, route theo ordered waypoints; weather chưa tích hợp fallback.

**Hoàn thành khi:** alias không mất note/sub_poi/components, Mega gate dùng tọa độ gate thật trong dataset, city-only requery và stopovers đều đi Map.

### Giai đoạn 3 — reducer và lời thoại

1. Merge slot và invalidate theo mục tiêu; mọi edit kể cả optional làm mất hiệu lực summary.
2. pending_modify_target riêng, xóa khi khách nêu slot/update; deny đơn slot không chốt dữ liệu cũ.
3. Retry chỉ đếm addressed slot; unclear counter thực sự liên tiếp.
4. Mega fallback chỉ khi có gate đã duyệt; destination tương đối cần tên/precision/city có căn cứ.
5. ready tính lại sau mọi thay đổi; giờ hết hạn/lỗi và optional đã yêu cầu chưa rõ đều được xử lý.
6. Policy không mutate slot, bảo toàn cancel/booked/terminal, repeat giữ action còn hiệu lực.
7. Template thuần TTS: giờ/ngày bằng văn nói, summary chứa optional, không ETA/giá/tài xế thiếu nguồn.

**Hoàn thành khi:** 30 kịch bản Planner trong planner.md pass bằng fixtures; không có luồng “không → sửa xe → ừ” bị kẹt hoặc confirm+edit tạo cuốc ngay.

### Giai đoạn 4 — LangGraph và persistence

Lắp đúng 8 node/3 edge theo langgraph.md. QA sau Reducer. Dùng InMemorySaver và thread_id=session_id cho MVP; không tuyên bố resume dở dang sau restart.

Synth tạo text nhưng adapter chỉ phát sau persistence commit. Lỗi persistence phải có outcome lookup theo session/turn và đường resume không nhân đôi turn. Không dùng cùng phát ngôn lỗi làm một lượt mới để “retry”.

**Hoàn thành khi:** chạy nhiều lượt giữ state, tách hai phiên cùng SĐT, terminal bị chặn, rollback/replay không tạo booking/CRM trùng.

### Giai đoạn 5 — CLI và nghiệm thu

Hợp đồng adapter dự kiến:

~~~python
def start_session(phone, name, city=None):
    """UUID mới, metadata + db_start_session trước invoke đầu."""

def handle_turn(session_id, utterance, received_at):
    """Giữ utterance gốc, ghi received_at một lần, invoke graph tuần tự.
    Chỉ trả final_response_text sau commit; adapter TTS dùng trực tiếp chuỗi này."""
~~~

- Mở phiên bằng tham số CLI hoặc prompt metadata riêng trên stderr.
- Nhận từng dòng như phát ngôn ASR hoàn chỉnh; dòng trống bỏ qua, EOF kết thúc CLI; không coi slash-command là nội dung đặt xe.
- Lượt đầu truyền metadata + input; lượt sau chỉ input + received_at, dùng thread_id cố định.
- stdout chỉ lời bot; prompt/input log/debug Rich/JSON state ở stderr. Chế độ debug không sửa final_response_text.
- Terminal booked/canceled/operator_required kết thúc vòng; phiên mới có UUID mới.
- Lỗi persistence không phát lời success đã synth, báo câu chưa xác nhận lưu và xử lý outcome theo DAL.
- Đo latency theo từng node và tổng lượt. Template/local lookup có mục tiêu nhanh; không cam kết toàn lượt <150ms khi gọi LLM/HTTP/embedding.

**Hoàn thành khi:** E2E CLI đọc văn bản ASR không dấu câu/số chữ, tạo/hủy cuốc, hỏi QA rỗng, và xuất chuỗi có thể đưa thẳng cho TTS.

## 4. Giao diện nạp dữ liệu dự kiến

Các lệnh sau là yêu cầu thiết kế CLI, chỉ chạy được sau khi viết src.cli.data:

~~~powershell
python -m src.cli.data validate-places --input .\du-lieu-dia-danh.json
python -m src.cli.data upsert-places --input .\du-lieu-dia-danh.json
python -m src.cli.data validate-faq --input .\chinh-sach.json
python -m src.cli.data upsert-faq --input .\chinh-sach.json
~~~

Có lệnh delete riêng theo ID, xuất snapshot địa lý runtime, kiểm tra manifest RAG và thống kê số bản ghi đã nạp/bị lỗi. Nạp/reload giữa các lượt, không đổi cache đang phục vụ một turn. Không tự xóa bản ghi thiếu trong batch upsert.

Địa danh: place_id/gate_id/alias ổn định, city/source/verified, tọa độ đã kiểm tra. FAQ: chunk ID, source/version/approved, canonical_answer. Shape đầy đủ trong database.md.

## 5. Cấu hình dự kiến

~~~env
DEFAULT_SESSION_CITY=
SESSION_TIMEZONE=Asia/Ho_Chi_Minh
MAP_MODE=mock
VIETMAP_API_KEY=
LLM_MODE=mock
RAG_ENABLED=false
EMBEDDING_PROVIDER=
EMBEDDING_MODEL=
EMBEDDING_DIMENSIONS=
PERSISTENT_DB_PATH=data/parrotgo.db
CHROMA_DATA_DIR=data/chroma_data
DEBUG=false
~~~

DEFAULT_SESSION_CITY trống → None, không hardcode Hà Nội trong init/DDL. LLM mock và Map mock phục vụ offline/test; live yêu cầu cấu hình adapter thật và keys tương ứng. RAG false hoặc kho rỗng không cần model/key embedding; khi nạp data phải cấu hình manifest phù hợp.

Dependencies dự kiến: langgraph, typing_extensions, pydantic/pydantic-settings, chromadb, client HTTP phù hợp, rapidfuzz, rich, tzdata và pytest; SDK LLM/embedding theo provider chọn khi triển khai. Pin phiên bản sau smoke test, không giả định API mọi phiên bản giống nhau.

## 6. Nghiệm thu và giới hạn

Bộ kiểm thử gồm validator/unit và nhiều lượt E2E có ý nghĩa, không chỉ assert lại mã implementation:
- Happy path, one-shot, confirm+edit core/optional, deny chung/đơn slot, cancel chen QA, repeat rồi confirm.
- Metadata null, time invalid/expired/relative, city None/city-only/liên tỉnh.
- Alias/CRM/fuzzy, cổng Mega có/không default, raw/note nguyên vẹn, destination tương đối/mơ hồ, stopover đầy đủ.
- Kho RAG/địa lý rỗng, ingestion/upsert/manifest, QA fail vẫn có thoại.
- Transaction rollback, replay idempotent, terminal, hai session cùng SĐT, stdout thuần thoại.

Mock pass chứng minh logic điều phối; chưa chứng minh chất lượng NLU/live geocoding/RAG. Sau khi có dữ liệu và chọn adapter thật, chạy suite đánh giá riêng với câu ASR thực, địa danh/chính sách đã duyệt và smoke test integration. Không đưa fixtures chưa kiểm chứng vào runtime để coi là đã nghiệm thu vận hành thật.
