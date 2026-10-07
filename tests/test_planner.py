"""Tests covering Planner, Reducer, Policy, and multi-turn state transitions."""

from src.core.graph import build_parrotgo_graph
from src.core.state import create_initial_state
from src.core.time_utils import now_iso


def test_planner_happy_path(tmp_path):
    # Setup graph with fresh temp SQLite DB
    db_file = str(tmp_path / "planner_test.db")
    from src.db.sqlite_manager import SQLiteManager, set_default_db_manager
    db = SQLiteManager(db_path=db_file)
    set_default_db_manager(db)
    graph = build_parrotgo_graph()

    session_id = "sess-happy-01"
    phone = "0987111222"
    name = "Khách Hàng A"
    started_at = now_iso()
    db.start_session(session_id, phone, name, "Hà Nội", "Asia/Ho_Chi_Minh", started_at)

    config = {"configurable": {"thread_id": session_id}}

    # Turn 1: user gives pickup
    t1_state = create_initial_state(session_id, phone, name, started_at, session_city="Hà Nội")
    t1_state["user_current_input"] = "Đón tôi ở 12 Cầu Giấy"
    res1 = graph.invoke(t1_state, config=config)
    assert res1["booking_status"] == "collecting"
    assert res1["booking_slots"]["pickup"]["status"] == "extracted"
    assert "đến đâu" in res1["final_response_text"].lower()

    # Turn 2: user gives destination
    t2_input = {
        "user_current_input": "Tôi muốn đến Viện 108",
        "turn_received_at": now_iso(),
    }
    res2 = graph.invoke(t2_input, config=config)
    assert res2["booking_status"] == "collecting"
    assert res2["booking_slots"]["destination"]["status"] == "extracted"
    assert "loại xe" in res2["final_response_text"].lower()

    # Turn 3: user gives vehicle
    t3_input = {
        "user_current_input": "Đi ô tô bốn chỗ nhé",
        "turn_received_at": now_iso(),
    }
    res3 = graph.invoke(t3_input, config=config)
    # Pickup time was defaulted to 'now' when address was present
    assert res3["ready_to_book"] is True
    assert res3["booking_status"] == "confirming"
    assert "đúng chưa" in res3["final_response_text"].lower()

    # Turn 4: user confirms
    t4_input = {
        "user_current_input": "Đúng rồi em",
        "turn_received_at": now_iso(),
    }
    res4 = graph.invoke(t4_input, config=config)
    assert res4["booking_status"] == "booked"
    assert res4["is_terminal"] is True
    assert res4["booking_id"] is not None
    assert "thành công" in res4["final_response_text"].lower()


def test_planner_one_shot_all_info(tmp_path):
    db_file = str(tmp_path / "planner_test.db")
    from src.db.sqlite_manager import SQLiteManager, set_default_db_manager
    db = SQLiteManager(db_path=db_file)
    set_default_db_manager(db)
    graph = build_parrotgo_graph()

    session_id = "sess-oneshot-01"
    phone = "0987333444"
    name = "Khách Hàng B"
    started_at = now_iso()
    db.start_session(session_id, phone, name, "Hà Nội", "Asia/Ho_Chi_Minh", started_at)

    config = {"configurable": {"thread_id": session_id}}

    t1_state = create_initial_state(session_id, phone, name, started_at, session_city="Hà Nội")
    t1_state["user_current_input"] = "Đón ở 12 Cầu Giấy sang Viện 108, đi bốn chỗ bây giờ"
    res1 = graph.invoke(t1_state, config=config)

    # Must be ready to book and confirming, not booked on turn 1!
    assert res1["ready_to_book"] is True
    assert res1["booking_status"] == "confirming"
    assert "đúng chưa" in res1["final_response_text"].lower()


def test_planner_cancel_flow(tmp_path):
    db_file = str(tmp_path / "planner_test.db")
    from src.db.sqlite_manager import SQLiteManager, set_default_db_manager
    db = SQLiteManager(db_path=db_file)
    set_default_db_manager(db)
    graph = build_parrotgo_graph()

    session_id = "sess-cancel-01"
    phone = "0987555666"
    name = "Khách Hàng C"
    started_at = now_iso()
    db.start_session(session_id, phone, name, "Hà Nội", "Asia/Ho_Chi_Minh", started_at)

    config = {"configurable": {"thread_id": session_id}}

    # Turn 1: user initiates cancel
    t1_state = create_initial_state(session_id, phone, name, started_at, session_city="Hà Nội")
    t1_state["user_current_input"] = "Thôi tôi muốn hủy xe không đi nữa"
    res1 = graph.invoke(t1_state, config=config)
    assert res1["booking_status"] == "cancel_pending"
    assert "chắc muốn hủy" in res1["final_response_text"].lower()

    # Turn 2: user confirms cancellation
    t2_input = {
        "user_current_input": "Đúng rồi, hủy giúp tôi",
        "turn_received_at": now_iso(),
    }
    res2 = graph.invoke(t2_input, config=config)
    assert res2["booking_status"] == "canceled"
    assert res2["is_terminal"] is True
    assert "đã hủy" in res2["final_response_text"].lower()


def test_planner_request_operator(tmp_path):
    db_file = str(tmp_path / "planner_test.db")
    from src.db.sqlite_manager import SQLiteManager, set_default_db_manager
    db = SQLiteManager(db_path=db_file)
    set_default_db_manager(db)
    graph = build_parrotgo_graph()

    session_id = "sess-operator-01"
    phone = "0987777888"
    name = "Khách Hàng D"
    started_at = now_iso()
    db.start_session(session_id, phone, name, "Hà Nội", "Asia/Ho_Chi_Minh", started_at)

    config = {"configurable": {"thread_id": session_id}}

    t1_state = create_initial_state(session_id, phone, name, started_at, session_city="Hà Nội")
    t1_state["user_current_input"] = "Cho tôi gặp trực tiếp nhân viên tổng đài"
    res1 = graph.invoke(t1_state, config=config)
    assert res1["booking_status"] == "operator_required"
    assert res1["is_terminal"] is True
    assert "nhân viên hỗ trợ" in res1["final_response_text"].lower()
