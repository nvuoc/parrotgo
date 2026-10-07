# Rà soát rủi ro demo ParrotGo — 07/10/2026

## Kết luận

Có nhiều lỗi có thể làm bot chọn sai địa điểm, mất thông tin khách đã cung cấp, hỏi lặp hoặc đóng phiên trước khi lưu được yêu cầu. Ví dụ “đi vincom” trong ảnh phù hợp với cơ chế chọn kết quả bản đồ đầu tiên và bỏ qua sự mơ hồ. Không có log của phiên trong ảnh nên chưa thể khẳng định đó là request API cụ thể nào.

**P1:** nên sửa trước buổi demo có khách hàng nhập câu tự do. **P2:** làm giảm trải nghiệm hoặc ảnh hưởng các cấu hình/môi trường mở rộng.

Đã đọc các node LangGraph, NLU mock/live, map/cache, validator, QA/template, CLI/config và persistence. Bộ test hiện có: **23 passed in 1.71s**, chạy bằng Python trong .venv với pytest -q -p no:cacheprovider. tests/conftest.py:26 ép mock cho mọi test. Các kiểm chứng bổ sung dùng Python, DB tạm và phản hồi API giả; không gọi dịch vụ live. Các rủi ro chỉ đọc mã được ghi rõ. Mã nguồn ứng dụng chưa được sửa.

## Phát hiện chi tiết

### R01 — P1: Tự chốt kết quả địa điểm đầu tiên, dù tên chung hoặc sai tỉnh

- **Tình huống:** “đi vincom” khi chưa biết chi nhánh; hoặc phiên Hà Nội nhưng kết quả đầu là Milano Vincom Quảng Trị.
- **Bằng chứng:** [vietmap_client.py](E:/ParrotGo/src/services/vietmap_client.py:332) chọn results[0]; dòng 367–379 trả SUCCESS, candidates=[]; có tọa độ thì gán precision exact. Không có kiểm tra độ tương đồng, số ứng viên, loại POI, hay xung đột tỉnh/thành. [map_resolver.py](E:/ParrotGo/src/services/map_resolver.py:199) chuyển thành extracted. [templates.py](E:/ParrotGo/src/services/templates.py:152) đọc “điểm đến ... em đã lưu rồi”.
- **Kiểm chứng:** fake HTTP trả hai địa điểm [Milano Vincom Quảng Trị, Vincom Bà Triệu Hà Nội], session_city=Hà Nội. Resolver lấy Milano, SUCCESS, candidates=[], requires_confirmation=False; destination được validator chấp nhận. Đây là kiểm chứng thuật toán bằng phản hồi giả, không phải kết quả API thực tại thời điểm rà soát.
- **Hệ quả:** khách phải tự phát hiện bot chọn sai; nếu chỉ nghe nhanh tóm tắt, có thể xác nhận chuyến sai địa điểm.
- **Nhánh alias cũng có rủi ro:** map_resolver.py:143 lấy local_matches[0] và bật allow_unverified=True; in_memory_cache.py:348 chỉ sort theo city. Nhiều alias trùng tên hoặc khác tỉnh không được làm rõ; cổng cũng được lookup với allow_unverified=True. Đây là nhận xét từ mã.
- **Đề xuất:** giữ ứng viên; xác minh tên/loại địa điểm và city; tên chuỗi thương hiệu chưa đủ chi nhánh phải hỏi. Khi chưa có tỉnh/thành, hỏi vị trí trước. Một tọa độ trả về không chứng minh đó là điểm khách muốn.

### R02 — P1: Mock và fallback có thể tự thay số nhà, ngõ hoặc cổng

- **Tái hiện:** “đón tôi ở số 99 ngách 5 ngõ 200 Hoàng Hoa Thám” được NLU đổi thành Ngõ 78 Cầu Giấy và note Số 12 ngách 34/56. “cột 3 sảnh A tầng 1 Nội Bài” thành Cột 9 sảnh E tầng 2. “112 Cầu Giấy” geocode thành 12 Cầu Giấy; “115 Lê Văn Lương” thành 15 Lê Văn Lương.
- **Nguồn:** [llm_extractor.py](E:/ParrotGo/src/services/llm_extractor.py:199) dòng 199–225 hardcode detail/head_alley/sub_poi. [vietmap_client.py](E:/ParrotGo/src/services/vietmap_client.py:245) partial substring match cũng lấy địa chỉ fixture. City được cung cấp không ngăn một số fixture trả Hà Nội.
- **Hệ quả:** mock tạo cảm giác bot hiểu tốt nhưng thực tế sửa lời khách thành dữ liệu mẫu; đặc biệt nguy hiểm vì live lỗi cũng rơi về mock.
- **Đề xuất:** chỉ khớp chính xác fixture đã định nghĩa; không khớp số nhà bằng substring. Parse hoặc giữ nguyên detail thật; địa điểm ngoài fixture phải báo chưa giải quyết.

### R03 — P1: Live NLU mất ngữ cảnh hội thoại và âm thầm fallback

- **Bằng chứng:** [extractor.py](E:/ParrotGo/src/core/nodes/extractor.py:20) gửi existing_slots_summary, recent_dialog_turns, session_city, turn_received_at, timezone và last_bot_action. Nhưng [llm_extractor.py](E:/ParrotGo/src/services/llm_extractor.py:317) đọc booking_slots — key không được gửi. Prompt chỉ dùng last target, không dùng loại câu hỏi/metadata, history, city và đồng hồ; schema slot_name live ở dòng 335 thiếu session_city.
- **Kiểm chứng:** capture prompt bằng fake Groq client trong phiên đã có pickup/destination và đang hỏi city. Prompt thực tế chỉ có “Currently asking customer for: destination”, không chứa những thông tin đã biết.
- **Rủi ro suy ra:** câu “Hà Nội” khi đang bổ sung tỉnh/thành có thể bị hiểu là địa chỉ thay thế; lịch “mai 9 giờ” thiếu mốc ngày tham chiếu; sửa điểm dừng/ghi chú thiếu dữ liệu đã có.
- **Lỗi dịch vụ:** dòng 395–400 nuốt exception rồi chạy parser mock, không đánh dấu degraded mode. Lời gọi SDK ở dòng 359–381 không có deadline tổng lượt và giới hạn retry được cấu hình tại đây. Chưa đo độ trễ API thật.
- **Đề xuất:** thống nhất contract context; truyền đủ state/action/time; báo lỗi có cấu trúc, đặt deadline cho lượt và tránh fallback làm phát sinh địa chỉ khác.

### R04 — P1: Câu hỏi kiểm tra chuyến đi ghi đè địa chỉ

- **Tái hiện E2E:** “đón ở 12 Cầu Giấy” → “đi đến Viện 108” → “xe bốn chỗ” → “Nãy tôi đặt đi đâu?”. Destination bị ghi đè thành raw=đâu?, formatted/coords mất, chuyển needs_clarification. Bot trả lời điểm đến là đâu? rồi hỏi làm rõ.
- **Nguồn:** [llm_extractor.py](E:/ParrotGo/src/services/llm_extractor.py:182) từ đi/đến được coi là destination mà không loại đủ từ hỏi. [graph.py](E:/ParrotGo/src/core/graph.py:51) chạy Map/Reducer trước QA nên sửa sai đã xảy ra trước khi bot trả lời.
- **Đề xuất:** tách câu hỏi về state khỏi yêu cầu thêm/sửa chuyến đi; chỉ tạo slot update khi có entity thực. Thêm test đi qua toàn graph, không chỉ gọi QA dispatcher trực tiếp.

### R05 — P1: Mất ngày hẹn hoặc bỏ qua thời gian nói tự nhiên

- **Tái hiện:** tại mốc 07/10/2026 09:00 +07, “10:00 ngày mai” chỉ được trích xuất 10:00 rồi chuẩn hóa thành 07/10, thay vì 08/10. “mai 9 giờ” và “sau 30 phút” không được mock nhận đúng.
- **Nguồn:** [llm_extractor.py](E:/ParrotGo/src/services/llm_extractor.py:131) chỉ hỗ trợ now, vài cách nói 15 phút và HH:MM. [time_utils.py](E:/ParrotGo/src/core/time_utils.py:91) gán HH:MM vào ngày tham chiếu. [state_reducer.py](E:/ParrotGo/src/core/nodes/state_reducer.py:158) mặc định now khi time vẫn empty và đã có địa chỉ.
- **Hệ quả:** bỏ phần thời gian trong một câu chứa địa chỉ có thể khiến bot dùng “đón ngay”; giờ đã qua có thể gây hỏi lại thay vì hiểu ngày mai.
- **Đề xuất:** nhận cả ngày và giờ, thời lượng tổng quát; bảo toàn raw thời gian chưa hiểu để hỏi lại và chặn mặc định now. Thời gian cần được neo một lần theo turn_received_at.

### R06 — P1: Phủ định và tự sửa loại xe chọn sai giá trị cuối

- **Tái hiện:** “cho tôi đi bảy chỗ à thôi bốn chỗ” và “không cần xe bảy chỗ, bốn chỗ thôi” đều trả oto_7_cho.
- **Nguồn:** [llm_extractor.py](E:/ParrotGo/src/services/llm_extractor.py:82) thấy cả bốn và bảy luôn chọn bảy, không theo thứ tự hoặc phạm vi phủ định.
- **Đề xuất:** xử lý giá trị sau cùng được khẳng định; kiểm thử cả 4→7, 7→4, và từ chối một loại để chọn loại khác.

### R07 — P1: Xác nhận hủy hoặc rút lại hủy vẫn hỏi hủy lặp

- **Tái hiện:** sau câu “mình có chắc muốn hủy ...?”, khách nói “đúng rồi hủy xe giúp tôi” → cancel_pending, bot hỏi lại. “không hủy xe nữa” cũng bị nhận là cancel. Câu “đúng rồi, hủy giúp tôi” lại kết thúc được vì không chứa cụm hủy xe.
- **Nguồn:** [llm_extractor.py](E:/ParrotGo/src/services/llm_extractor.py:38) return cancel trước khi xét confirm/deny và ngữ cảnh. [state_reducer.py](E:/ParrotGo/src/core/nodes/state_reducer.py:247) không xử lý confirm nếu intents còn cancel.
- **Đề xuất:** ở confirm_cancel phải phân biệt xác nhận hủy, từ chối hủy và câu hỏi; xử lý phủ định theo cụm, không theo substring.

### R08 — P1: Nạp địa danh thành công nhưng dữ liệu mất khi demo khởi động

- **Tái hiện:** python -m src.cli.data upsert-places --input data/seed_data/places.json báo “2 places processed”; process mới có 0 places.
- **Nguồn:** [in_memory_cache.py](E:/ParrotGo/src/db/in_memory_cache.py:86) dùng SQLite :memory:; [data.py](E:/ParrotGo/src/cli/data.py:38) chỉ nhập vào RAM của process CLI; [runner.py](E:/ParrotGo/src/cli/runner.py:45) không hydrate cache từ seed/snapshot.
- **Hệ quả:** làm theo README vẫn không có alias, cổng mặc định hay đường địa phương khi chạy bot. Có thể rơi vào API hoặc handoff ngoài dự tính. Fixture còn dùng place_id p_noi_bai/fixture_times_city, khác seed noi_bai/times_city, làm lookup cổng bằng ID thất bại ở đường fallback.
- **Đề xuất:** lưu dataset bền vững và hydrate lúc startup; startup cần cho biết số place/gate/FAQ thực có. Kiểm thử nạp và chạy trong hai process riêng.

### R09 — P1: Có cổng đón hợp lệ nhưng vẫn không đạt điều kiện đặt xe

- **Kiểm chứng:** sau khi nạp seed trực tiếp vào process, resolve Times City với sub_poi=Cổng T1 cho gate_resolved=True và tọa độ đúng, nhưng precision=poi và address_ready(pickup)=False.
- **Nguồn:** [map_resolver.py](E:/ParrotGo/src/services/map_resolver.py:151) gán poi; dòng 158–163 gán cổng nhưng không đổi thành anchor. [validators.py](E:/ParrotGo/src/core/validators.py:74) pickup chỉ nhận exact/anchor.
- **Hệ quả:** bot tiếp tục hỏi điểm đón dù khách đã nêu cổng; trường hợp POI nhỏ từ alias cũng thiếu cách trở thành pickup hợp lệ.
- **Đề xuất:** khi cổng/mốc hợp lệ đã được giải quyết, cập nhật precision theo dữ liệu thật; nghiệm thu toàn pipeline alias→gate→ready.

### R10 — P1: Commit thất bại nhưng phiên đã bị đánh dấu booked và terminal

- **Tái hiện:** đi đủ luồng mock, inject PersistenceError ở lượt “Đúng rồi em”. Bot báo chưa thể lưu, DB có 0 booking, nhưng checkpoint có booked và is_terminal=True. Thử lại bị chặn “Phiên đã kết thúc; cần session_id mới”. CLI có thể tự kết thúc.
- **Nguồn:** [state_reducer.py](E:/ParrotGo/src/core/nodes/state_reducer.py:283) gán booked, [response_synthesizer.py](E:/ParrotGo/src/core/nodes/response_synthesizer.py:47) gán terminal trước persistence; [runner.py](E:/ParrotGo/src/cli/runner.py:109) chỉ trả thông báo lỗi, không phục hồi state. [session_init.py](E:/ParrotGo/src/core/nodes/session_init.py:11) chặn lượt mới.
- **Đề xuất:** trạng thái booked/terminal chỉ được công bố sau commit hoặc phải phục hồi checkpoint khi commit lỗi; khách thử lại được mà không tạo booking trùng.

### R11 — P1: Validator JSON chưa chặn kiểu dữ liệu làm graph crash

- **Kiểm chứng:** validate_extractor_output nhận slot vehicle_type có value={type: oto_4_cho}; reducer sau đó TypeError vì dict không thể dùng để kiểm tra membership của set.
- **Nguồn:** [validators.py](E:/ParrotGo/src/core/validators.py:235) không giới hạn tên slot và kiểu value/metadata theo schema; [state_reducer.py](E:/ParrotGo/src/core/nodes/state_reducer.py:139) dùng val in VEHICLES. [runner.py](E:/ParrotGo/src/cli/runner.py:112) ném lại lỗi graph ngoài PersistenceError.
- **Rủi ro:** JSON hợp lệ về cú pháp từ LLM chưa đảm bảo đúng kiểu; một phản hồi sai contract có thể làm demo thoát.
- **Đề xuất:** schema runtime riêng cho từng slot/operation, enum tên slot và target stopover; dữ liệu sai trả kết quả làm rõ có kiểm soát.

### R12 — P1: .env đặt mock vẫn tự chuyển live nếu còn API key

- **Kiểm chứng:** Settings với .env tạm chứa MAP_MODE=mock, LLM_MODE=mock và API key giả vẫn thành MAP_MODE=live và LLM_MODE=groq.
- **Nguồn:** [config.py](E:/ParrotGo/src/config.py:44) chỉ xét key mode có trong os.environ, bỏ qua mode đã khai báo ở .env.
- **Hệ quả:** buổi demo offline có thể phụ thuộc mạng/API ngoài dự tính; kết quả test mock không phản ánh mode demo thực.
- **Đề xuất:** tôn trọng mode được khai báo ở mọi nguồn cấu hình; in tên mode/provider an toàn lúc startup, không in API key.

## Rủi ro P2 và trải nghiệm

1. **Không kiểm tra số khách với loại xe.** Đã chạy reducer/policy với 5 khách và xe máy: ready=True, bot đọc xác nhận chuyến. [validators.py](E:/ParrotGo/src/core/validators.py:106) chỉ kiểm số người dương. Cần giới hạn theo chính sách sức chứa được duyệt hoặc hỏi chọn xe/đặt nhiều xe.
2. **Câu một lượt có cả xe và destination bị bỏ địa chỉ trong mock.** “Cho tôi đi Vincom bằng xe bốn chỗ” có vehicle update nên nhánh destination tại llm_extractor.py:182 bị bỏ. Cần trích xuất độc lập các entity.
3. **Câu hỏi làm rõ không hiển thị đủ lựa chọn.** templates.py:186–190 chỉ dùng city để phân biệt A/B; hai chi nhánh cùng thành phố có thể thành “Hà Nội hay Hà Nội”. Câu xác nhận stopovers dùng {} thay vì address của điểm dừng tại dòng 201–203; đã tái hiện “dừng chân tại chưa có địa chỉ” dù slot có formatted.
4. **Keyword QA không đồng nhất.** NLU mock llm_extractor.py:53 thiếu “mấy km”, “thời tiết”, “đón ở đâu”, trong khi dispatcher có logic tương ứng. Khách có thể bị bỏ qua câu hỏi và nhận lại câu thu thập thông tin.
5. **Một lỗi map dừng cả phiên.** action_policy.py:44–60 chuyển operator_required ngay API_ERROR; template chỉ nói cần nhân viên, CLI kết thúc. Chưa có chuyển máy thật; nên có retry có giới hạn/cách tiếp tục hoặc đường liên hệ rõ trong demo.
6. **FAQ không lọc loại xe.** chroma_client.py:120 nhận vehicle_type nhưng where tại dòng 133 chỉ approved=True. Có thể trả policy của loại xe khác nếu KB có nhiều nhóm. Chưa kiểm chứng bằng KB thực. embedding_adapter.py:28 trả [], cấu hình embedding chưa nối đầy đủ với Chroma.
7. **Hai SessionRunner có DB riêng dùng chung global manager.** Đã tạo A rồi B, lượt của A lỗi Session not found vì constructor B đè manager. runner.py:45–46; persistence.py:10; sqlite_manager.py:459–473. Ít ảnh hưởng CLI một phiên, ảnh hưởng harness/server nhiều phiên.
8. **Ước tính quãng đường bỏ điểm dừng.** qa_dispatcher.py:113–137 dùng đường chim bay pickup→destination ×1.3, không cộng stopovers. Là suy luận từ mã, chưa kiểm chứng tuyến thực; cần nói rõ phạm vi ước tính hoặc dùng route đầy đủ.

## Thứ tự xử lý đề xuất

1. Sửa chọn địa điểm và độ chính xác, chặn dữ liệu mock bịa và trạng thái terminal trước commit (R01/R02/R10).
2. Hoàn thiện context/schema NLU, phân biệt hỏi–sửa–hủy và lịch hẹn (R03–R07/R11).
3. Sửa startup cache, gate precision và mode cấu hình (R08/R09/R12).
4. Bổ sung validation sức chứa, câu thoại lựa chọn, QA và deadline tổng lượt.

## Bộ câu nghiệm thu trước demo

| Tình huống | Kết quả cần đạt |
| --- | --- |
| chào → đi vincom | Hỏi tỉnh/thành hoặc chi nhánh khi thiếu; không tự chọn một địa điểm không liên quan. |
| Session Hà Nội, API trả Vincom Quảng Trị đầu tiên | Không chốt sai tỉnh; giữ ứng viên hợp lệ và hỏi làm rõ. |
| 112 Cầu Giấy / 115 Lê Văn Lương | Giữ nguyên số nhà; không đổi thành 12/15. |
| Ngách/cổng Nội Bài khác fixture | Giữ đúng detail khách nói hoặc hỏi lại. |
| Vincom + xe bốn chỗ cùng câu | Nhận cả destination và vehicle. |
| Bảy chỗ à thôi bốn chỗ | Xe cuối cùng là bốn chỗ. |
| Không cần xe bảy chỗ, bốn chỗ thôi | Chọn bốn chỗ và giữ các slot khác. |
| Confirm_cancel → đúng rồi hủy xe giúp tôi | canceled, không hỏi hủy lặp. |
| Confirm_cancel → không hủy xe nữa | Tiếp tục phiên đặt xe. |
| Nãy tôi đặt đi đâu? | Trả destination hiện có, booking_slots không bị thay đổi. |
| 10:00 ngày mai / mai 9 giờ / sau 30 phút | Đúng ngày/giờ theo mốc lượt hoặc hỏi lại; không mặc định now. |
| Nhập seed ở process A, chạy bot ở process B | Alias/gate/street vẫn sử dụng được. |
| Times City, Cổng T1 | Pickup đạt ready khi tọa độ cổng hợp lệ. |
| 5 khách, xe máy | Phát hiện mâu thuẫn sức chứa trước tóm tắt cuối. |
| LLM trả vehicle_type dạng object | Không crash; hỏi lại có kiểm soát. |
| Commit SQLite lỗi rồi thử lại | Không terminal khi chưa lưu; retry an toàn và không booking trùng. |
| .env mock cùng API key | Mode vẫn mock, không gọi API. |
| Timeout LLM/map | Có deadline, phản hồi rõ và cách tiếp tục hữu ích. |

## Giới hạn kiểm chứng

Chưa gọi API Vietmap/Gemini/Groq thực; chưa có transcript và response API của ảnh; chưa nghiệm thu audio ASR/TTS vì dự án hiện là MVP CLI. Phát hiện live chọn top/context đã kiểm chứng bằng client giả, còn chất lượng kết quả thực, độ trễ mạng và policy KB cần buổi kiểm thử riêng. Các lỗi mock/fallback vẫn quan trọng vì suite ép mock và live có nhánh fallback sang mock.
