"""FAQ interruptions preserve confirmation without repeating a long trip summary."""
from src.cli.runner import SessionRunner
from src.services.qa_dispatcher import chroma_faq_client


def confirming_runner(tmp_path, monkeypatch):
    monkeypatch.setattr(chroma_faq_client, "search_faq_policy", lambda *args, **kwargs: {"category": "static_faq", "success": True, "answer_text": "Dạ mình báo trước khi mang thú cưng ạ.", "source": "test", "metadata": {}})
    runner = SessionRunner(phone="0999000777", name="Audit", city="Hà Nội", db_path=str(tmp_path / "quiet-faq.db"))
    runner.handle_turn("đón ở 12 Cầu Giấy")
    runner.handle_turn("đi đến Viện 108")
    summary = runner.handle_turn("xe bốn chỗ")
    assert "Thông tin này đã đúng chưa" in summary
    return runner


def test_faq_answer_is_short_and_next_confirmation_still_books(tmp_path, monkeypatch):
    runner = confirming_runner(tmp_path, monkeypatch)
    text = runner.handle_turn("xe bốn chỗ chở chó được không?")
    assert text == "Dạ mình báo trước khi mang thú cưng ạ."
    snapshot = runner.graph.get_state({"configurable": {"thread_id": runner.session_id}}).values
    assert snapshot["last_bot_action"]["action_type"] == "confirm_booking"
    reply = runner.handle_turn("đúng rồi")
    assert "thành công" in reply
    assert runner.is_session_terminal()


def test_repeat_after_quiet_faq_reads_trip_summary(tmp_path, monkeypatch):
    runner = confirming_runner(tmp_path, monkeypatch)
    runner.handle_turn("xe bốn chỗ chở chó được không?")
    text = runner.handle_turn("nhắc lại")
    assert "12 Cầu Giấy" in text and "108" in text
    assert "Thông tin này đã đúng chưa" in text
    assert "thú cưng" not in text
    assert "thành công" in runner.handle_turn("đúng rồi")


def test_question_and_vehicle_edit_reads_new_summary(tmp_path, monkeypatch):
    runner = confirming_runner(tmp_path, monkeypatch)
    text = runner.handle_turn("đổi sang xe bảy chỗ, chở chó được không?")
    assert "thú cưng" in text
    assert "bảy chỗ" in text
    assert "Thông tin này đã đúng chưa" in text


def test_repeat_trip_question_reads_addresses_once_and_preserves_confirmation(tmp_path, monkeypatch):
    runner = confirming_runner(tmp_path, monkeypatch)
    text = runner.handle_turn("Nhắc lại thông tin chuyến đi?")
    assert text.count("12 Cầu Giấy") == 1
    assert text.count("108") == 1
    assert text.count("Thông tin này đã đúng chưa") == 1
    assert "chuyến đi của mình hiện gồm" not in text
    assert "thành công" in runner.handle_turn("đúng rồi")
