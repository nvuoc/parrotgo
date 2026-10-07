"""Clarification speech follows map.md 14/84 and planner.md 73/130."""
import copy

import pytest

from src.core.state import get_initial_booking_slots
from src.core.validators import validate_spoken_text
from src.services.templates import render_template_by_action


def render(slot, *, target="destination", kind="ab", metadata=None):
    slots = get_initial_booking_slots()
    if target.startswith("stopovers:"):
        slots["stopovers"] = [{"order": 1, "address": slot}]
    else:
        slots[target] = slot
    before = copy.deepcopy(slots)
    action = {"action_type": "clarify_address", "target_slots": [target], "metadata": {"type": kind, **(metadata or {})}}
    speech = render_template_by_action(action, slots)
    assert slots == before  # Short speech never removes candidates or address data.
    validate_spoken_text(speech)
    assert speech.count("?") == 1
    assert len(speech.split()) <= 25
    return speech


def branch(name, *, district="", ward="", city="Thành Phố Hà Nội"):
    return {"name": name, "formatted": f"{name}, Phường {ward or 'Tràng Tiền'}, Quận {district or 'Hoàn Kiếm'}, {city}", "city": city, "components": {"ward": ward, "district": district, "province_city": city}}


@pytest.mark.parametrize("count", [2, 3, 5])
def test_generic_brand_asks_one_branch_in_known_city_without_listing_candidates(count):
    candidates = [branch(name) for name in ["Vincom Center Bà Triệu", "Vincom Center Nguyễn Chí Thanh", "Vincom Royal City", "Vincom Times City", "Vincom Long Biên"][:count]]
    speech = render({"raw": "Vincom", "components": {"province_city": "Thành Phố Hà Nội"}, "candidates": candidates}, kind="ab" if count == 2 else "narrow")
    assert speech == "Dạ mình muốn đến Vincom chi nhánh nào ở Hà Nội ạ?"
    assert "hay" not in speech
    assert all(candidate["name"] not in speech for candidate in candidates)


def test_generic_brand_uses_uniform_candidate_city_when_slot_city_missing():
    speech = render({"raw": "Vincom, Hà Nội", "components": {}, "candidates": [branch("Vincom Bà Triệu"), branch("Vincom Nguyễn Chí Thanh")]})
    assert speech == "Dạ mình muốn đến Vincom chi nhánh nào ở Hà Nội ạ?"


def test_city_stage_asks_only_city_and_never_guesses_two_provinces():
    speech = render({"raw": "Vincom", "components": {}, "candidates": [branch("Vincom Bà Triệu"), branch("Vincom Đồng Khởi", city="Thành Phố Hồ Chí Minh")]}, kind="city")
    assert speech == "Dạ địa điểm này thuộc tỉnh hoặc thành phố nào ạ?"
    assert "Hà Nội" not in speech and "Hồ Chí Minh" not in speech


def test_two_homonymous_roads_read_only_the_differing_district():
    speech = render({"raw": "Nguyễn Trãi", "components": {"province_city": "Hà Nội"}, "candidates": [branch("Đường Nguyễn Trãi", district="Thanh Xuân", ward="Nhân Chính"), branch("Đường Nguyễn Trãi", district="Hà Đông", ward="Mộ Lao")]}, target="pickup")
    assert "Thanh Xuân hay Hà Đông" in speech
    assert all(text not in speech for text in ["Nhân Chính", "Mộ Lao", "Đường Nguyễn Trãi", "Hà Nội"])


def test_two_same_district_roads_read_only_differing_ward():
    speech = render({"raw": "Nguyễn Trãi", "components": {"province_city": "Hà Nội"}, "candidates": [branch("Đường Nguyễn Trãi", district="Thanh Xuân", ward="Nhân Chính"), branch("Đường Nguyễn Trãi", district="Thanh Xuân", ward="Khương Trung")]})
    assert "Nhân Chính hay Khương Trung" in speech
    assert "Thanh Xuân" not in speech and "Hà Nội" not in speech


@pytest.mark.parametrize("kind", ["ab", "narrow"])
def test_more_than_two_road_candidates_ask_one_district_without_listing_places(kind):
    candidates = [branch("Đường Nguyễn Trãi", district=district, ward=f"Phường {i}") for i, district in enumerate(["Thanh Xuân", "Hà Đông", "Đống Đa"])]
    speech = render({"raw": "Nguyễn Trãi", "components": {"province_city": "Hà Nội"}, "candidates": candidates}, kind=kind)
    assert speech == "Dạ địa điểm này ở quận hoặc huyện nào ạ?"
    assert "hay" not in speech
    assert all(candidate["components"]["district"] not in speech for candidate in candidates)


def test_more_than_two_candidates_in_one_district_ask_only_ward():
    candidates = [branch("Đường Nguyễn Trãi", district="Thanh Xuân", ward=ward) for ward in ["Nhân Chính", "Khương Trung", "Thanh Xuân Trung"]]
    speech = render({"raw": "Nguyễn Trãi", "components": {"province_city": "Hà Nội"}, "candidates": candidates}, kind="narrow")
    assert speech == "Dạ địa điểm này ở phường hoặc xã nào ạ?"
    assert "Nhân Chính" not in speech


def test_uninformative_candidates_ask_one_landmark_without_fake_a_b():
    speech = render({"raw": "địa điểm khách nói", "components": {"province_city": "Hà Nội"}, "candidates": [branch("địa điểm khách nói") for _ in range(3)]}, kind="narrow")
    assert speech == "Dạ mình cho em một mốc dễ tìm gần điểm đến này ạ?"
    assert "vị trí A" not in speech and "vị trí B" not in speech


def test_destination_missing_city_does_not_ask_street_ward_and_city_together():
    speech = render({"raw": "một địa điểm", "components": {}, "candidates": []}, kind="narrow")
    assert speech == "Dạ địa điểm này thuộc tỉnh hoặc thành phố nào ạ?"
    assert "đường" not in speech and "phường" not in speech


def test_gate_question_uses_poi_name_without_full_administrative_chain():
    speech = render({"raw": "Times City", "formatted": "Times City, 458 Minh Khai, Phường Vĩnh Tuy, Quận Hai Bà Trưng, Thành Phố Hà Nội", "components": {"province_city": "Hà Nội"}}, target="pickup", kind="mega_poi_gate")
    assert "Times City" in speech
    assert all(value not in speech for value in ["458", "Vĩnh Tuy", "Hai Bà Trưng", "Hà Nội"])


def test_short_acknowledgment_before_pickup_question_keeps_selected_branch():
    slots = get_initial_booking_slots()
    slots["destination"].update(raw="Vincom Bà Triệu", formatted="Vincom Center Bà Triệu, 191 Bà Triệu, Phường Lê Đại Hành, Quận Hai Bà Trưng, Thành Phố Hà Nội")
    speech = render_template_by_action({"action_type": "ask_slot", "target_slots": ["pickup"], "metadata": {"type": "explain_destination_ask_pickup"}}, slots)
    assert "Vincom Center Bà Triệu" in speech
    assert all(text not in speech for text in ["191", "Lê Đại Hành", "Hai Bà Trưng", "Hà Nội"])
    assert speech.count("?") == 1 and len(speech.split()) <= 32
    assert "đón" in speech


def test_final_confirmation_keeps_details_customer_must_confirm():
    slots = get_initial_booking_slots()
    slots["pickup"].update(raw="12 Cầu Giấy", formatted="12 Cầu Giấy, Phường Quan Hoa, Quận Cầu Giấy, Hà Nội")
    slots["destination"].update(raw="Vincom Bà Triệu", formatted="Vincom Bà Triệu, 191 Bà Triệu, Hà Nội")
    slots["vehicle_type"].update(value="oto_4_cho", status="extracted")
    speech = render_template_by_action({"action_type": "confirm_booking", "target_slots": ["pickup", "destination", "vehicle_type", "pickup_time"], "metadata": {}}, slots)
    assert "12 Cầu Giấy" in speech and "191 Bà Triệu" in speech
    assert "Thông tin này đã đúng chưa" in speech


def test_stopover_clarification_is_one_question_and_preserves_target():
    speech = render({"raw": "Vincom", "components": {"province_city": "Hà Nội"}, "candidates": [branch("Vincom Bà Triệu"), branch("Vincom Royal City")]}, target="stopovers:0")
    assert speech == "Dạ mình muốn dừng chân Vincom chi nhánh nào ở Hà Nội ạ?"
