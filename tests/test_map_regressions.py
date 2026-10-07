"""Regression cases for ambiguous places, exact house numbers, gates and persistence."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.core.state import empty_address_slot, get_initial_booking_slots
from src.core.validators import address_ready
from src.db.in_memory_cache import GeoCache
from src.services import map_resolver
from src.services.map_resolver import prepare_address_updates, resolve_address_update
from src.services.vietmap_client import VietmapClient


@pytest.fixture
def seeded_cache(monkeypatch):
    cache = GeoCache()
    dataset = json.loads(Path("data/seed_data/places.json").read_text(encoding="utf-8"))
    cache.upsert_dataset(dataset)
    monkeypatch.setattr(map_resolver, "geo_cache", cache)
    return cache


def search_place(name, ref="vm:POI:test", city="Thành Phố Hà Nội", address=None):
    return {
        "ref_id": ref,
        "name": name,
        "display": address or f"{name}, {city}",
        "boundaries": [{"type": 0, "full_name": city}],
    }


def fake_http(monkeypatch, searches, details, detail_status=200):
    calls = []

    class Response:
        def __init__(self, payload, status=200):
            self.payload, self.status_code = payload, status

        def json(self):
            return self.payload

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params):
            calls.append(
                (
                    url.rsplit("/", 2)[-2:],
                    {key: value for key, value in params.items() if key != "apikey"},
                )
            )
            if "/search/" in url:
                return Response(searches)
            payload = (
                details.get(params["refid"], {})
                if isinstance(details, dict)
                else details
            )
            return Response(payload, detail_status)

    monkeypatch.setattr("src.services.vietmap_client.httpx.Client", Client)
    return calls


@pytest.mark.parametrize("query", ["115 Lê Văn Lương", "112 Cầu Giấy"])
def test_mock_does_not_change_house_number(query):
    result = VietmapClient(mode="mock").resolve_address(query, address_city="Hà Nội")
    assert result["tool_status"] != "SUCCESS"
    assert result["coords"] is None


def test_mock_street_without_house_number_is_not_exact():
    result = VietmapClient(mode="mock").resolve_address(
        "Cầu Giấy", address_city="Hà Nội"
    )
    assert result["tool_status"] == "AMBIGUOUS"
    assert result["location_precision"] == "road"
    assert result["coords"] is None


def test_mock_accepts_matching_city_suffix_but_rejects_other_city():
    client = VietmapClient(mode="mock")
    assert client.resolve_address("12 Cầu Giấy, Hà Nội")["tool_status"] == "SUCCESS"
    wrong = client.resolve_address("12 Cầu Giấy", address_city="TP. Hồ Chí Minh")
    assert wrong["tool_status"] == "AMBIGUOUS"
    assert wrong["formatted"] is None
    assert wrong["clarification_kind"] == "city"


def test_city_augmentation_preserves_road_in_mock():
    result = VietmapClient(mode="mock").resolve_address(
        "Đường Nguyễn Trãi Hà Nội", role="destination", address_city="Hà Nội"
    )
    assert result["components"]["street"] == "Nguyễn Trãi"
    assert result["formatted"] != "Thành phố Hà Nội"


def test_live_generic_brand_does_not_select_milano(monkeypatch):
    places = [
        search_place("Milano Vincom", city="Tỉnh Quảng Trị"),
        search_place("Vincom Bà Triệu", ref="vm:POI:second"),
    ]
    calls = fake_http(monkeypatch, places, {})
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        "vincom", role="destination"
    )
    assert result["tool_status"] == "AMBIGUOUS"
    assert result["formatted"] is None
    assert len(result["candidates"]) == 2
    assert len(calls) == 1


def test_live_prefers_the_mall_over_a_shop_inside_it(monkeypatch):
    places = [
        search_place("Mango Vincom Center Bà Triệu", ref="vm:POI:shop"),
        search_place("Vincom Center Bà Triệu", ref="vm:POI:mall"),
    ]
    calls = fake_http(
        monkeypatch,
        places,
        {
            "vm:POI:mall": {
                "city": "Thành Phố Hà Nội",
                "hs_num": "191",
                "street": "Phố Bà Triệu",
                "lat": 21.010879,
                "lng": 105.849579,
            }
        },
    )
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        "Vincom Center Bà Triệu", role="destination", address_city="Hà Nội"
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["place_id"] == "vm:POI:mall"
    assert result["location_precision"] == "poi"
    assert result["is_mega_poi"] is True
    assert "focus" not in calls[0][1]
    assert calls[0][1]["text"].endswith("Hà Nội")
    assert len(calls) == 2


def test_live_exact_house_beats_similar_house_numbers(monkeypatch):
    places = [
        search_place("12 Cầu Giấy", ref="vm:ADDRESS:12"),
        search_place("112 Cầu Giấy", ref="vm:ADDRESS:112"),
        search_place("2B Cầu Giấy", ref="vm:ADDRESS:2B"),
    ]
    calls = fake_http(
        monkeypatch,
        places,
        {
            "vm:ADDRESS:12": {
                "city": "Thành Phố Hà Nội",
                "hs_num": "12",
                "street": "Cầu Giấy",
                "lat": 21.03,
                "lng": 105.8,
            }
        },
    )
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        "12 Cầu Giấy, Hà Nội", address_city="Hà Nội"
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["location_precision"] == "exact"
    assert calls[-1][1]["refid"] == "vm:ADDRESS:12"


def test_live_house_number_disagreement_is_not_accepted(monkeypatch):
    fake_http(
        monkeypatch,
        [search_place("115 Lê Văn Lương", ref="vm:ADDRESS:115")],
        {
            "vm:ADDRESS:115": {
                "city": "Thành Phố Hà Nội",
                "hs_num": "15",
                "street": "Lê Văn Lương",
                "lat": 21.0,
                "lng": 105.8,
            }
        },
    )
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        "115 Lê Văn Lương", address_city="Hà Nội"
    )
    assert result["tool_status"] == "AMBIGUOUS"
    assert result["formatted"] is None


def test_live_business_full_address_disambiguates_same_name(monkeypatch):
    places = [
        search_place(
            "FPT Shop", ref="vm:POI:45", address="FPT Shop 45 Thái Hà, Hà Nội"
        ),
        search_place(
            "FPT Shop", ref="vm:POI:216", address="FPT Shop 216 Thái Hà, Hà Nội"
        ),
    ]
    calls = fake_http(
        monkeypatch,
        places,
        {
            "vm:POI:45": {
                "city": "Hà Nội",
                "hs_num": "45",
                "street": "Thái Hà",
                "lat": 21.01,
                "lng": 105.81,
            }
        },
    )
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        "FPT Shop 45 Thái Hà, Hà Nội", address_city="Hà Nội"
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["location_precision"] == "anchor"
    assert result["requires_confirmation"] is True
    assert calls[-1][1]["refid"] == "vm:POI:45"


def test_live_city_mismatch_does_not_fetch_guessed_place(monkeypatch):
    calls = fake_http(
        monkeypatch, [search_place("Vincom Bà Triệu", city="Tỉnh Quảng Trị")], {}
    )
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        "Vincom Bà Triệu", role="destination", address_city="Hà Nội"
    )
    assert result["tool_status"] == "AMBIGUOUS"
    assert result["clarification_kind"] == "city"
    assert result["formatted"] is None
    assert len(calls) == 1


def test_live_road_coordinate_does_not_become_exact_pickup(monkeypatch):
    fake_http(
        monkeypatch,
        [search_place("Đường Nguyễn Trãi", ref="vm:STREET:road")],
        {
            "vm:STREET:road": {
                "city": "Hà Nội",
                "street": "Nguyễn Trãi",
                "lat": 21.0,
                "lng": 105.8,
            }
        },
    )
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        "Đường Nguyễn Trãi", address_city="Hà Nội"
    )
    assert result["tool_status"] == "AMBIGUOUS"
    assert result["location_precision"] == "road"


def test_live_place_failure_is_api_error(monkeypatch):
    fake_http(
        monkeypatch,
        [search_place("12 Cầu Giấy", ref="vm:ADDRESS:12")],
        {},
        detail_status=503,
    )
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        "12 Cầu Giấy", address_city="Hà Nội"
    )
    assert result["tool_status"] == "API_ERROR"


def test_cached_brand_requires_branch_before_accepting(seeded_cache):
    result = resolve_address_update(
        {"slot_name": "destination", "value": "Vincom"},
        "destination",
        None,
        get_initial_booking_slots(),
    )
    assert result["tool_status"] == "AMBIGUOUS"
    assert result["slot"]["formatted"] is None
    assert len(result["slot"]["candidates"]) == 3
    assert not address_ready(result["slot"], "destination")


def test_cached_candidates_support_index_selection_without_api(
    seeded_cache, monkeypatch
):
    slots = get_initial_booking_slots()
    slots["destination"] = resolve_address_update(
        {"value": "Vincom"}, "destination", "Hà Nội", slots
    )["slot"]
    monkeypatch.setattr(
        map_resolver.vietmap_client,
        "resolve_address",
        lambda *args, **kwargs: pytest.fail(
            "cached selection must not call external geocoder"
        ),
    )
    result = resolve_address_update(
        {"value": "2", "metadata": {"candidate_selection": 1}},
        "destination",
        "Hà Nội",
        slots,
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["slot"]["place_id"] == "vincom_royal_city_hn"
    assert result["slot"]["requires_confirmation"] is False
    assert address_ready(result["slot"], "destination")


def test_city_clarification_filters_cached_branches(seeded_cache):
    slots = get_initial_booking_slots()
    slots["destination"] = resolve_address_update(
        {"value": "Vincom"}, "destination", None, slots
    )["slot"]
    result = resolve_address_update(
        {
            "value": "Hà Nội",
            "metadata": {"operation": "augment", "component_type": "city"},
        },
        "destination",
        "Hà Nội",
        slots,
    )
    assert result["tool_status"] == "AMBIGUOUS"
    assert len(result["slot"]["candidates"]) == 2
    assert result["slot"]["formatted"] is None


def test_one_cached_branch_is_a_proposal_for_generic_brand(seeded_cache):
    result = resolve_address_update(
        {"value": "Vincom"}, "destination", "TP.HCM", get_initial_booking_slots()
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["slot"]["place_id"] == "vincom_thu_duc_hcm"
    assert result["slot"]["requires_confirmation"] is True
    assert not address_ready(result["slot"], "destination")


def test_gate_coordinate_has_anchor_precision_and_is_ready(seeded_cache):
    dataset = seeded_cache.export_dataset()
    for gate in dataset["gates"]:
        gate["verified"] = True  # Test-only verified operator data.
    seeded_cache.upsert_dataset(dataset)
    result = resolve_address_update(
        {"value": "Times City", "metadata": {"sub_poi": "Cổng T1"}},
        "pickup",
        "Hà Nội",
        get_initial_booking_slots(),
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["slot"]["gate_resolved"] is True
    assert result["slot"]["location_precision"] == "anchor"
    assert address_ready(result["slot"], "pickup")


def test_gate_followup_uses_existing_place_not_a_new_geocode(seeded_cache):
    dataset = seeded_cache.export_dataset()
    for gate in dataset["gates"]:
        gate["verified"] = True
    seeded_cache.upsert_dataset(dataset)
    slots = get_initial_booking_slots()
    slots["pickup"] = resolve_address_update(
        {"value": "Times City"}, "pickup", "Hà Nội", slots
    )["slot"]
    result = resolve_address_update(
        {
            "value": "Cổng T1",
            "metadata": {"operation": "augment", "sub_poi": "Cổng T1"},
        },
        "pickup",
        "Hà Nội",
        slots,
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["slot"]["gate_id"] == "times_gate_t1"
    assert address_ready(result["slot"], "pickup")


def test_demo_gate_is_not_a_verified_pickup(seeded_cache):
    result = resolve_address_update(
        {"value": "Times City", "metadata": {"sub_poi": "Cổng T1"}},
        "pickup",
        "Hà Nội",
        get_initial_booking_slots(),
    )
    assert result["tool_status"] == "AMBIGUOUS"
    assert result["slot"]["gate_resolved"] is False
    assert not address_ready(result["slot"], "pickup")


def test_snapshot_survives_a_separate_process(seeded_cache, tmp_path):
    snapshot = tmp_path / "places.json"
    seeded_cache.persist_snapshot(snapshot)
    program = "from src.db.in_memory_cache import GeoCache; import sys; cache=GeoCache(); assert cache.hydrate_snapshot(sys.argv[1]); print(len(cache.lookup_poi_alias('vincom', city='TP.HCM')))"
    result = subprocess.run(
        [sys.executable, "-c", program, str(snapshot)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "1"


def test_invalid_snapshot_does_not_clear_cache(seeded_cache, tmp_path):
    snapshot = tmp_path / "bad.json"
    snapshot.write_text(
        '{"places":[{"place_id":"bad","lat":true,"lng":105.0}]}', encoding="utf-8"
    )
    before = seeded_cache.export_dataset()
    with pytest.raises((TypeError, ValueError)):
        seeded_cache.hydrate_snapshot(snapshot)
    assert seeded_cache.export_dataset() == before


def test_append_stopover_preserves_existing_order():
    slots = get_initial_booking_slots()
    old = empty_address_slot()
    old.update(
        {
            "raw": "12 Cầu Giấy",
            "formatted": "12 Cầu Giấy, Hà Nội",
            "status": "confirmed",
        }
    )
    slots["stopovers"] = [{"order": 1, "address": old}]
    prepared, operation = prepare_address_updates(
        {
            "booking_slots": slots,
            "turn_extracted_slots": [
                {
                    "slot_name": "stopovers",
                    "value": ["15 Lê Văn Lương"],
                    "metadata": {"operation": "append"},
                }
            ],
        },
        "Hà Nội",
    )
    assert prepared[0][0] == "stopovers:1"
    assert operation["items"][0]["address"] == old
    assert [item["order"] for item in operation["items"]] == [1, 2]
    operation["items"][0]["address"]["raw"] = "changed"
    assert slots["stopovers"][0]["address"]["raw"] == "12 Cầu Giấy"


def test_city_only_update_revisits_unresolved_address():
    slots = get_initial_booking_slots()
    slots["pickup"].update(
        {
            "raw": "Đường Nguyễn Trãi",
            "status": "needs_clarification",
            "clarification_kind": "city",
        }
    )
    slots["destination"].update({"raw": "Vincom Thủ Đức", "status": "confirmed"})
    prepared, _ = prepare_address_updates(
        {
            "booking_slots": slots,
            "turn_extracted_slots": [
                {
                    "slot_name": "session_city",
                    "value": "Hà Nội",
                    "source_text": "ở Hà Nội",
                }
            ],
        },
        "Hà Nội",
    )
    assert [target for target, _ in prepared] == ["pickup"]
    assert prepared[0][1]["metadata"]["component_type"] == "city"


def test_city_metadata_has_priority_over_bad_llm_value(seeded_cache):
    slots = get_initial_booking_slots()
    slots["destination"] = resolve_address_update(
        {"value": "Vincom"}, "destination", None, slots
    )["slot"]
    result = resolve_address_update(
        {
            "value": "Vincom Bà Triệu",
            "metadata": {
                "operation": "augment",
                "component_type": "city",
                "address_city": "Hà Nội",
            },
        },
        "destination",
        "Hà Nội",
        slots,
    )
    assert result["tool_status"] == "AMBIGUOUS"
    assert len(result["slot"]["candidates"]) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("verified", "false"),
        ("is_default_pickup", "false"),
        ("lat", True),
        ("lng", False),
    ],
)
def test_import_rejects_fake_gate_verification(seeded_cache, field, value):
    dataset = seeded_cache.export_dataset()
    dataset["gates"][0][field] = value
    with pytest.raises((TypeError, ValueError)):
        seeded_cache.upsert_dataset(dataset)


def test_import_rejects_fake_place_verification(seeded_cache):
    dataset = seeded_cache.export_dataset()
    dataset["places"][0]["verified"] = "false"
    with pytest.raises(TypeError):
        seeded_cache.upsert_dataset(dataset)


def test_city_word_inside_full_poi_name_is_preserved(monkeypatch):
    fake_http(
        monkeypatch,
        [search_place("Ga Hà Nội", ref="vm:POI:station")],
        {
            "vm:POI:station": {
                "city": "Thành Phố Hà Nội",
                "hs_num": "120",
                "street": "Lê Duẩn",
                "lat": 21.0245,
                "lng": 105.8415,
            }
        },
    )
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        "Ga Hà Nội", role="destination"
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["is_mega_poi"] is True
    assert result["place_id"] == "vm:POI:station"


def mall_center(name, ref, address, ward="Phường Thượng Đình"):
    place = search_place(name, ref=ref, address=address)
    place["boundaries"].extend(
        [{"type": 1, "full_name": "Quận Thanh Xuân"}, {"type": 2, "full_name": ward}]
    )
    return place


def test_duplicate_records_for_explicit_mall_destination_are_one_branch(monkeypatch):
    name = "Vincom Mega Mall Royal City"
    centers = [
        mall_center(
            name, "vm:POI:complex", f"{name} Khu Đô Thị Vinhomes Royal City, Hà Nội"
        ),
        mall_center(name, "vm:POI:street", f"{name} 72A Nguyễn Trãi, Hà Nội"),
    ]
    calls = fake_http(
        monkeypatch,
        centers,
        {
            "vm:POI:street": {
                "city": "Thành Phố Hà Nội",
                "ward": "Phường Thượng Đình",
                "district": "Quận Thanh Xuân",
                "hs_num": "72A",
                "street": "Nguyễn Trãi",
                "lat": 21.001124,
                "lng": 105.816667,
            }
        },
    )
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        name, role="destination", address_city="Hà Nội"
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["place_id"] == "vm:POI:street"
    assert len(calls) == 2


@pytest.mark.parametrize(
    "role,ref,ward",
    [
        ("pickup", "vm:POI:other", "Phường Thượng Đình"),
        ("destination", "vm:ENTRY_POINT:gate", "Phường Thượng Đình"),
        ("destination", "vm:POI:other", "Phường Khác"),
    ],
)
def test_duplicate_filter_keeps_pickup_entrances_and_different_outlets(
    monkeypatch, role, ref, ward
):
    name = "Vincom Mega Mall Royal City"
    centers = [
        mall_center(name, "vm:POI:street", f"{name} 72A Nguyễn Trãi, Hà Nội"),
        mall_center(
            name, ref, f"{name} Khu Đô Thị Vinhomes Royal City, Hà Nội", ward=ward
        ),
    ]
    calls = fake_http(monkeypatch, centers, {})
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        name, role=role, address_city="Hà Nội"
    )
    assert result["tool_status"] == "AMBIGUOUS"
    assert len(result["candidates"]) == 2
    assert len(calls) == 1


def test_city_augmentation_does_not_append_hallucinated_raw_full(seeded_cache):
    slots = get_initial_booking_slots()
    slots["destination"] = resolve_address_update(
        {"value": "Vincom"}, "destination", None, slots
    )["slot"]
    result = resolve_address_update(
        {
            "value": "Hà Nội",
            "source_text": "Hà Nội",
            "metadata": {
                "operation": "augment",
                "component_type": "city",
                "raw_full": "vincom",
                "address_city": "Hà Nội",
            },
        },
        "destination",
        "Hà Nội",
        slots,
    )
    assert result["slot"]["raw"] == "Vincom, Hà Nội"


@pytest.mark.parametrize("city,kind", [(None, "city"), ("Hà Nội", "narrow")])
def test_many_candidates_are_retained_and_not_an_ab_choice(city, kind):
    from src.services.vietmap_client import ambiguous_result

    candidates = [
        {
            "name": f"Địa điểm {index}",
            "formatted": f"Địa điểm {index}, Hà Nội",
            "city": "Hà Nội",
        }
        for index in range(9)
    ]
    result = ambiguous_result(candidates, city)
    assert result["clarification_kind"] == kind
    assert result["candidates"] == candidates
    assert result["formatted"] is None
    assert result["components"] == ({"province_city": city} if city else {})


@pytest.mark.parametrize(
    "reply",
    [
        "Bà Triệu nhé",
        "Bà Triệu ạ em",
        "ở Bà Triệu",
        "tại chi nhánh Bà Triệu nhé",
        "em chọn Bà Triệu ạ",
    ],
)
def test_short_branch_reply_ignores_politeness_only_for_matching(seeded_cache, reply):
    slots = get_initial_booking_slots()
    slots["destination"] = resolve_address_update(
        {"value": "Vincom"}, "destination", "Hà Nội", slots
    )["slot"]
    result = resolve_address_update(
        {
            "value": reply,
            "source_text": reply,
            "metadata": {"operation": "augment", "raw_full": reply},
        },
        "destination",
        "Hà Nội",
        slots,
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["slot"]["place_id"] == "vincom_ba_trieu_hn"
    assert reply in result["slot"]["raw"]
    assert slots["pickup"]["status"] == "empty"


def test_unmatched_branch_detail_keeps_existing_candidates(seeded_cache):
    slots = get_initial_booking_slots()
    slots["destination"] = resolve_address_update(
        {"value": "Vincom"}, "destination", "Hà Nội", slots
    )["slot"]
    before = slots["destination"]["candidates"]
    result = resolve_address_update(
        {"value": "chi nhánh gần công viên nhé", "metadata": {"operation": "augment"}},
        "destination",
        "Hà Nội",
        slots,
    )
    assert result["tool_status"] == "AMBIGUOUS"
    assert result["slot"]["clarification_kind"] == "narrow"
    assert result["slot"]["candidates"] == before
    assert result["slot"]["formatted"] is None
    assert result["slot"]["components"]["province_city"] == "Hà Nội"


def test_matching_keeps_third_branch_not_only_first_two(seeded_cache):
    dataset = seeded_cache.export_dataset()
    extra = dict(dataset["places"][2])
    extra.update(
        {
            "place_id": "test_vincom_long_bien",
            "canonical_name": "Vincom Plaza Long Biên",
            "formatted_address": "Vincom Plaza Long Biên, Long Biên, Hà Nội",
            "source": "test_fixture",
            "components": {"district": "Long Biên", "province_city": "Hà Nội"},
        }
    )
    dataset["places"].append(extra)
    dataset["aliases"].append({"alias_key": "vincom", "place_id": extra["place_id"]})
    seeded_cache.upsert_dataset(dataset)
    slots = get_initial_booking_slots()
    slots["destination"] = resolve_address_update(
        {"value": "Vincom"}, "destination", "Hà Nội", slots
    )["slot"]
    assert len(slots["destination"]["candidates"]) == 3
    assert slots["destination"]["clarification_kind"] == "narrow"
    result = resolve_address_update(
        {"value": "Long Biên nhé", "metadata": {"operation": "augment"}},
        "destination",
        "Hà Nội",
        slots,
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["slot"]["place_id"] == "test_vincom_long_bien"


def test_district_one_does_not_match_district_ten(seeded_cache):
    dataset = seeded_cache.export_dataset()
    template = dict(dataset["places"][-1])
    for district in ["1", "10"]:
        place = {
            **template,
            "place_id": f"test_branch_q{district}",
            "canonical_name": f"Test Branch Quận {district}",
            "formatted_address": f"Test Branch, Quận {district}, Hồ Chí Minh",
            "city": "TP. Hồ Chí Minh",
            "source": "test_fixture",
            "components": {
                "district": f"Quận {district}",
                "province_city": "TP. Hồ Chí Minh",
            },
        }
        dataset["places"].append(place)
        dataset["aliases"].append(
            {"alias_key": "test branch", "place_id": place["place_id"]}
        )
    seeded_cache.upsert_dataset(dataset)
    slots = get_initial_booking_slots()
    slots["destination"] = resolve_address_update(
        {"value": "Test Branch"}, "destination", "TP. Hồ Chí Minh", slots
    )["slot"]
    result = resolve_address_update(
        {
            "value": "Quận 1",
            "metadata": {"operation": "augment", "component_type": "district"},
        },
        "destination",
        "TP. Hồ Chí Minh",
        slots,
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["slot"]["place_id"] == "test_branch_q1"


@pytest.mark.parametrize("alias_type", ["home", "work", "unknown"])
def test_missing_crm_alias_does_not_use_unrelated_favorite(
    seeded_cache, monkeypatch, alias_type
):
    favorite = {
        "formatted": "Bệnh viện Bạch Mai, Hà Nội",
        "coords": {"lat": 21.0, "lng": 105.8},
        "components": {"province_city": "Hà Nội"},
        "location_precision": "poi",
    }
    profile = {"frequent_destinations": [{"address": favorite}]}
    monkeypatch.setattr(
        map_resolver.vietmap_client,
        "resolve_address",
        lambda *args, **kwargs: pytest.fail(
            "missing CRM alias must ask for address, not geocode a literal alias"
        ),
    )
    result = resolve_address_update(
        {
            "value": "nhà tôi",
            "metadata": {"is_crm_alias": True, "crm_alias_type": alias_type},
        },
        "destination",
        "Hà Nội",
        get_initial_booking_slots(),
        profile,
    )
    assert result["tool_status"] == "NOT_FOUND"
    assert result["slot"]["formatted"] is None
    assert result["slot"]["coords"] is None
    assert result["slot"]["requires_confirmation"] is False
    assert result["slot"]["components"]["province_city"] == "Hà Nội"


def test_explicit_frequent_alias_can_propose_favorite(seeded_cache):
    favorite = {
        "formatted": "Bệnh viện Bạch Mai, Hà Nội",
        "coords": {"lat": 21.0, "lng": 105.8},
        "components": {"province_city": "Hà Nội"},
        "location_precision": "poi",
    }
    result = resolve_address_update(
        {
            "value": "địa điểm thường đến",
            "metadata": {"is_crm_alias": True, "crm_alias_type": "frequent"},
        },
        "destination",
        "Hà Nội",
        get_initial_booking_slots(),
        {"frequent_destinations": [{"address": favorite}]},
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["slot"]["formatted"] == favorite["formatted"]
    assert result["slot"]["requires_confirmation"] is True


@pytest.mark.parametrize("tool_status", ["NOT_FOUND", "AMBIGUOUS", "API_ERROR"])
def test_known_city_survives_unresolved_provider_result(monkeypatch, tool_status):
    monkeypatch.setattr(
        map_resolver.vietmap_client,
        "resolve_address",
        lambda *args, **kwargs: {
            "tool_status": tool_status,
            "formatted": None,
            "coords": None,
            "components": {},
            "location_precision": "unknown",
        },
    )
    result = resolve_address_update(
        {"value": "đường chưa xác định"},
        "pickup",
        "Hà Nội",
        get_initial_booking_slots(),
    )
    assert result["tool_status"] == tool_status
    assert result["slot"]["components"] == {"province_city": "Hà Nội"}
    assert not address_ready(result["slot"], "pickup")


def test_live_administrative_destination_matches_without_prefix(monkeypatch):
    places = [
        {
            "ref_id": "vm:DIST:315",
            "name": "Thành Phố Hạ Long",
            "display": "Thành Phố Hạ Long,Tỉnh Quảng Ninh",
            "boundaries": [
                {"type": 1, "full_name": "Thành Phố Hạ Long"},
                {"type": 0, "full_name": "Tỉnh Quảng Ninh"},
            ],
        },
        search_place("Quận Hà Đông", ref="vm:DIST:1035", city="Thành Phố Hà Nội"),
        search_place("Huyện Hạ Lang", ref="vm:DIST:1052", city="Tỉnh Cao Bằng"),
    ]
    calls = fake_http(
        monkeypatch,
        places,
        {
            "vm:DIST:315": {
                "city": "Tỉnh Quảng Ninh",
                "district": "Thành Phố Hạ Long",
                "lat": 20.949873,
                "lng": 107.073785,
            }
        },
    )
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        "Hạ Long", role="destination"
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["components"]["province_city"] == "Tỉnh Quảng Ninh"
    assert "Hạ Long" in result["formatted"]
    assert result["location_precision"] == "ward"
    assert len(calls) == 2


def test_live_deep_alley_house_number_matches_and_asks_confirmation(monkeypatch):
    places = [
        {
            "ref_id": "vm:ADDRESS:test_ngoa_long",
            "name": "3 Ngách 16 Ngõ 51 Ngọa Long",
            "display": "3 Ngách 16 Ngõ 51 Ngọa Long Phường Minh Khai,Quận Bắc Từ Liêm,Thành Phố Hà Nội",
            "boundaries": [
                {"type": 2, "full_name": "Phường Minh Khai"},
                {"type": 1, "full_name": "Quận Bắc Từ Liêm"},
                {"type": 0, "full_name": "Thành Phố Hà Nội"},
            ],
        },
        search_place("16 Ngách 16 Ngõ 51 Ngọa Long", ref="vm:ADDRESS:other16"),
        search_place("1 Ngách 16 Ngõ 51 Ngọa Long", ref="vm:ADDRESS:other1"),
    ]
    calls = fake_http(
        monkeypatch,
        places,
        {
            "vm:ADDRESS:test_ngoa_long": {
                "city": "Thành Phố Hà Nội",
                "district": "Quận Bắc Từ Liêm",
                "ward": "Phường Minh Khai",
                "street": "Ngách 51/16 Ngọa Long",
                "hs_num": "3",
                "display": "3 Ngách 51/16 Ngọa Long,Phường Minh Khai,Quận Bắc Từ Liêm,Thành Phố Hà Nội",
                "lat": 21.051487,
                "lng": 105.744222,
            }
        },
    )
    result = VietmapClient(mode="live", api_key="test-key").resolve_address(
        "số 3 ngách 51/16 ngoạ long", role="pickup"
    )
    assert result["tool_status"] == "SUCCESS"
    assert result["location_precision"] == "exact"
    assert result["requires_confirmation"] is True
    assert "3 Ngách 51/16 Ngọa Long" in result["formatted"]
    assert len(calls) == 2


