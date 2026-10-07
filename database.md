# LƯU TRỮ VÀ NẠP DỮ LIỆU PARROTGO

Contract state: [architecture.md](./architecture.md). Map: [map.md](./map.md). RAG: [ask.md](./ask.md). Thứ tự commit: [langgraph.md](./langgraph.md).

## 1. Ba tầng độc lập

| Tầng | Mục đích | Khi chưa có dữ liệu |
| --- | --- | --- |
| SQLite persistent, `data/parrotgo.db` | Khách hàng, phiên, message, booking, favorites, audit | Tạo schema trước khi nhận phiên. |
| SQLite in-memory | Địa điểm, alias, cổng/sảnh, danh mục đường | Kho rỗng hợp lệ; miss → thử Map live hoặc NOT_FOUND trong mock. |
| Chroma, `data/chroma_data` | Chunks FAQ/chính sách đã duyệt | Trả câu chưa có thông tin; không yêu cầu embedding/API khi kho rỗng. |

Dữ liệu fixture nằm dưới `tests/fixtures/`, không tự nạp vào kho runtime. Kho runtime ban đầu có thể là các danh sách rỗng. Số lượng FAQ phụ thuộc dữ liệu thật, không phải điều kiện khởi động.

## 2. SQLite persistent: 6 bảng

Mọi connection bật `PRAGMA foreign_keys = ON`, dùng SQL tham số và transaction có rollback. DDL dưới đây dành cho database mới. Khi triển khai thay schema đã có, cần migration có version và backup, không trông chờ `CREATE TABLE IF NOT EXISTS` tự thêm cột/ràng buộc.

~~~sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    phone TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    total_trips INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL REFERENCES customers(phone) ON DELETE CASCADE,
    label TEXT NOT NULL,
    address_key TEXT NOT NULL,
    address_json TEXT NOT NULL,
    frequency INTEGER NOT NULL DEFAULT 1,
    last_used TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(phone, label, address_key)
);

CREATE TABLE IF NOT EXISTS call_sessions (
    session_id TEXT PRIMARY KEY,
    customer_phone TEXT NOT NULL REFERENCES customers(phone),
    session_city TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    booking_status TEXT NOT NULL DEFAULT 'collecting'
        CHECK (booking_status IN ('collecting', 'ready_to_book', 'confirming',
               'booked', 'cancel_pending', 'canceled', 'operator_required')),
    fallback_count INTEGER NOT NULL DEFAULT 0 CHECK (fallback_count >= 0),
    started_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS bookings (
    booking_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE REFERENCES call_sessions(session_id),
    customer_phone TEXT NOT NULL REFERENCES customers(phone),
    customer_name TEXT NOT NULL,
    vehicle_type TEXT NOT NULL CHECK (vehicle_type IN ('xe_may', 'oto_4_cho', 'oto_7_cho')),
    pickup_time TEXT NOT NULL,
    slots_json TEXT NOT NULL,
    booking_revision INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    dispatch_status TEXT NOT NULL DEFAULT 'not_integrated'
        CHECK (dispatch_status IN ('not_integrated', 'pending', 'accepted', 'failed')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES call_sessions(session_id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL CHECK (turn_index > 0),
    turn_received_at TEXT NOT NULL,
    user_input TEXT NOT NULL,
    bot_response TEXT NOT NULL,
    intents_json TEXT NOT NULL,
    action_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, turn_index)
);

CREATE TABLE IF NOT EXISTS audit_trail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES call_sessions(session_id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL,
    rule_triggered TEXT NOT NULL,
    action_selected TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    latency_ms REAL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, turn_index)
);

CREATE INDEX IF NOT EXISTS idx_fav_phone ON customer_favorites(phone);
CREATE INDEX IF NOT EXISTS idx_session_phone ON call_sessions(customer_phone);
CREATE INDEX IF NOT EXISTS idx_booking_phone ON bookings(customer_phone);
~~~

`slots_json` lưu đầy đủ BookingSlots: raw, formatted, components, tọa độ, driver note, place/gate ID, giờ đã chuẩn hóa và giờ gốc, điểm dừng theo thứ tự. Không mất metadata do flatten một phần địa chỉ. `pickup_time` cột riêng là `now` hoặc ISO có offset; không lưu `+15m`/`15:30` chưa neo.

`bookings.status=confirmed` là xác nhận của khách. `dispatch_status=not_integrated` trong MVP; không suy ra đã có tài xế. Timestamp ứng dụng lưu ISO có offset; started/ended dùng đồng hồ adapter.

## 3. DAL và transaction

~~~python
def db_start_session(session_id, phone, name, session_city, timezone, started_at):
    """Một transaction: upsert customers rồi insert call_sessions.
    Gọi trước invoke lượt đầu. Session đã có phải khớp metadata, không mở lại terminal."""

def db_get_customer_crm_profile(phone):
    """Trả profile + địa chỉ home/work/frequent đã lưu; không có thì None."""

def db_persist_turn(state):
    """Một transaction cho toàn bộ lượt; trả {"booking_id": str | None} sau commit."""

def db_get_turn_outcome(session_id, turn_index):
    """Tra outcome đã commit theo key khi gặp lỗi persistence/ack; không tạo lượt mới."""
~~~

`db_persist_turn` thực hiện:

1. Xác minh session tồn tại, thuộc đúng khách và turn index hợp lệ. Tạo hash canonical từ payload nghiệp vụ của lượt, không gồm latency hoặc timestamp ghi DB.
2. Nếu `(session_id, turn_index)` đã tồn tại: cùng payload hash → trả outcome cũ; hash khác → lỗi xung đột, không ghi đè.
3. Insert session_messages và audit_trail; update session_city/status/fallback/ended_at.
4. Nếu state booked: insert booking dùng UUID đầy đủ, `UNIQUE(session_id)` là lớp bảo vệ cuối. Conflict booking phải kiểm tra payload cuốc đã lưu khớp; không trả thành công cho dữ liệu khác.
5. Chỉ khi booking **mới được insert**: tăng total_trips và upsert favorites bằng address_key ổn định. Không tự gán địa chỉ thường đi thành home/work nếu khách chưa chỉ định.
6. Commit tất cả hoặc rollback tất cả. Không mỗi helper mở connection/commit riêng.

Không có lookup “kiểm tra chưa tồn tại” rồi insert ngoài transaction. Synchronous CLI xử lý tuần tự; DAL vẫn cần uniqueness để an toàn khi replay. Khi DB lỗi, adapter chưa phát lời success; chi tiết khôi phục lượt trong langgraph.md. SQLite lịch sử nghiệp vụ không thay thế LangGraph checkpoint.

## 4. Danh mục địa lý: schema và khóa ổn định

Một connection in-memory được giữ suốt tiến trình, inject vào service. Nếu dùng URI shared-memory, giữ ít nhất một connection mở; `sqlite3.connect(":memory:")` riêng trong mỗi hàm sẽ tạo kho khác nhau.

~~~sql
PRAGMA foreign_keys = ON;

CREATE TABLE places (
    place_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    formatted_address TEXT NOT NULL,
    city TEXT NOT NULL,
    lat REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lng REAL NOT NULL CHECK (lng BETWEEN -180 AND 180),
    poi_type TEXT NOT NULL,
    is_mega_poi INTEGER NOT NULL CHECK (is_mega_poi IN (0, 1)),
    components_json TEXT NOT NULL,
    driver_note TEXT,
    source TEXT NOT NULL,
    verified INTEGER NOT NULL CHECK (verified IN (0, 1))
);

CREATE TABLE local_poi_alias (
    alias_key TEXT NOT NULL,
    place_id TEXT NOT NULL REFERENCES places(place_id) ON DELETE CASCADE,
    PRIMARY KEY(alias_key, place_id)
);

CREATE TABLE mega_poi_gates (
    gate_id TEXT PRIMARY KEY,
    place_id TEXT NOT NULL REFERENCES places(place_id) ON DELETE CASCADE,
    gate_code TEXT NOT NULL,
    gate_key TEXT NOT NULL,
    lat REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lng REAL NOT NULL CHECK (lng BETWEEN -180 AND 180),
    is_default_pickup INTEGER NOT NULL DEFAULT 0 CHECK (is_default_pickup IN (0, 1)),
    is_default_dropoff INTEGER NOT NULL DEFAULT 0 CHECK (is_default_dropoff IN (0, 1)),
    driver_instruction TEXT NOT NULL,
    source TEXT NOT NULL,
    verified INTEGER NOT NULL CHECK (verified IN (0, 1)),
    UNIQUE(place_id, gate_key)
);
CREATE UNIQUE INDEX unique_default_pickup ON mega_poi_gates(place_id)
    WHERE is_default_pickup = 1;
CREATE UNIQUE INDEX unique_default_dropoff ON mega_poi_gates(place_id)
    WHERE is_default_dropoff = 1;

CREATE TABLE city_streets (
    street_id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    street_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    source TEXT NOT NULL,
    verified INTEGER NOT NULL CHECK (verified IN (0, 1))
);
CREATE INDEX idx_streets_city ON city_streets(city, normalized_name);
~~~

Alias cho phép trùng tên giữa nhiều địa điểm. Lookup trả danh sách ứng viên, lọc/xếp hạng theo city; không lấy hàng đầu tiên tùy ý. Mega POI và gates join bằng place_id, không dùng tên hiển thị như “Times City” vs “Vinhomes Times City”. `is_mega_poi` là nguồn chính; adapter dữ liệu cũ hiểu cả poi_type `mega_poi/airport/mall/hospital/station/complex`.

## 5. File dữ liệu và nạp địa danh sau này

Các file JSON runtime: `places.json`, `poi_aliases.json`, `mega_poi_gates.json`, `city_streets.json`. Mỗi file là list; thiếu file được coi rỗng khi khởi động, nhưng file có JSON/schema sai phải báo lỗi dữ liệu, không âm thầm bỏ qua.

Ví dụ **fixture tổng hợp**, chỉ để minh họa shape; không phải tọa độ/cổng đã kiểm chứng ngoài thực tế:

~~~json
{
  "places": [{
    "place_id": "fixture_times_city",
    "canonical_name": "Vinhomes Times City",
    "formatted_address": "Times City, Hà Nội",
    "city": "Hà Nội",
    "lat": 21.0,
    "lng": 105.8,
    "poi_type": "mega_poi",
    "is_mega_poi": true,
    "components": {"province_city": "Hà Nội"},
    "driver_note": null,
    "source": "test_fixture",
    "verified": false
  }],
  "aliases": [{
    "alias_key": "times city",
    "place_id": "fixture_times_city"
  }],
  "gates": [{
    "gate_id": "fixture_times_gate",
    "place_id": "fixture_times_city",
    "gate_code": "Cổng kiểm thử",
    "lat": 21.001,
    "lng": 105.801,
    "is_default_pickup": true,
    "is_default_dropoff": true,
    "driver_instruction": "Liên hệ khách tại cổng kiểm thử.",
    "source": "test_fixture",
    "verified": false
  }]
}
~~~

`gate_key` và alias_key chuẩn hóa được tính bằng cùng một helper Unicode/casefold/bỏ dấu trên bản sao; không làm mất raw. Chỉ mock/test được đọc fixture chưa verified, qua flag rõ ràng; live chỉ tra hàng verified.

Hợp đồng ingestion:

- `validate_place_dataset(dataset)` kiểm tra ID, nguồn, city, tọa độ hữu hạn, alias/gate FK, gate trùng và duy nhất default theo role.
- `upsert_place_dataset(dataset)` thực hiện một transaction, theo ID ổn định; lỗi bất kỳ rollback, giữ kho cũ. Ingest cả place trước alias/gate.
- `delete_place_ids(ids)` là thao tác riêng, không coi hàng vắng trong batch upsert là yêu cầu xóa.
- `export_place_dataset()` xuất snapshot để lưu lại file runtime. CLI import xác thực toàn bộ rồi ghi snapshot bằng temp-file + atomic replace và reload cache giữa hai lượt. Cache RAM không tự bền vững.
- `in_memory_lookup_poi_alias(raw_phrase, city)` trả list ứng viên đầy đủ metadata.
- `in_memory_lookup_sub_poi(place_id, gate_code)` trả cổng đã duyệt hoặc None.
- `in_memory_lookup_default_gate(place_id, role)` trả cổng default đã duyệt hoặc None, không dùng tọa độ tâm place thay thế.
- `in_memory_fuzzy_street_match(street_input, city)` trả ứng viên để khách xác nhận; kho rỗng trả list rỗng.

Tên/tỉnh/thành hành chính trong ví dụ là fixture; ingestion phải dùng bộ dữ liệu thực tế người dùng cung cấp, không hardcode danh mục hành chính từ tài liệu.

## 6. Chroma: cấu hình embedding thống nhất

Ứng dụng dùng một `EmbeddingAdapter` cấu hình rõ provider/model/revision/dimensions/preprocessing. Ingestion và truy vấn dùng **cùng adapter**. Không ngầm dùng embedding mặc định của Chroma.

Ví dụ client local; `embedding_function` là instance đã cấu hình của adapter Chroma, không phải tên model dạng chuỗi:

~~~python
collection = client.get_or_create_collection(
    name=collection_name,
    embedding_function=embedding_function,
    configuration={"hnsw": {"space": "cosine"}},
    metadata={"embedding_manifest": manifest_json},
)
~~~

Cấu hình cosine và embedding function theo [Chroma Configure Collections](https://docs.trychroma.com/docs/collections/configure). Với collection cũ phải đọc/so sánh manifest và cấu hình thực tế; `get_or_create_collection` không phải migration và có thể bỏ qua metadata mới khi kho đã tồn tại, theo [Chroma Python Client](https://docs.trychroma.com/reference/python/client).

Đổi model, dimension hoặc preprocessing → tạo collection phiên bản mới và re-embed dữ liệu đã duyệt, kiểm thử rồi chuyển collection active. Không trộn hai embedding space dù cùng dimension. Pin phiên bản chromadb đã kiểm thử trong dependency lock.

Khi RAG disabled hoặc kho rỗng: không cần khởi tạo embedding model/tải model/gọi API để trả fallback. Đến lúc có dữ liệu hoặc kho không rỗng mới yêu cầu config embedding phù hợp.

## 7. Contract FAQ chunks và ingestion

~~~json
{
  "id": "faq_policy_example",
  "document": "Câu hỏi và nội dung chính sách đã được chủ dữ liệu duyệt.",
  "metadata": {
    "category": "policy",
    "sub_intent": "example",
    "vehicle_type": "all",
    "canonical_answer": "Câu trả lời dạng văn nói đã duyệt.",
    "source": "ten_nguon",
    "version": "v1",
    "approved": true
  }
}
~~~

Ví dụ không cung cấp giá/sức chứa/chính sách thật. Chunks chứa dữ liệu kiểm thử dùng collection test riêng. Metadata lưu các giá trị scalar Chroma hỗ trợ; không đưa list/dict tùy ý. Chính sách khác theo loại xe dùng chunk riêng hoặc metadata vehicle_type; không suy diễn từ xe khác.

- `chroma_upsert_faq_policies(chunks)`: validate toàn batch, ID ổn định, approved/source/version/canonical_answer, upsert theo batch giới hạn client. Nạp lại cùng ID cập nhật, không tạo bản sao.
- Upsert là bổ sung/cập nhật, không xóa ID vắng mặt. `chroma_delete_faq_ids(ids)` xử lý xóa riêng.
- MVP nạp/reload giữa hai lượt, không ingestion đồng thời với query. Chroma và SQLite không có transaction chung: nếu batch Chroma lỗi một phần, báo thất bại và retry cùng IDs; không báo thành công toàn batch.
- `chroma_search_faq_policy(query, vehicle_type)`: trước tiên kiểm tra enabled/count; rỗng trả QAResponse source empty_kb. Filter approved và vehicle_type phù hợp, top-k hữu hạn, tính score=1-distance khi metric cosine.
- Ngưỡng high/low là config, ban đầu có thể thử 0.82/0.65 nhưng phải hiệu chỉnh bằng câu hỏi tiếng Việt/ASR có đáp án và câu ngoài phạm vi. Không gọi score là xác suất hay đảm bảo chính xác chỉ vì chọn một model.
- Thiếu kết quả, không đủ bằng chứng, mâu thuẫn nguồn hoặc lỗi embedding → fallback có source/reason; không bịa chính sách và không làm mất booking_slots.

## 8. Kiểm thử lưu trữ bắt buộc

Tạo session rồi lưu lượt với foreign_keys bật; rollback khi lỗi audit/booking; replay cùng lượt chỉ có một message/audit/booking và một lần tăng CRM; payload replay khác phải lỗi; city None được giữ. Ingest alias trùng city khác phải trả ứng viên đúng; gate thiếu/sai FK/default trùng phải lỗi và không đổi kho cũ. RAG rỗng không gọi embedding; upsert cùng ID không nhân bản; manifest/model lệch bị phát hiện.
