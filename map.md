# MAP SERVICE: ĐỊA CHỈ, ĐỊA DANH VÀ ĐIỂM ĐÓN

Schema chuẩn: [architecture.md](./architecture.md). NLU: [extractor.md](./extractor.md). Dữ liệu địa lý: [database.md](./database.md). Luồng node: [langgraph.md](./langgraph.md).

## 1. Ranh giới và nguyên tắc

Map nhận văn bản được Extractor bóc tách và ngữ cảnh địa lý, trả AddressSlot + tool_status. Không tự quyết định booked hay phát câu thoại. Reducer áp dụng kết quả; Policy chọn câu hỏi.

Không có GPS thiết bị/Caller ID hay bản đồ ngầm trong CLI. Tên/SĐT là metadata mở phiên. Địa chỉ chưa xác định không được gán tọa độ giả. Độ chính xác cần đủ để tìm được điểm đón, không phải lời hứa GPS tuyệt đối.

- Pickup: địa chỉ cụ thể hoặc mốc cố định + ghi chú; Mega POI cần cổng/sảnh đã xác định.
- Destination: có thể tương đối nếu Map xác định được tên đường/POI/xã-phường và tỉnh/thành. Câu “đâu đó”, “về quê”, “chỗ kia” chưa có antecedent không hợp lệ.
- Stopover: nếu khách chủ động yêu cầu thì cần coords và ghi chú rõ, giữ thứ tự; không tự bỏ điểm chưa tìm được.
- Tối đa hai lựa chọn địa chỉ trong lời thoại. Nhiều hơn hai → hỏi một thuộc tính để thu hẹp.
- Kho địa danh rỗng hợp lệ. Miss local → live Map nếu bật; mock không biết → NOT_FOUND.
- Không ép khách nói số nhà điểm đến đã xác định tương đối.

## 2. Contract dịch vụ thống nhất

~~~python
def resolve_address_update(update, target, session_city, existing_slots, crm_profile):
    """Trả {"slot": AddressSlot, "tool_status": MapToolStatus}.
    target: pickup, destination hoặc stopovers:i."""

def prepare_address_updates(state, city):
    """Chuẩn bị địa chỉ mới, bổ sung và requery do city thay đổi.
    Trả (list[(target, update)], stopover_operation)."""

def resolve_vietmap_address(raw_address, role, address_city, metadata):
    """Adapter nhà cung cấp trả kết quả đã chuẩn hóa, không trả JSON API thẳng vào state."""
~~~

`AddressSlot` luôn đủ trường trong architecture.md. `components` và `candidates` được giữ xuyên lượt. Status geocode/fallback hợp lệ là `extracted`; `confirmed` chỉ sau khách xác nhận.

| Tool status | Slot status | Ý nghĩa |
| --- | --- | --- |
| SUCCESS | extracted | Đủ dữ liệu cho role, có thể vẫn chờ xác nhận đề xuất CRM/fuzzy. |
| AMBIGUOUS | needs_clarification | Nhiều ứng viên hoặc điểm chưa đủ hẹp; giữ candidates. |
| NOT_FOUND | needs_clarification | Không tìm thấy/không có dữ liệu đủ dùng; không phải lỗi mạng. |
| API_ERROR | needs_clarification | Live timeout/HTTP lỗi/payload hỏng; lỗi định vị thiết yếu → hỗ trợ thủ công. |

Tổng hợp nhiều địa chỉ theo `API_ERROR > NOT_FOUND > AMBIGUOUS > SUCCESS`. Không che lỗi pickup bằng success destination. Adapter nhà cung cấp phải validate coords hữu hạn và ngữ nghĩa độ chính xác; có lat/lng không đồng nghĩa pickup hợp lệ.

## 3. Pipeline mọi địa chỉ, kể cả alias

1. **Giữ nguyên văn:** lưu raw bằng metadata.raw_full nếu có, nếu không dùng source/address đầy đủ. Chuỗi query riêng lấy head_alley/anchor/value. Không mất số ngách, từ chỉ hướng, sub_poi.
2. **Hợp nhất câu trả lời bổ sung:** chỉ khi metadata.operation=augment hoặc action=disambiguation_resolve. Ghép district/ward/city/gate vào địa chỉ đang chờ, giữ candidates/notes. `replace` là địa chỉ mới, không nối địa chỉ cũ. `clear` do Reducer xử lý.
3. **City:** ưu tiên địa lý được nói rõ trong địa chỉ. Nếu pickup thiếu city, dùng session_city; cả hai thiếu và kết quả không duy nhất thì hỏi tỉnh/thành, không đoán Hà Nội. Destination khác tỉnh không bị lọc mất theo pickup.
4. **CRM:** nếu is_crm_alias, tìm home/work/frequent theo profile. Có đề xuất hợp lệ → extracted + requires_confirmation=True. Không có → hỏi địa chỉ, không gửi literal “work_address” lên geocoder.
5. **Local alias:** lookup theo normalized key + city, có thể nhiều match. Copy đầy đủ place_id, components, poi_type/is_mega_poi, note và formatted. Không return sớm trước bước gate/metadata.
6. **Fuzzy/Vietmap:** match tên chuẩn nhưng phải giữ giá trị khách nói. Fuzzy correction là đề xuất cần xác nhận; nếu pickup chỉ là tên đường vẫn cần mốc cụ thể sau khi chấp nhận tên.
7. **Sub-POI/gate:** xử lý cho cả kết quả alias và API theo mục 5. Gate join bằng place_id ổn định, không canonical_name.
8. **Note:** nối note khách/driver_note, chỉ dẫn địa điểm, note đầu ngõ/số lân cận và gate; loại trùng, không dùng toán tử `or` làm rơi phần còn lại. Tọa độ query có thể là mốc nhưng raw vẫn đầy đủ.
9. Trả slot hoàn chỉnh và tool_status. Nếu geocoder không có components thì chỉ bổ sung city từ ngữ cảnh đã xác định; không tự bịa ward/district.

Thay session_city → re-resolve pickup hiện có nếu phụ thuộc vùng cũ, cùng các địa chỉ tương ứng; xóa kết quả hành trình cũ. Pickup ở tỉnh khác nói rõ có thể cập nhật vùng điểm đón qua slot session_city. City riêng của destination không tự đổi vùng pickup.

## 4. Ma trận 17 tình huống trong 8 nhóm

| TH | Nhóm | Tình huống/ví dụ | Xử lý |
| --- | --- | --- | --- |
| 1 | 1 | “Đón ở Hà Nội/phường X” | Pickup hỏi mốc cụ thể, không dùng tâm vùng. Destination cần tối thiểu xã/phường + tỉnh/thành đã xác định. |
| 2 | 1 | “Đường Nguyễn Trãi”, địa danh trùng tên | Chưa biết city → hỏi city mở. Có city → lọc, hai ứng viên hỏi A/B, nhiều hơn hỏi ward/district. Pickup vẫn cần số nhà/mốc. |
| 3 | 2 | “15 Lê Văn Lương” | Khớp đúng số nhà/đường/city thì lấy ứng viên đúng; không hỏi số 15 hay 17 chỉ vì API có lân cận. |
| 4 | 3 | “Kengnam”, “Lăng Bác” | Tra alias theo city; đọc tên chuẩn để khách kiểm tra trong tóm tắt. |
| 5 | 4 | “Đối diện cổng bảo tàng” | Geocode mốc, note hướng đứng; không tính tọa độ ảo bên kia đường. |
| 6 | 6 | “Công ty anh”, “chỗ cũ” | Tra CRM, hỏi confirm_slots trước dùng. Deny chỉ invalidate địa chỉ đó. |
| 7 | 4 | “Ngã tư A giao B” | Resolve giao lộ/mốc đã xác định, note góc đứng; không giả định nhà cung cấp có endpoint giao lộ. |
| 8 | 5 | Mega POI nói chung | Phân biệt role pickup/destination/stopover trước chọn gate. |
| 9 | 8 | Khách đang di chuyển/không biết vị trí | Hỏi một mốc cố định; không dừng được/không resolve được → human_handoff. |
| 10 | 3 | “Tôn Thất Thuyếp” | Fuzzy trong city, đề xuất tên chuẩn để khách xác nhận; không âm thầm đổi. |
| 11 | 5 | “Đi Times City” | Dùng cổng dropoff đã duyệt nếu có; nếu chưa có có thể nhận POI tương đối + city, không giả cờ default. |
| 12 | 5 | “Đón Times City, không biết tòa” | Hỏi cổng/mốc một lần; unknown → lookup default pickup thật, không có thì hỗ trợ. |
| 13 | 2 | Ngách sâu “12 ngách 34/56 ngõ 78” | Query đầu ngõ, raw giữ toàn bộ, note bản đồ ghim đầu ngõ. Không hứa xe vào ngách. |
| 14 | 7 | Đọc cả đón và đến | Resolve cả hai cùng lượt; chỉ song song khi không phụ thuộc city/pickup vừa resolve. |
| 15 | 7 | “Số 5… à thôi số 8” | Extractor lấy sửa đổi sau cùng; Map không resolve/lưu cả hai làm điểm đón. |
| 16 | 5 | “Cột 9 sảnh E tầng 2 Nội Bài” | Lookup sub-POI đã duyệt, thay coords bằng gate cụ thể, giữ raw/note. |
| 17 | 8 | Geocoder 0 kết quả | Một câu cứu hộ mốc lớn; vẫn thất bại/không biết → hỗ trợ, không dùng raw bất kỳ để chốt. |

### Nhóm 1: city và làm rõ

Lọc thành phố/địa lý là bước trước xếp hạng. Bias từ pickup/CRM chỉ giúp xếp hạng, không loại địa chỉ destination xa mà khách đã nói rõ. Không hardcode bán kính 15 km làm rào cản chuyến liên tỉnh.

Với tên chuỗi nhiều chi nhánh như Vincom, ưu tiên một câu hỏi mở về chi nhánh trong thành phố đã biết; giữ toàn bộ candidates để xử lý câu trả lời tiếp theo. Không đọc danh sách địa chỉ đầy đủ hoặc ngụ ý chỉ có hai lựa chọn khi dữ liệu còn nhiều hơn.

Câu A/B lấy thuộc tính khác nhau của hai candidates thực tế. “Thanh Xuân” trả lời cho “Nguyễn Trãi ở đâu” là augment; geocoder nhận địa chỉ tổng hợp, không geocode riêng tên quận rồi dùng tâm quận làm điểm đón.

### Nhóm 2: độ khớp và ghim mốc

Top-1 dominance có thể thử threshold 0.85 và gap 0.20 trên thang điểm chuẩn hóa; phải kiểm thử/hiệu chỉnh với fixture và nguồn thực tế. Chỉ đủ điểm chuỗi chưa cho phép bỏ qua mismatch số nhà, city hay khác role.

Số nhà 148A nhưng chỉ có 148: chỉ dùng làm anchor nếu xác định cùng tuyến/khu vực và khách kiểm tra được qua tóm tắt/note. Không tùy ý chọn số gần nhất khác đường. Bot đọc raw 148A và nói rõ bản đồ ghim mốc lân cận khi cần.

### Nhóm 3–4: tên địa danh, hướng và giao lộ

Fuzzy threshold là tham số thử nghiệm, không xác suất đúng. Kho đường rỗng thì bỏ bước fuzzy. Alias nhiều địa điểm phải làm rõ; không coi key không dấu là đảm bảo duy nhất.

Không tự cộng/trừ lat/lng để suy ra “đối diện”, “cách 50 m”. Chỉ giữ tọa độ mốc cố định và note. Nếu mốc còn mơ hồ thì pickup vẫn cần làm rõ.

## 5. Mega POI và fallback đúng tọa độ

Nhận diện từ field is_mega_poi. Adapter dữ liệu cũ thiếu cờ suy ra từ poi_type `mega_poi/airport/mall/hospital/station/complex`. Với nguồn đã biên tập có cờ explicit false, tôn trọng đánh giá của dữ liệu; không coi mọi bệnh viện/tòa nhà là khu rộng.

### Pickup

- Khách nêu cổng/sảnh: lookup `in_memory_lookup_sub_poi(place_id, sub_poi)`. Chỉ chốt gate_resolved khi có cổng xác định và coords hợp lệ. Tên gate còn thiếu/không khớp không đồng nghĩa tâm POI là gate.
- Chưa có gate: slot needs_clarification, clarification_kind=mega_poi_gate. Bot hỏi mở một câu về cổng/tòa/mốc, không dựng “sảnh A/B”.
- Khách thực sự trả lời không biết hoặc bổ sung vẫn không giải quyết được: Reducer lookup default gate theo place_id và role pickup. Nếu có bản ghi đã duyệt, thay coords/formatted/gate_id, đặt gate_resolved/default_point_used true, precision anchor; giữ raw và thêm driver_instruction/cảnh báo.
- Không có cổng default đã duyệt hoặc khách từ chối địa điểm/cổng: không giả default thành công; handoff_reason=missing_safe_pickup/pickup_unresolved. Không hỏi cổng lặp lại.
- FAQ/xã giao chen ngang không được xem là phản hồi không biết và không tiêu lượt gate.

### Destination

Nếu có default dropoff đã duyệt thì dùng thật và đặt default_point_used true với note/coords/gate_id. Nếu không có, nhận POI tương đối đã xác định + city; giữ default_point_used false, note trao đổi chi tiết khi gần tới. Không bắt khách chọn sảnh.

### Stopover

Cần resolve điểm dừng có coords theo yêu cầu. Mega POI stopover dùng gate đã duyệt; thiếu gate thì hỏi làm rõ điểm dừng đã yêu cầu, không tự dùng tâm khu rộng. Mặc định role stopover không fallback bằng cổng pickup nếu dữ liệu không phù hợp mục đích dừng.

## 6. Đếm retry và fallback destination

`slot_retry_counts` đếm **phản hồi chưa giải quyết được slot**, không đếm mọi lượt hội thoại. Extractor phải trả addressed_slots; reducer tăng khi bot vừa clarify và khách thực sự đáp lại slot đó.

| Role/kịch bản | Giới hạn |
| --- | --- |
| Pickup mơ hồ thông thường | Tối đa 2 phản hồi làm rõ chưa giải quyết; đạt 2 → hỗ trợ. Địa chỉ thay thế rõ ràng mở episode mới. |
| Pickup không tìm thấy/đang di chuyển | Một phản hồi cứu hộ mốc cố định; vẫn không xác định → hỗ trợ. |
| Mega pickup | Một phản hồi về gate; fallback gate đã duyệt hoặc hỗ trợ. |
| Destination | Một phản hồi làm rõ. Nếu đã có đường/POI/xã-phường + city được xác định → chấp nhận tương đối; không có → hỗ trợ. |
| Stopover khách yêu cầu | Một phản hồi làm rõ không thành → hỗ trợ; không âm thầm bỏ. |

Destination fallback chỉ nằm trong Reducer, trước tính ready. Khách từ chối candidate (“không phải nơi đó”) phải invalidate candidate; không dùng nguyên candidate để fallback. Câu “không biết số nhà” có thể chấp nhận ward/road đã xác định, khác với từ chối địa điểm.

## 7. Mock offline và live adapter

Chế độ `MAP_MODE=mock|live` rõ ràng. Không tự mock khi live lỗi hoặc thiếu key. Live thiếu config báo lỗi khởi động; mock không cần key.

Fixture gồm: địa chỉ đúng, trùng city, ngõ sâu, anchor, alias, gate có/không default, city khác, stopovers, NOT_FOUND và API_ERROR. Tọa độ fixture phục vụ kiểm thử, không cam kết vị trí/cổng thực tế. Bản ghi không có trong mock trả NOT_FOUND.

Khi xây live adapter, chọn endpoint/schema theo tài liệu Vietmap của phiên bản dùng, thêm timeout và retry giới hạn cho request đọc. Kết quả route phải có cờ khả năng traffic; không tuyên bố có traffic thời gian thực nếu response/API không cung cấp.

## 8. Kiểm thử Map bắt buộc

17 tình huống trên; metadata null; raw_full/driver_note/sub_poi đi qua alias không mất; Times City poi_type=mega_poi; default coords khác tâm place; thiếu gate không có default_point_used; alias trùng ở hai city; augment district giữ address gốc; city-only requery pending address; destination liên tỉnh không bị city pickup loại; chỉ stopovers vẫn đi Map; API_ERROR không bị che bởi slot success.
