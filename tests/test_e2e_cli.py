"""End-to-End tests for SessionRunner CLI."""

from src.cli.runner import SessionRunner
from src.core.validators import validate_spoken_text
from src.db.sqlite_manager import SQLiteManager


def test_e2e_cli_full_booking_flow(tmp_path):
    db_file = str(tmp_path / "e2e_parrotgo.db")
    runner = SessionRunner(
        phone="0999123456",
        name="Lê Văn C",
        city="Hà Nội",
        db_path=db_file,
    )
    runner.start_new_session()
    assert runner.session_id is not None

    # Turn 1: User says pickup
    reply1 = runner.handle_turn("Đón tôi ở 12 Cầu Giấy")
    assert reply1 is not None
    validate_spoken_text(reply1)
    assert not runner.is_session_terminal()

    # Turn 2: User says destination
    reply2 = runner.handle_turn("Đi đến Viện 108")
    assert reply2 is not None
    validate_spoken_text(reply2)
    assert not runner.is_session_terminal()

    # Turn 3: User says vehicle
    reply3 = runner.handle_turn("Xe bốn chỗ")
    assert reply3 is not None
    validate_spoken_text(reply3)
    assert "đúng chưa" in reply3.lower()

    # Turn 4: User confirms
    reply4 = runner.handle_turn("Đúng rồi em")
    assert reply4 is not None
    validate_spoken_text(reply4)
    assert "thành công" in reply4.lower()
    assert runner.is_session_terminal()

    # Verify SQLite database contains the booking
    db = SQLiteManager(db_path=db_file)
    with db.get_connection() as conn:
        book_row = conn.execute(
            "SELECT * FROM bookings WHERE session_id = ?;", (runner.session_id,)
        ).fetchone()
        assert book_row is not None
        assert book_row["customer_phone"] == "0999123456"
        assert book_row["vehicle_type"] == "oto_4_cho"

        # Check total messages logged
        msg_count = conn.execute(
            "SELECT count(*) as c FROM session_messages WHERE session_id = ?;",
            (runner.session_id,),
        ).fetchone()["c"]
        assert msg_count == 4


def test_e2e_cli_nationwide_city_clarification_flow(tmp_path):
    db_file = str(tmp_path / "e2e_nationwide.db")
    runner = SessionRunner(
        phone="0911223344",
        name="Chị Hương",
        city=None,  # Nationwide call center mode: no pre-assigned city
        db_path=db_file,
    )
    runner.start_new_session()
    assert runner.session_id is not None

    # Turn 1: User mentions ambiguous street without specifying city
    reply1 = runner.handle_turn("Đón tôi ở đường Nguyễn Trãi")
    assert reply1 is not None
    validate_spoken_text(reply1)
    # The nationwide assistant correctly asks for province/city clarification
    assert "tỉnh hoặc thành phố" in reply1.lower()

    # Turn 2: User clarifies city
    reply2 = runner.handle_turn("Hà Nội")
    assert reply2 is not None
    validate_spoken_text(reply2)
    assert not runner.is_session_terminal()

