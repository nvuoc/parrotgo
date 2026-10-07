"""Bounded real API and RAG checks using synthetic customers and temporary bookings."""

import argparse
import copy
import json
import sys
import tempfile
import time
from contextlib import closing
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import settings
from src.cli.runner import SessionRunner
from src.core.time_utils import now_iso, parse_aware
from src.db.chroma_client import chroma_faq_client
from src.db.in_memory_cache import geo_cache, normalize_geo_key
from src.services.vietmap_client import vietmap_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(ROOT / "reports" / f"live-demo-check-{now_iso(settings.SESSION_TIMEZONE)[:10]}.json"))
    args = parser.parse_args()
    if not settings.VIETMAP_API_KEY or settings.LLM_MODE not in {"gemini", "groq"}:
        print("Configure VIETMAP_API_KEY and a live LLM_MODE before running these checks.")
        return 2
    settings.RAG_ENABLED = True
    vietmap_client.mode = "live"
    checks = []
    turns = []
    consecutive_service_errors = 0

    class LiveProviderUnavailable(Exception):
        pass
    started = time.perf_counter()
    reference = now_iso(settings.SESSION_TIMEZONE)
    report = {"started_at": reference, "llm_provider": settings.LLM_MODE, "map_provider": "vietmap_live", "checks": checks, "turns": turns}

    def check(name, condition, **evidence):
        checks.append({"name": name, "passed": bool(condition), **evidence})

    def step(runner, text):
        nonlocal consecutive_service_errors
        tick = time.perf_counter()
        try:
            reply = runner.handle_turn(text)
            state = runner.graph.get_state({"configurable": {"thread_id": runner.session_id}}).values
            turns.append({"input": text, "reply": reply, "latency_seconds": round(time.perf_counter() - tick, 3),
                          "booking_status": state.get("booking_status"), "nlu_error": state.get("nlu_error"),
                          "pickup": copy.deepcopy(state.get("booking_slots", {}).get("pickup")),
                          "destination": copy.deepcopy(state.get("booking_slots", {}).get("destination")),
                          "vehicle": copy.deepcopy(state.get("booking_slots", {}).get("vehicle_type")),
                          "pickup_time": copy.deepcopy(state.get("booking_slots", {}).get("pickup_time")),
                          "qa_source": (state.get("qa_response") or {}).get("source")})
            check("live_nlu: " + text, not state.get("nlu_error"))
            consecutive_service_errors = consecutive_service_errors + 1 if state.get("nlu_error") else 0
            if consecutive_service_errors >= 2:
                raise LiveProviderUnavailable
            return state, reply
        except LiveProviderUnavailable:
            raise
        except Exception as error:
            check("turn_error: " + text, False, error_type=type(error).__name__)
            return {}, ""

    try:
        # This client call goes to Vietmap, even if the local snapshot contains the name.
        for query, city, specific in [("vincom", None, False), ("Vincom Mega Mall Royal City", "Hà Nội", True)]:
            tick = time.perf_counter()
            result = vietmap_client.resolve_address(query, role="destination", address_city=city, metadata={})
            check("live_map: " + query,
                  result.get("tool_status") == "AMBIGUOUS" if not specific else result.get("tool_status") == "SUCCESS" and "royal city" in normalize_geo_key(result.get("formatted") or ""),
                  tool_status=result.get("tool_status"), formatted=result.get("formatted"),
                  candidates=result.get("candidates"), latency_seconds=round(time.perf_counter() - tick, 3))

        with tempfile.TemporaryDirectory(prefix="parrotgo_live_") as directory:
            runner = SessionRunner("0000000000", "Live API check", city="toàn quốc", db_path=str(Path(directory) / "booking.db"))
            step(runner, "chào")
            state, _ = step(runner, "đi vincom")
            destination = state.get("booking_slots", {}).get("destination", {})
            check("generic_vincom_needs_clarification", destination.get("status") == "needs_clarification" and not destination.get("formatted"))
            state, clarification = step(runner, "Hà Nội")
            destination = state.get("booking_slots", {}).get("destination", {})
            check("city_keeps_branch_ambiguous", destination.get("status") == "needs_clarification" and "vincom" in normalize_geo_key(destination.get("raw") or "") and not runner.is_session_terminal())
            check("vincom_clarification_is_short", len(clarification.split()) <= 25 and clarification.count("?") == 1 and " hay " not in clarification and "Phường" not in clarification and "Quận" not in clarification, answer=clarification)
            pickup_before_branch = copy.deepcopy(state.get("booking_slots", {}).get("pickup"))
            state, branch_reply = step(runner, "ở Bà Triệu nhé")
            destination = state.get("booking_slots", {}).get("destination", {})
            check("selected_branch_matches", "ba trieu" in normalize_geo_key(destination.get("formatted") or "") and destination.get("status") in {"extracted", "confirmed"})
            check("branch_answer_preserves_pickup", state.get("booking_slots", {}).get("pickup") == pickup_before_branch)
            check("destination_acknowledgement_is_short", len(branch_reply.split()) <= 32 and str(destination.get("formatted") or "") not in branch_reply and "Bà Triệu" in branch_reply, answer=branch_reply)
            state, _ = step(runner, "Đón tôi tại 12 Cầu Giấy, Hà Nội")
            if state.get("booking_slots", {}).get("pickup", {}).get("requires_confirmation"):
                state, _ = step(runner, "Đúng điểm đón đó")
            check("pickup_is_usable", state.get("booking_slots", {}).get("pickup", {}).get("status") in {"extracted", "confirmed"} and state.get("booking_slots", {}).get("pickup", {}).get("location_precision") in {"exact", "anchor"})
            state, _ = step(runner, "xe bảy chỗ à thôi bốn chỗ")
            check("vehicle_last_correction", state.get("booking_slots", {}).get("vehicle_type", {}).get("value") == "oto_4_cho")
            state, _ = step(runner, "mai 9 giờ")
            time_value = state.get("booking_slots", {}).get("pickup_time", {}).get("value")
            expected_date = (parse_aware(reference) + timedelta(days=1)).date()
            try:
                scheduled = parse_aware(time_value)
                correct_time = scheduled.date() == expected_date and scheduled.hour == 9
            except (TypeError, ValueError):
                correct_time = False
            check("tomorrow_9am", correct_time, pickup_time=time_value)
            before = copy.deepcopy(state.get("booking_slots"))
            state, _ = step(runner, "Nãy tôi đặt đi đâu?")
            check("state_question_preserves_booking", state.get("booking_slots") == before and (state.get("qa_response") or {}).get("source") == "session_state")
            state, reply = step(runner, "Có những loại xe nào?")
            qa = state.get("qa_response") or {}
            check("live_faq_uses_approved_source", qa.get("success") and str(qa.get("source", "")).startswith("architecture.md"), answer=reply)
            state, reply = step(runner, "Đúng rồi em")
            with closing(runner.db.get_connection()) as connection:
                count = connection.execute("SELECT count(*) FROM bookings").fetchone()[0]
            check("booking_commits_once", state.get("booking_status") == "booked" and runner.is_session_terminal() and count == 1, booking_count=count)

            cancel = SessionRunner("0000000001", "Live cancel check", city="Hà Nội", db_path=str(Path(directory) / "cancel.db"))
            step(cancel, "Tôi muốn hủy xe")
            state, _ = step(cancel, "Đúng rồi hủy xe giúp tôi")
            check("cancel_confirmation_finishes", state.get("booking_status") == "canceled" and cancel.is_session_terminal())

        for query in ["Có những loại xe nào?", "Có thể hẹn giờ đón không?", "Tôi có thể thêm điểm dừng không?", "Có được mang chó lên xe không?"]:
            result = chroma_faq_client.search_faq_policy(query)
            expected = "chó" not in query
            check("persistent_rag: " + query, bool(result.get("success")) == expected,
                  source=result.get("source"), answer=result.get("answer_text"), metadata=result.get("metadata"))
        report["geography_records"] = len(geo_cache.export_dataset()["places"])
        report["rag_vector_records"] = chroma_faq_client.count()
    except LiveProviderUnavailable:
        check("live_provider_unavailable", False, reason="two_consecutive_nlu_errors")
    except Exception as error:
        check("unhandled_check_error", False, error_type=type(error).__name__)
    report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    report["passed"] = all(item["passed"] for item in checks)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "failed": [item["name"] for item in checks if not item["passed"]], "elapsed_seconds": report["elapsed_seconds"], "report": str(target)}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
