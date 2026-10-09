# CƠ SỞ TRI THỨC — ĐẶT XE QUA TỔNG ĐÀI XANH SM

**Loại dữ liệu:** Quy định và quy trình nghiệp vụ giả lập phục vụ Voice Chatbot.

## 1. Quy định chung về dịch vụ đặt xe qua tổng đài

- [GEN-01] Khách hàng có thể gọi đến tổng đài Xanh SM để yêu cầu đặt xe mà không cần sử dụng ứng dụng trên điện thoại.
- [GEN-02] Dịch vụ đặt xe qua tổng đài Xanh SM hỗ trợ khách hàng 24 giờ mỗi ngày, bao gồm cả thứ Bảy, Chủ nhật và ngày lễ.
- [GEN-03] Khách hàng không cần tạo tài khoản Xanh SM để đặt xe qua tổng đài.
- [GEN-04] Khách hàng cần cung cấp thông tin cần thiết để tổng đài tiếp nhận và điều phối xe phù hợp.
- [GEN-05] Việc tiếp nhận yêu cầu đặt xe không đồng nghĩa với việc đã có tài xế nhận chuyến.
- [GEN-06] Yêu cầu đặt xe chỉ được xác nhận thành công sau khi hệ thống tìm được tài xế và xác nhận chuyến đi.
- [GEN-07] Tổng đài không thu phí riêng cho việc tạo yêu cầu đặt xe. Khách hàng chỉ thanh toán cước chuyến đi và những khoản phụ phí hợp lệ nếu có.

## 2. Quy định về các loại xe

- [CAR-01] Khi đặt xe qua tổng đài Xanh SM, khách hàng chỉ có thể lựa chọn hai loại xe là ô tô 4 chỗ và ô tô 7 chỗ.
- [CAR-02] Tổng đài Xanh SM không hỗ trợ đặt xe máy hoặc các loại phương tiện khác ngoài ô tô 4 chỗ và ô tô 7 chỗ.
- [CAR-03] Nếu khách hàng muốn lựa chọn thêm các loại dịch vụ xe khác, hãy hướng dẫn khách hàng sử dụng ứng dụng Xanh SM trên điện thoại.
- [CAR-04] Xe ô tô 4 chỗ có thể phục vụ tối đa 4 hành khách, không tính tài xế.
- [CAR-05] Xe ô tô 7 chỗ có thể phục vụ tối đa 6 hành khách, không tính tài xế.
- [CAR-06] Khách hàng có thể yêu cầu xe 7 chỗ ngay cả khi số lượng hành khách ít hơn 6 người.
- [CAR-07] Khách hàng không thể lựa chọn chính xác biển số xe, màu xe hoặc tài xế cụ thể khi đặt xe qua tổng đài.
- [CAR-08] Nếu loại xe khách hàng yêu cầu không còn xe trống, tổng đài có thể đề xuất loại xe khác nhưng chỉ được thay đổi sau khi khách hàng đồng ý.

## 3. Thông tin cần cung cấp khi đặt xe

- [BOOK-01] Khi đặt xe qua tổng đài, khách hàng cần cung cấp địa chỉ đón chi tiết, điểm đến ở mức vùng tối thiểu theo DEST-01, thời gian đón, loại xe và số điện thoại liên hệ.
- [BOOK-02] Khách hàng nên cung cấp số lượng người đi để tổng đài tư vấn loại xe có sức chứa phù hợp.
- [BOOK-03] Khách hàng không bắt buộc cung cấp số nhà, cổng hoặc địa chỉ điểm đến chính xác ngay khi tạo yêu cầu, nhưng cần xác định được tối thiểu xã/phường hiện hành hoặc đơn vị cấp huyện trước sáp nhập, kèm tỉnh/thành phố.
- [BOOK-04] Nếu chưa biết địa chỉ điểm đến chính xác, khách hàng có thể thông báo vùng tối thiểu nói trên và trao đổi chi tiết với tài xế trước khi khởi hành. Chỉ tên tỉnh/thành phố hoặc chưa có vùng dự kiến thì cần hỏi bổ sung trước khi tạo yêu cầu.
- [BOOK-05] Khách hàng có thể sử dụng số điện thoại đang gọi đến làm số liên hệ đặt xe.
- [BOOK-06] Khách hàng có thể cung cấp số điện thoại liên hệ khác với số đang gọi để tài xế thuận tiện liên lạc.
- [BOOK-07] Trước khi gửi yêu cầu điều xe, tổng đài cần xác nhận lại điểm đón (giữ nguyên địa chỉ khách nói), điểm đến, các điểm dừng đã yêu cầu theo thứ tự, loại xe, thời gian đón và số điện thoại liên hệ; vùng tương đối được đọc ở mức đã xác minh.
- [BOOK-08] Nếu khách hàng cung cấp thông tin chưa đầy đủ hoặc chưa rõ ràng, tổng đài cần yêu cầu bổ sung trước khi tạo yêu cầu đặt xe.
- [BOOK-09] Khách hàng có thể yêu cầu tổng đài nhắc lại thông tin đặt xe trước khi xác nhận.

## 4. Quy định về điểm đón

- [PICK-01] Khách hàng cần cung cấp địa chỉ đón chi tiết hoặc mốc đón cụ thể; hệ thống giữ nguyên địa chỉ khách nói để hỗ trợ tìm và đón khách. Độ chi tiết khách cung cấp được phân biệt với độ chính xác bản đồ trả về.
- [PICK-02] Khách hàng có thể cung cấp điểm đón bằng số nhà, tên đường, tên tòa nhà, khách sạn, trung tâm thương mại hoặc địa danh cụ thể.
- [PICK-03] Nếu lời khách chỉ có tên vùng hoặc chưa có địa chỉ/mốc đón cụ thể, tổng đài cần hỏi thêm chi tiết hoặc địa điểm nhận diện gần đó. Khách đã nói địa chỉ chi tiết nhưng bản đồ thiếu số nhà/ngõ/ngách thì áp dụng PICK-09, không tự yêu cầu khách lặp lại chi tiết đã cung cấp.
- [PICK-04] Khách hàng có thể yêu cầu xe đón tại cổng tòa nhà, cổng bệnh viện, cổng trường học hoặc một vị trí thuận tiện khác.
- [PICK-05] Nếu vị trí khách yêu cầu nằm trong khu vực cấm dừng hoặc cấm đỗ, tài xế có thể đề xuất một điểm đón hợp lệ gần đó.
- [PICK-06] Đối với các con hẻm hoặc đường nhỏ mà xe ô tô không thể đi vào, khách hàng cần di chuyển ra vị trí mà xe có thể tiếp cận an toàn.
- [PICK-07] Nếu khách hàng không biết địa chỉ hiện tại, tổng đài có thể hướng dẫn khách xác định tên đường, biển hiệu hoặc địa danh gần nhất.
- [PICK-08] Tổng đài không được tự suy đoán tọa độ điểm đón hoặc thay địa chỉ khách nói bằng một địa điểm khác; địa chỉ và mức định vị được đọc lại trong tóm tắt để khách xác nhận.
- [PICK-09] Khi khách đã cung cấp địa chỉ đón chi tiết nhưng bản đồ chỉ xác định được xã/phường hiện hành và tỉnh/thành phố chứa địa chỉ đó, yêu cầu vẫn được chấp nhận. Bắt buộc giữ nguyên địa chỉ khách nói trong dữ liệu cuốc và ghi kèm nguyên văn vào ghi chú, cùng vùng đã xác minh và mức định vị. Không bắt buộc tìm được tọa độ ngõ/ngách/cổng hoặc hỏi lại chỉ vì bản đồ thiếu chi tiết.
- [PICK-10] Khách chỉ nói tên xã/phường hoặc hệ thống chỉ xác định đến cấp huyện trước sáp nhập thì chưa đủ cho điểm đón; cần bổ sung chi tiết hoặc xác định xã/phường hiện hành còn thiếu. Tọa độ tâm vùng nếu có không được trình bày như điểm đón chính xác.

## 5. Quy định về điểm đến

- [DEST-01] Khi đặt xe qua tổng đài, khách cần cung cấp điểm đến ở mức tối thiểu xã/phường hiện hành hoặc đơn vị cấp huyện trước sáp nhập, kèm tỉnh/thành phố; địa chỉ chi tiết có thể trao đổi với tài xế khi lên xe.
- [DEST-02] Nếu khách chưa xác định địa chỉ đến chính xác nhưng vùng tối thiểu đã được nguồn địa lý xác minh và các thông tin còn lại đầy đủ, tổng đài vẫn tiếp nhận yêu cầu. Không bắt buộc số nhà, tọa độ hoặc cổng điểm đến; chỉ tỉnh/thành phố hoặc chưa xác định vùng thì cần hỏi bổ sung.
- [DEST-03] Trước khi bắt đầu di chuyển, khách hàng cần xác nhận điểm đến cụ thể với tài xế.
- [DEST-04] Tài xế có trách nhiệm cập nhật thông tin điểm đến vào hệ thống trước khi khởi hành nếu thông tin này chưa được cung cấp khi đặt xe.
- [DEST-05] Khách hàng có thể thay đổi điểm đến trong quá trình di chuyển nếu tài xế có thể đáp ứng và tuyến đường mới phù hợp với phạm vi phục vụ.
- [DEST-06] Việc thay đổi điểm đến có thể làm thay đổi quãng đường và tổng cước phải thanh toán.
- [DEST-07] Nếu khách hàng muốn đi nhiều địa điểm trong cùng một chuyến, khách hàng cần thông báo trước cho tài xế.
- [DEST-08] Nếu điểm đến nằm ngoài phạm vi phục vụ, tài xế hoặc tổng đài sẽ thông báo và hướng dẫn phương án phù hợp.
- [DEST-09] Tổng đài không được cam kết giá chuyến đi cố định nếu chưa có xác nhận giá từ hệ thống.
- [DEST-10] Điểm dừng trung gian áp dụng cùng mức tối thiểu với điểm đến: xã/phường hiện hành hoặc đơn vị cấp huyện trước sáp nhập và tỉnh/thành phố đã xác minh. Không bắt buộc số nhà, tọa độ hoặc cổng; giữ tên/địa chỉ khách nói và thứ tự các điểm dừng.
- [DEST-11] Với tên có nhiều địa điểm như “Vincom”, tổng đài hỏi để xác định Vincom đó thuộc xã/phường hiện hành hoặc huyện trước đây nào và tỉnh/thành phố nào; tên chi nhánh có thể giúp xác định vùng. Khách trả lời được tỉnh thì tiếp tục hỏi vùng còn thiếu. Khi vùng tối thiểu đã xác định thì không hỏi thêm số nhà/cổng chỉ để tăng độ chi tiết.

## 6. Đặt xe hộ và đặt nhiều xe

- [MULTI-01] Khách hàng có thể gọi tổng đài để đặt xe hộ người thân, bạn bè hoặc đồng nghiệp.
- [MULTI-02] Khi đặt xe hộ người khác, khách hàng cần cung cấp địa chỉ đón và số điện thoại của người trực tiếp sử dụng dịch vụ.
- [MULTI-03] Tổng đài có thể ghi nhận tên hoặc đặc điểm nhận diện của người được đón để hỗ trợ tài xế tìm khách.
- [MULTI-04] Khách hàng có thể yêu cầu đặt nhiều xe cùng lúc nếu cần phục vụ một nhóm đông người.
- [MULTI-05] Mỗi xe được đặt cho nhóm khách sẽ được tạo thành một yêu cầu đặt xe riêng.
- [MULTI-06] Tổng đài không bảo đảm tất cả xe trong một yêu cầu đặt nhiều xe sẽ đến cùng một thời điểm.
- [MULTI-07] Khách hàng có thể đặt xe cho người thân không sử dụng điện thoại thông minh, nhưng cần cung cấp phương thức liên hệ phù hợp.

## 7. Đặt xe ngay và đặt xe trước

- [TIME-01] Khách hàng có thể yêu cầu xe đến đón ngay sau khi tổng đài tiếp nhận thông tin.
- [TIME-02] Khách hàng có thể yêu cầu đặt xe trước tối đa 24 giờ so với thời gian dự kiến khởi hành.
- [TIME-03] Đối với yêu cầu đặt xe trước, khách hàng cần đặt sớm hơn giờ đón mong muốn ít nhất 30 phút.
- [TIME-04] Khách hàng có thể lựa chọn thời gian đón cụ thể khi đặt xe trước.
- [TIME-05] Thời gian đón dự kiến không phải là cam kết tài xế sẽ đến chính xác tuyệt đối vào thời điểm đó.
- [TIME-06] Việc đặt xe trước không bảo đảm có xe nếu tại thời điểm điều phối không có phương tiện phù hợp.
- [TIME-07] Khách hàng có thể liên hệ tổng đài để yêu cầu thay đổi giờ đón đối với chuyến xe đặt trước.
- [TIME-08] Nếu khách hàng muốn đặt xe khởi hành ngay, tổng đài không cần yêu cầu khách cung cấp giờ đón cụ thể mà sẽ ghi nhận nhu cầu đón sớm nhất có thể.

## 8. Quy trình tiếp nhận và điều phối xe

- [DISP-01] Sau khi khách hàng xác nhận thông tin, tổng đài gửi yêu cầu đặt xe đến hệ thống điều phối.
- [DISP-02] Hệ thống điều phối ưu tiên tìm xe phù hợp đang hoạt động gần điểm đón của khách hàng.
- [DISP-03] Việc tìm xe phụ thuộc vào loại xe, khu vực, số lượng xe trống và điều kiện giao thông.
- [DISP-04] Khi có tài xế nhận chuyến, khách hàng sẽ được thông báo về trạng thái đặt xe.
- [DISP-05] Khi chuyến xe được xác nhận, khách hàng có thể nhận thông tin tài xế, biển số xe và thời gian dự kiến đến điểm đón.
- [DISP-06] Nếu chưa tìm được tài xế, tổng đài cần thông báo trạng thái chờ điều phối thay vì xác nhận đặt xe thành công.
- [DISP-07] Nếu hệ thống không tìm được xe phù hợp, tổng đài sẽ thông báo và đề xuất khách hàng thử lại sau hoặc thay đổi loại xe.
- [DISP-08] Khách hàng không thể yêu cầu hệ thống bắt buộc phân công một tài xế cụ thể.
- [DISP-09] Khách hàng có quyền từ chối loại xe thay thế do tổng đài đề xuất.

## 9. Thời gian xe đến đón

- [ETA-01] Thời gian xe đến điểm đón phụ thuộc vào vị trí hiện tại của tài xế và điều kiện giao thông.
- [ETA-02] Thời gian đón do hệ thống cung cấp chỉ mang tính dự kiến và có thể thay đổi trong quá trình tài xế di chuyển.
- [ETA-03] Khách hàng có thể liên hệ tổng đài để kiểm tra tình trạng chuyến xe đang chờ đón.
- [ETA-04] Nếu tài xế đến muộn hơn dự kiến, khách hàng có thể yêu cầu tổng đài kiểm tra lại vị trí và trạng thái tài xế.
- [ETA-05] Trong trường hợp tài xế không thể tiếp tục đến đón, tổng đài có thể hỗ trợ tìm một xe khác.
- [ETA-06] Nếu khách hàng không muốn chờ thêm, khách hàng có thể yêu cầu hủy chuyến chưa bắt đầu.
- [ETA-07] Tổng đài không được tự đưa ra thời gian xe đến nếu hệ thống chưa cung cấp kết quả dự kiến.

## 10. Quy định chờ khách tại điểm đón

- [WAIT-01] Sau khi đến điểm đón, tài xế sẽ liên hệ với khách hàng để thông báo xe đã tới.
- [WAIT-02] Khách hàng được miễn phí chờ trong 5 phút đầu tiên kể từ thời điểm bắt đầu tính chờ hợp lệ.
- [WAIT-03] Sau 5 phút miễn phí, hệ thống áp dụng phí chờ giả lập 3.000 đồng cho mỗi phút tiếp theo nếu chuyến đi được thực hiện.
- [WAIT-04] Thời điểm bắt đầu tính chờ đối với chuyến đặt trước không được sớm hơn giờ đón mà khách hàng đã xác nhận.
- [WAIT-05] Nếu khách hàng chưa thể ra xe, khách hàng nên thông báo cho tài xế hoặc tổng đài.
- [WAIT-06] Tài xế có thể hủy yêu cầu đón nếu khách hàng không xuất hiện sau 15 phút và không liên lạc được.
- [WAIT-07] Nếu chuyến đi bị hủy trước khi khách lên xe, khách hàng không bị thu phí chờ trong chính sách giả lập này.
- [WAIT-08] Nếu tài xế đến sai điểm đón đã xác nhận, thời gian chờ do sai vị trí không được tính phí cho khách hàng.

## 11. Thay đổi thông tin đặt xe

- [EDIT-01] Khách hàng có thể yêu cầu thay đổi điểm đón trước khi chuyến đi bắt đầu.
- [EDIT-02] Việc thay đổi điểm đón sau khi đã phân công tài xế có thể khiến hệ thống phải tìm tài xế khác.
- [EDIT-03] Khách hàng có thể yêu cầu thay đổi loại xe từ 4 chỗ sang 7 chỗ hoặc ngược lại nếu chuyến đi chưa bắt đầu.
- [EDIT-04] Nếu muốn thay đổi loại xe, tổng đài cần kiểm tra khả năng phục vụ trước khi xác nhận.
- [EDIT-05] Khách hàng có thể thay đổi số điện thoại liên hệ trước khi tài xế đến đón.
- [EDIT-06] Khách hàng có thể thay đổi thời gian đón đối với chuyến đặt trước nếu hệ thống còn hỗ trợ điều chỉnh.
- [EDIT-07] Nếu thông tin mới không thể áp dụng cho chuyến hiện tại, tổng đài có thể đề xuất hủy yêu cầu cũ và tạo yêu cầu mới.
- [EDIT-08] Khi thay đổi thông tin đặt xe, tổng đài cần xác nhận lại thông tin mới với khách hàng.

## 12. Quy định hủy chuyến

- [CANCEL-01] Khách hàng có thể yêu cầu hủy chuyến xe thông qua tổng đài trước khi bắt đầu di chuyển.
- [CANCEL-02] Việc hủy chuyến trước khi khách hàng lên xe được miễn phí theo chính sách giả lập này.
- [CANCEL-03] Khách hàng có thể hủy chuyến ngay cả khi hệ thống đã phân công tài xế.
- [CANCEL-04] Nếu khách hàng muốn hủy chuyến, tổng đài cần xác nhận đúng chuyến xe trước khi gửi yêu cầu hủy.
- [CANCEL-05] Sau khi hủy thành công, hệ thống không tiếp tục điều phối xe cho yêu cầu đã hủy.
- [CANCEL-06] Nếu khách hàng muốn đặt lại xe sau khi hủy, tổng đài cần tạo một yêu cầu đặt xe mới.
- [CANCEL-07] Nếu khách hàng đã lên xe và chuyến đi đang diễn ra, yêu cầu kết thúc chuyến sẽ được xử lý như kết thúc chuyến sớm và cước được tính theo phần dịch vụ đã sử dụng.
- [CANCEL-08] Nếu tài xế tự ý yêu cầu khách hàng hủy chuyến mà không có lý do phù hợp, khách hàng có thể phản ánh với tổng đài.

## 13. Cách tính cước và giá chuyến đi

- [FARE-01] Đối với chuyến xe đặt qua tổng đài, cước phí được tính theo quãng đường di chuyển thực tế do hệ thống đồng hồ tính cước ghi nhận.
- [FARE-02] Giá cước đặt xe qua tổng đài không bắt buộc phải được chốt thành một số tiền cố định trước khi khách hàng lên xe.
- [FARE-03] Nếu khách hàng yêu cầu biết trước chi phí chuyến đi, tổng đài có thể cung cấp giá tham khảo khi hệ thống có đủ dữ liệu tính giá.
- [FARE-04] Giá tham khảo không phải là giá cam kết thanh toán cuối cùng.
- [FARE-05] Trong bộ dữ liệu giả lập này, xe 4 chỗ có cước mở cửa 18.000 đồng cho 1 km đầu tiên.
- [FARE-06] Trong bộ dữ liệu giả lập này, từ sau 1 km đầu tiên, xe 4 chỗ có đơn giá 14.000 đồng cho mỗi km tiếp theo.
- [FARE-07] Trong bộ dữ liệu giả lập này, xe 7 chỗ có cước mở cửa 24.000 đồng cho 1 km đầu tiên.
- [FARE-08] Trong bộ dữ liệu giả lập này, từ sau 1 km đầu tiên, xe 7 chỗ có đơn giá 17.000 đồng cho mỗi km tiếp theo.
- [FARE-09] Tổng cước chuyến đi có thể bao gồm cước di chuyển, phí chờ và các khoản phụ phí hợp lệ.
- [FARE-10] Nếu khách hàng thay đổi tuyến đường, quãng đường tính cước được cập nhật theo hành trình di chuyển thực tế.
- [FARE-11] Khách hàng chỉ cần thanh toán số tiền được xác nhận sau khi kết thúc chuyến đi, cùng các phụ phí hợp lệ được thông báo.
- [FARE-12] Trong chính sách giả lập này, không áp dụng phụ phí tăng giá riêng theo giờ cao điểm hoặc ban đêm.
- [FARE-13] Tổng đài không được tự tính hoặc cam kết số tiền chuyến đi nếu thiếu dữ liệu quãng đường, loại xe hoặc thông tin phụ phí.

## 14. Quy định về phụ phí

- [FEE-01] Phí cầu đường và phí sử dụng đường cao tốc không được bao gồm trong đơn giá tính cước theo km của bộ dữ liệu giả lập.
- [FEE-02] Nếu hành trình đi qua trạm thu phí, khách hàng cần thanh toán khoản phí cầu đường phát sinh thực tế.
- [FEE-03] Nếu khách hàng yêu cầu đón hoặc trả tại khu vực có phí vào cổng, phí đỗ xe hoặc phí sân bay, các khoản phí hợp lệ có thể được cộng vào tổng tiền chuyến đi.
- [FEE-04] Tài xế cần thông báo cho khách hàng trước khi lựa chọn tuyến đường hoặc điểm đón làm phát sinh phụ phí có thể tránh được.
- [FEE-05] Phí chờ được tính theo quy định riêng về thời gian chờ tại điểm đón.
- [FEE-06] Tài xế không được tự ý thu các khoản phí ngoài quy định hoặc khoản phí không có căn cứ.
- [FEE-07] Nếu khách hàng thắc mắc về khoản phụ phí, khách hàng có thể yêu cầu tổng đài hỗ trợ kiểm tra.

## 15. Quy định về thanh toán

- [PAY-01] Khách hàng đặt xe qua tổng đài có thể thanh toán bằng tiền mặt sau khi hoàn thành chuyến đi.
- [PAY-02] Khách hàng có thể thanh toán bằng mã QR nếu xe và hệ thống thanh toán của chuyến đi hỗ trợ phương thức này.
- [PAY-03] Khách hàng không bắt buộc phải liên kết thẻ ngân hàng để đặt xe qua tổng đài.
- [PAY-04] Khách hàng không phải thanh toán trước toàn bộ cước chuyến đi khi tạo yêu cầu đặt xe thông thường.
- [PAY-05] Khách hàng cần kiểm tra số tiền thanh toán dựa trên thông tin cước chuyến đi và các khoản phụ phí hợp lệ.
- [PAY-06] Nếu khách hàng muốn đổi phương thức thanh toán, khách hàng cần thông báo với tài xế trước khi thực hiện thanh toán.
- [PAY-07] Khách hàng không bắt buộc phải trả thêm tiền boa cho tài xế.
- [PAY-08] Nếu giao dịch thanh toán điện tử gặp lỗi, khách hàng cần thông báo cho tài xế hoặc tổng đài trước khi thực hiện giao dịch lại.
- [PAY-09] Nếu khách hàng đã thanh toán nhưng hệ thống chưa ghi nhận, tổng đài cần hỗ trợ kiểm tra để tránh thu tiền hai lần.

## 16. Khuyến mại và mã giảm giá

- [PROMO-01] Chương trình khuyến mại dành riêng cho ứng dụng Xanh SM không mặc định áp dụng cho chuyến đặt qua tổng đài.
- [PROMO-02] Khách hàng chỉ được sử dụng mã giảm giá qua tổng đài nếu mã đó có điều kiện áp dụng cho kênh tổng đài.
- [PROMO-03] Nếu khách hàng cung cấp mã giảm giá, tổng đài cần kiểm tra điều kiện áp dụng trước khi xác nhận ưu đãi.
- [PROMO-04] Tổng đài không được cam kết giảm giá khi chưa xác minh tính hợp lệ của chương trình khuyến mại.
- [PROMO-05] Khách hàng muốn sử dụng khuyến mại chỉ dành cho ứng dụng cần thực hiện đặt chuyến thông qua ứng dụng Xanh SM.
- [PROMO-06] Những chương trình ưu đãi đã hết hạn hoặc không đáp ứng điều kiện sử dụng sẽ không được áp dụng.

## 17. Quy định về hành lý và đồ dùng cá nhân

- [LUG-01] Khách hàng có thể mang theo hành lý cá nhân khi sử dụng dịch vụ taxi Xanh SM.
- [LUG-02] Hành lý cần được sắp xếp gọn gàng, không cản trở tầm nhìn hoặc khả năng điều khiển xe của tài xế.
- [LUG-03] Khách hàng mang theo nhiều vali hoặc hành lý cồng kềnh nên lựa chọn xe 7 chỗ để có thêm không gian.
- [LUG-04] Nếu hành lý có kích thước lớn, khách hàng cần thông báo cho tổng đài trước khi đặt xe để kiểm tra khả năng vận chuyển.
- [LUG-05] Khách hàng không được mang theo chất dễ cháy nổ, hàng hóa bị pháp luật cấm hoặc vật dụng có nguy cơ gây mất an toàn.
- [LUG-06] Khách hàng có trách nhiệm tự kiểm tra và mang đủ hành lý cá nhân khi kết thúc chuyến đi.
- [LUG-07] Nếu khách hàng bỏ quên đồ trên xe, tổng đài có thể hỗ trợ liên hệ tài xế để kiểm tra.

## 18. Trẻ em, người cao tuổi và người cần hỗ trợ

- [SUP-01] Khách hàng có thể đặt xe để đưa đón người cao tuổi hoặc người gặp khó khăn trong việc di chuyển.
- [SUP-02] Nếu hành khách cần hỗ trợ đặc biệt khi lên hoặc xuống xe, người đặt cần thông báo với tổng đài trước khi tạo chuyến.
- [SUP-03] Người cao tuổi có thể sử dụng dịch vụ mà không cần điện thoại thông minh nếu có số điện thoại liên hệ phù hợp.
- [SUP-04] Trẻ em cần có người đủ khả năng giám sát đi cùng theo chính sách giả lập này.
- [SUP-05] Tổng đài không hỗ trợ đặt chuyến cho trẻ nhỏ đi một mình mà không có người giám sát.
- [SUP-06] Nếu khách hàng cần ghế an toàn chuyên dụng cho trẻ em, tổng đài cần kiểm tra khả năng đáp ứng; không được tự cam kết xe có sẵn loại ghế này.
- [SUP-07] Nếu hành khách sử dụng xe lăn gấp gọn, tổng đài cần kiểm tra khả năng chứa xe lăn trong khoang hành lý.
- [SUP-08] Tổng đài cần chuyển nhân viên hỗ trợ đối với yêu cầu phương tiện tiếp cận đặc biệt không nằm trong các lựa chọn đặt xe thông thường.

## 19. Thú cưng và các quy định trong xe

- [RULE-01] Khách hàng muốn mang thú cưng lên xe cần thông báo trước cho tổng đài hoặc tài xế.
- [RULE-02] Thú cưng cần được giữ an toàn trong lồng hoặc túi vận chuyển phù hợp, trừ trường hợp có phương án hỗ trợ đặc biệt được chấp thuận.
- [RULE-03] Tổng đài cần kiểm tra điều kiện phục vụ trước khi xác nhận những yêu cầu vận chuyển động vật đặc biệt.
- [RULE-04] Khách hàng không được hút thuốc trong xe.
- [RULE-05] Khách hàng cần giữ vệ sinh và không cố ý làm hư hỏng nội thất xe.
- [RULE-06] Khách hàng không được yêu cầu tài xế chở quá số người cho phép.
- [RULE-07] Khách hàng cần thắt dây an toàn khi sử dụng xe theo quy định an toàn giao thông.
- [RULE-08] Tài xế có thể từ chối tiếp tục chuyến đi nếu có hành vi đe dọa an toàn nghiêm trọng.

## 20. Quy định về hành trình và các điểm dừng

- [ROUTE-01] Khách hàng có thể trao đổi với tài xế về tuyến đường mong muốn khi lên xe.
- [ROUTE-02] Nếu khách hàng không yêu cầu tuyến đường cụ thể, tài xế có thể lựa chọn tuyến đường phù hợp với điều kiện giao thông.
- [ROUTE-03] Khách hàng có thể đề nghị tài xế thay đổi tuyến đường trong quá trình di chuyển nếu tuyến đường mới hợp lệ và an toàn.
- [ROUTE-04] Nếu khách hàng yêu cầu đi đường vòng hoặc thay đổi hành trình, tổng cước có thể tăng theo quãng đường thực tế.
- [ROUTE-05] Khách hàng có thể yêu cầu dừng tại một hoặc nhiều địa điểm trung gian nếu không vi phạm quy định dừng đỗ. Khi tạo yêu cầu, mỗi điểm dừng chỉ cần vùng tối thiểu theo DEST-10; ghi nhận đúng thứ tự, không bỏ điểm dừng chỉ vì thiếu tọa độ chi tiết.
- [ROUTE-06] Thời gian dừng chờ tại các điểm trung gian có thể làm phát sinh cước hoặc phí chờ theo cách tính của hệ thống.
- [ROUTE-07] Nếu khách hàng muốn đi khứ hồi, tổng đài có thể tư vấn đặt hai chuyến riêng biệt.
- [ROUTE-08] Khi đặt hai chuyến khứ hồi riêng biệt, hệ thống không bảo đảm chuyến về sẽ do tài xế của chuyến đi thực hiện.

## 21. Đặt xe đi sân bay, bến xe và đi tỉnh

- [TRIP-01] Khách hàng có thể yêu cầu đặt xe đón hoặc trả tại sân bay nếu khu vực đó nằm trong phạm vi phục vụ.
- [TRIP-02] Khi đặt xe đón tại sân bay, khách hàng cần cung cấp tên sân bay, nhà ga và điểm hẹn đón nếu đã biết.
- [TRIP-03] Nếu sân bay có quy định riêng về điểm đón xe, khách hàng cần di chuyển đến khu vực đón hợp lệ.
- [TRIP-04] Khách hàng nên đặt xe sớm khi có nhu cầu di chuyển ra sân bay để tránh ảnh hưởng đến lịch trình.
- [TRIP-05] Tổng đài không bảo đảm thời gian di chuyển chính xác tuyệt đối khi đường đông hoặc có sự cố giao thông.
- [TRIP-06] Khách hàng có thể yêu cầu chuyến xe liên tỉnh, nhưng khả năng phục vụ cần được kiểm tra theo điểm đón, điểm đến và phạm vi hoạt động.
- [TRIP-07] Đối với chuyến đi dài hoặc đi tỉnh, tổng đài cần xác nhận khả năng phục vụ trước khi cam kết điều xe.
- [TRIP-08] Phí cầu đường, đường cao tốc và những khoản phí hợp lệ trên hành trình đi tỉnh có thể được tính bổ sung.

## 22. Biên nhận và hóa đơn

- [BILL-01] Khách hàng có thể yêu cầu cung cấp thông tin cước và biên nhận sau khi hoàn tất chuyến đi.
- [BILL-02] Nếu muốn nhận hóa đơn điện tử, khách hàng cần cung cấp thông tin xuất hóa đơn theo yêu cầu của bộ phận hỗ trợ.
- [BILL-03] Thông tin xuất hóa đơn doanh nghiệp có thể bao gồm tên đơn vị, mã số thuế, địa chỉ và email nhận hóa đơn.
- [BILL-04] Trong chính sách giả lập này, khách hàng có thể gửi yêu cầu xuất hóa đơn trong vòng 7 ngày kể từ thời điểm kết thúc chuyến.
- [BILL-05] Tổng đài có thể hỗ trợ tra cứu thông tin chuyến đi để xử lý yêu cầu biên nhận hoặc hóa đơn.
- [BILL-06] Nếu khách hàng cung cấp thiếu thông tin hóa đơn, tổng đài cần hướng dẫn bổ sung trước khi chuyển bộ phận xử lý.

## 23. Phản ánh, khiếu nại và đồ thất lạc

- [HELP-01] Khách hàng có thể liên hệ tổng đài để phản ánh về thái độ phục vụ, chất lượng xe hoặc cách tính cước.
- [HELP-02] Khi tiếp nhận phản ánh, tổng đài cần xác định chuyến xe liên quan thông qua số điện thoại, thời gian đi hoặc mã chuyến.
- [HELP-03] Nếu khách hàng cho rằng số tiền bị tính sai, tổng đài cần tiếp nhận yêu cầu kiểm tra cước.
- [HELP-04] Tổng đài không được tự cam kết hoàn tiền khi chưa có kết quả xác minh.
- [HELP-05] Nếu khách hàng làm rơi đồ trên xe, tổng đài cần hỗ trợ tìm chuyến và chuyển thông tin cho bộ phận phụ trách.
- [HELP-06] Nếu tìm thấy đồ thất lạc, bộ phận hỗ trợ sẽ liên hệ khách hàng để thống nhất phương thức nhận lại.
- [HELP-07] Nếu tài xế có hành vi không phù hợp, khách hàng có thể cung cấp biển số xe hoặc thông tin chuyến đi để tổng đài ghi nhận phản ánh.
- [HELP-08] Đối với sự cố an toàn đang diễn ra, cần ưu tiên hướng dẫn khách hàng đến vị trí an toàn và liên hệ dịch vụ khẩn cấp thích hợp thay vì chỉ ghi nhận khiếu nại thông thường.

## 24. Bảo mật và xác minh thông tin

- [SAFE-01] Khách hàng không cần cung cấp mật khẩu ứng dụng hoặc mật khẩu tài khoản ngân hàng để đặt xe qua tổng đài.
- [SAFE-02] Tổng đài không được yêu cầu khách hàng đọc mã OTP ngân hàng hoặc mã xác thực đăng nhập để đặt xe thông thường.
- [SAFE-03] Tổng đài chỉ thu thập thông tin cá nhân cần thiết để tạo, quản lý hoặc hỗ trợ chuyến đi.
- [SAFE-04] Thông tin số điện thoại và địa chỉ của khách hàng không được tiết lộ cho người không có quyền truy cập.
- [SAFE-05] Nếu có người yêu cầu kiểm tra chuyến đi của khách hàng khác, tổng đài cần thực hiện bước xác minh theo quy trình trước khi cung cấp thông tin.
- [SAFE-06] Tổng đài không được cung cấp lịch sử chuyến đi hoặc dữ liệu cá nhân chỉ dựa trên việc người gọi biết tên khách hàng.
- [SAFE-07] Nếu khách hàng nghi ngờ có hành vi lừa đảo liên quan đến thanh toán, tổng đài cần hướng dẫn khách hàng dừng giao dịch đáng ngờ và chuyển bộ phận hỗ trợ.
- [SAFE-08] Khách hàng có thể yêu cầu hỗ trợ về dữ liệu cá nhân thông qua bộ phận chăm sóc khách hàng.

## 25. Các trường hợp tổng đài cần hỗ trợ thêm

- [EXC-01] Nếu địa chỉ chưa rõ, tổng đài hỏi đúng phần còn thiếu theo vai trò: điểm đón cần chi tiết khách nói và áp dụng PICK-09 khi chỉ định vị được xã/phường; điểm đến/điểm dừng chỉ cần xác định xã/phường hiện hành hoặc đơn vị cấp huyện trước sáp nhập và tỉnh/thành phố. Không hỏi thêm số nhà/cổng khi đã đủ điều kiện tương ứng.
- [EXC-02] Nếu khách hàng không biết nên chọn xe 4 chỗ hay 7 chỗ, tổng đài cần hỏi số người và lượng hành lý để tư vấn.
- [EXC-03] Nếu khách chưa biết địa chỉ điểm đến chi tiết nhưng đã xác định vùng tối thiểu theo DEST-01, tổng đài tiếp tục đặt xe và hướng dẫn trao đổi chi tiết với tài xế. Nếu chưa xác định vùng hoặc chỉ biết tỉnh/thành phố, cần hỏi bổ sung trước khi chốt yêu cầu.
- [EXC-04] Nếu khách hàng yêu cầu loại xe không hỗ trợ qua tổng đài, tổng đài cần giải thích giới hạn dịch vụ và hướng dẫn sử dụng ứng dụng.
- [EXC-05] Nếu khách hàng hỏi về thời gian xe đến, tổng đài cần tra cứu trạng thái hệ thống thay vì tự dự đoán.
- [EXC-06] Nếu khách hàng hỏi tổng tiền chuyến đi nhưng chưa có kết quả tính giá, tổng đài chỉ được giải thích nguyên tắc tính cước.
- [EXC-07] Nếu không tìm được xe, tổng đài cần thông báo rõ rằng chưa có tài xế nhận chuyến và đề xuất phương án khác.
- [EXC-08] Nếu khách hàng muốn đặt xe tại khu vực chưa được xác định là có dịch vụ, tổng đài cần kiểm tra phạm vi phục vụ trước khi xác nhận.
- [EXC-09] Nếu khách hàng cần trợ giúp vượt quá chức năng đặt xe tự động, tổng đài có thể chuyển cuộc gọi đến nhân viên hỗ trợ.
- [EXC-10] Nếu thông tin khách hàng cung cấp mâu thuẫn nhau, tổng đài cần hỏi lại trước khi tạo hoặc thay đổi chuyến.
- [EXC-11] Nếu hệ thống tạo chuyến báo lỗi, tổng đài không được thông báo rằng đặt xe đã thành công.
- [EXC-12] Nếu khách hàng yêu cầu một ngoại lệ chưa có trong quy định, tổng đài không được tự chấp thuận mà cần chuyển nhân viên có thẩm quyền xử lý.
