import json

with open("data/seed_data/policy_faqs.json", "r", encoding="utf-8-sig") as f:
    data = json.load(f)

# Update pet policy
for item in data:
    if item["id"] == "faq_pet_policy":
        item["questions"] = ["Có được mang theo thú cưng không?", "Có cho chó lên xe không?", "Mang mèo theo được không?", "Quy định chở động vật thế nào?"]
        item["keywords"] = ["thú cưng", "chó", "mèo", "động vật", "vật nuôi"]
        item["metadata"]["approved"] = True
        item["metadata"]["canonical_answer"] = "Dạ mình có thể mang theo thú cưng nhưng cần thông báo trước ạ. Thú cưng cần được giữ an toàn trong lồng hoặc túi vận chuyển phù hợp trên xe ạ."
        item["metadata"]["source"] = "rag.md#19"
    elif item["id"] == "faq_child_seat":
        item["questions"] = ["Có ghế trẻ em không?", "Trẻ em đi một mình được không?", "Có hỗ trợ em bé không?"]
        item["keywords"] = ["trẻ em", "em bé", "trẻ nhỏ", "ghế trẻ em"]
        item["metadata"]["approved"] = True
        item["metadata"]["canonical_answer"] = "Dạ trẻ em cần có người lớn đi cùng ạ. Nếu mình cần ghế an toàn chuyên dụng cho trẻ em, em sẽ ghi chú lại để kiểm tra xem có xe đáp ứng được không, chứ không cam kết chắc chắn có sẵn ạ."
        item["metadata"]["source"] = "rag.md#18"

# Add luggage policy
luggage = {
    "id": "faq_luggage",
    "document": "Quy định về hành lý và đồ dùng cá nhân",
    "questions": ["Tôi mang theo nhiều đồ được không?", "Có chỗ để vali không?", "Hành lý cồng kềnh chở được không?"],
    "keywords": ["hành lý", "vali", "đồ đạc", "cồng kềnh"],
    "metadata": {
        "category": "policy",
        "sub_intent": "luggage",
        "vehicle_type": "all",
        "canonical_answer": "Dạ mình có thể mang theo hành lý cá nhân. Nếu có nhiều vali hoặc đồ cồng kềnh, mình nên chọn xe 7 chỗ để có thêm không gian nhé.",
        "source": "rag.md#17",
        "version": "v2",
        "approved": True
    }
}
if not any(x["id"] == "faq_luggage" for x in data):
    data.append(luggage)

# Add payment policy
payment = {
    "id": "faq_payment",
    "document": "Các hình thức thanh toán được chấp nhận",
    "questions": ["Có thanh toán bằng tiền mặt không?", "Có chuyển khoản được không?", "Quét mã QR được không?", "Trả thẻ được không?"],
    "keywords": ["thanh toán", "tiền mặt", "chuyển khoản", "mã qr", "quét mã", "trả tiền"],
    "metadata": {
        "category": "policy",
        "sub_intent": "payment",
        "vehicle_type": "all",
        "canonical_answer": "Dạ mình có thể thanh toán bằng tiền mặt hoặc quét mã QR sau khi hoàn thành chuyến đi ạ. Không bắt buộc phải thanh toán trước đâu ạ.",
        "source": "rag.md#15",
        "version": "v2",
        "approved": True
    }
}
if not any(x["id"] == "faq_payment" for x in data):
    data.append(payment)

with open("data/seed_data/policy_faqs.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
