"""Regression tests for sourced FAQ retrieval using actual persistent Chroma vectors."""

import json
from pathlib import Path

import pytest

from src.config import settings
from src.core.state import get_initial_booking_slots
from src.db.chroma_client import ChromaFAQClient
from src.services.embedding_adapter import EmbeddingAdapter
from src.services.templates import join_speech, render_template_by_action


@pytest.fixture
def rag_client(tmp_path, monkeypatch):
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

    model_path = Path(ONNXMiniLM_L6_V2.DOWNLOAD_PATH) / "onnx" / "model.onnx"
    if not model_path.exists():
        pytest.skip("The local ONNX model must be cached before offline RAG integration tests")
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    return ChromaFAQClient(
        data_dir=str(tmp_path / "chroma"),
        embedding=EmbeddingAdapter(provider="onnx", model="all-MiniLM-L6-v2", dimensions=384),
    )


def chunk(chunk_id, question, answer, vehicle_type="all", approved=True, **extra):
    return {
        "id": chunk_id,
        "document": question,
        "metadata": {
            "canonical_answer": answer,
            "source": "test_fixture",
            "version": "v1",
            "approved": approved,
            "vehicle_type": vehicle_type,
        },
        **extra,
    }


def test_seed_questions_use_real_vectors_and_survive_client_restart(rag_client):
    seed_file = Path(__file__).resolve().parents[1] / "data" / "seed_data" / "policy_faqs.json"
    chunks = json.loads(seed_file.read_text(encoding="utf-8"))
    assert rag_client.upsert_faq_policies(chunks) == len(chunks)
    restarted = ChromaFAQClient(data_dir=rag_client.data_dir)
    questions = {
        "Có những loại xe nào?": "faq_supported_vehicles",
        "Có xe bốn chỗ không?": "faq_supported_vehicles",
        "Có xe bảy chỗ không?": "faq_supported_vehicles",
        "Tôi cần cung cấp thông tin gì để đặt xe?": "faq_booking_information",
        "Hệ thống đã điều tài xế chưa?": "faq_booking_saved_only",
        "Có thể hẹn giờ đón không?": "faq_scheduled_pickup",
        "Tôi có thể thêm điểm dừng không?": "faq_stopovers",
        "Tôi có thể sửa thông tin trước khi xác nhận không?": "faq_modify_before_confirmation",
        "Tôi có thể hủy yêu cầu trước khi xác nhận không?": "faq_cancel_before_confirmation",
    }
    for question, faq_id in questions.items():
        answer = restarted.search_faq_policy(question)
        assert answer["success"], answer
        assert answer["metadata"]["chunk_id"] == faq_id
        assert answer["source"] != "official_terms"
    indexed_questions = {
        question for item in chunks for question in [item["document"], *item.get("questions", [])]
    }
    unseen_questions = {
        "Muốn hẹn đón vào ngày mai có được không?": "faq_scheduled_pickup",
        "Trên đường tôi muốn ghé thêm một chỗ được không?": "faq_stopovers",
        "Tôi muốn thay điểm đến thì làm sao?": "faq_modify_before_confirmation",
        "Có thể hẹn xe tới đón ngày mai được không?": "faq_scheduled_pickup",
        "Mình muốn ghé một nơi trên đường trước khi tới điểm đến được không?": "faq_stopovers",
        "Nếu muốn thay chỗ đón đã nói thì phải làm gì?": "faq_modify_before_confirmation",
        "Tôi muốn ghé thêm một chỗ để mua đồ rồi đi tiếp có được không?": "faq_stopovers",
        "Tôi có thể điều chỉnh địa chỉ đến khi chưa xác nhận không?": "faq_modify_before_confirmation",
    }
    for question, faq_id in unseen_questions.items():
        assert question not in indexed_questions
        answer = restarted.search_faq_policy(question)
        assert answer["success"], answer
        assert answer["metadata"]["chunk_id"] == faq_id
        assert answer["metadata"]["score"] >= 0.82
    collection = restarted._get_collection()
    assert collection.metadata["embedding_dimensions"] == 384
    assert len(collection.get(limit=1, include=["embeddings"])["embeddings"][0]) == 384
    for unknown_policy in (
        "Cho mang thú cưng lên xe không?", "Có ghế trẻ em không?",
        "Có xe bốn chỗ chở thú cưng không?", "Xe máy có ghế trẻ em không?",
        "Đi xe máy có được mang chó không?", "Có xe bốn chỗ không và giá bao nhiêu?",
        "Toi muon mang cho len xe may duoc khong?",
        "Tôi muốn thay điểm đến để mang chó lên xe thì được không?",
    ):
        assert not restarted.search_faq_policy(unknown_policy)["success"]


def test_vehicle_filter_and_unapproved_chunks(rag_client):
    question = "Quy định hành lý là gì?"
    rag_client.upsert_faq_policies([
        chunk("motorcycle", question, "Chính sách xe máy đã duyệt.", vehicle_type="xe_may"),
        chunk("car", question, "Chính sách ô tô đã duyệt.", vehicle_type="oto_4_cho"),
        chunk("draft", question, "Nội dung chưa duyệt.", approved=False),
    ])
    assert rag_client.search_faq_policy(question, "xe_may")["answer_text"] == "Chính sách xe máy đã duyệt."
    assert rag_client.search_faq_policy(question, "oto_4_cho")["answer_text"] == "Chính sách ô tô đã duyệt."
    assert not rag_client.search_faq_policy(question)["success"]
    assert not rag_client.search_faq_policy(question, "oto_7_cho")["success"]


def test_revoking_faq_also_revokes_old_question_variants(rag_client):
    question = "Có những loại xe nào?"
    rag_client.upsert_faq_policies([
        chunk("vehicles", question, "Xe máy và ô tô.", questions=["Có xe máy không?"]),
    ])
    assert rag_client.search_faq_policy("Có xe máy không?")["success"]
    rag_client.upsert_faq_policies([chunk("vehicles", question, "Chưa được duyệt.", approved=False)])
    assert not rag_client.search_faq_policy("Có xe máy không?")["success"]
    records = rag_client._get_collection().get(where={"faq_id": "vehicles"})
    assert all(not metadata["approved"] for metadata in records["metadatas"])


def test_moderate_confidence_falls_back_without_adding_a_question(rag_client, monkeypatch):
    rag_client.upsert_faq_policies([chunk("vehicles", "Có những loại xe nào?", "Nội dung chính sách.")])
    collection = rag_client._get_collection()
    monkeypatch.setattr(collection, "query", lambda **kwargs: {
        "ids": [["vehicles"]],
        "distances": [[0.25]],
        "metadatas": [[{"faq_id": "vehicles", "canonical_answer": "Nội dung chính sách.", "source": "test_fixture", "version": "v1"}]],
    })
    answer = rag_client.search_faq_policy("Câu hỏi chưa rõ")
    assert not answer["success"]
    assert answer["source"] == "faq_needs_clarification"
    assert "Nội dung chính sách" not in answer["answer_text"]
    assert "?" not in answer["answer_text"]
    action = {"action_type": "ask_slot", "target_slots": ["pickup"], "metadata": {}}
    spoken = join_speech(answer["answer_text"], render_template_by_action(action, get_initial_booking_slots()))
    assert spoken.count("?") == 1
    assert "nơi đón" in spoken


def test_topic_guard_rejects_similar_but_unrelated_question(rag_client):
    rag_client.upsert_faq_policies([
        chunk("vehicles", "Có xe máy không?", "Có xe máy.", keywords=["xe máy"]),
    ])
    assert not rag_client.search_faq_policy("Có ghế trẻ em không?", high_threshold=0.5)["success"]


def test_legacy_collection_keeps_existing_documents(rag_client):
    legacy = rag_client._get_client().get_or_create_collection(
        name="parrotgo_faq", embedding_function=None, metadata={"hnsw:space": "cosine"}
    )
    legacy.upsert(
        ids=["existing"], documents=["Câu hỏi cũ"],
        embeddings=rag_client.embedding.embed_texts(["Câu hỏi cũ"]),
        metadatas=[{"approved": False, "canonical_answer": "Giữ nguyên"}],
    )
    rag_client.upsert_faq_policies([chunk("new", "Có những loại xe nào?", "Xe máy và ô tô.")])
    assert rag_client._get_collection().get(ids=["existing"])["documents"] == ["Câu hỏi cũ"]


def test_embedding_manifest_mismatch_does_not_overwrite_collection(rag_client):
    rag_client.upsert_faq_policies([chunk("vehicles", "Có những loại xe nào?", "Xe máy và ô tô.")])
    incompatible = ChromaFAQClient(
        data_dir=rag_client.data_dir,
        embedding=EmbeddingAdapter(provider="onnx", dimensions=768),
    )
    with pytest.raises(ValueError, match="another embedding model"):
        incompatible.upsert_faq_policies([chunk("other", "Câu hỏi khác", "Trả lời khác")])
    assert rag_client._get_collection().count() == 1


def test_approval_is_boolean_and_approved_answers_require_sources():
    client = ChromaFAQClient()
    invalid = chunk("wrong", "Câu hỏi", "Câu trả lời", approved="true")
    with pytest.raises(TypeError, match="boolean"):
        client.validate_chunks([invalid])
    invalid = chunk("wrong", "Câu hỏi", "Câu trả lời")
    invalid["metadata"].pop("source")
    with pytest.raises(ValueError, match="source and version"):
        client.validate_chunks([invalid])
