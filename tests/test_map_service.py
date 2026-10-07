"""Tests for Map Resolver and Vietmap client covering 17 situations."""

from src.core.state import get_initial_booking_slots
from src.services.map_resolver import resolve_address_update
from src.services.vietmap_client import vietmap_client


def test_vietmap_exact_and_anchor():
    res1 = vietmap_client.resolve_address("15 Lê Văn Lương", role="pickup")
    assert res1["tool_status"] == "SUCCESS"
    assert res1["location_precision"] == "exact"
    assert res1["coords"] is not None

    res2 = vietmap_client.resolve_address("Ngõ 78 Cầu Giấy", role="pickup")
    assert res2["tool_status"] == "SUCCESS"
    assert res2["location_precision"] == "anchor"


def test_vietmap_ambiguous_road_without_city():
    res = vietmap_client.resolve_address("Đường Nguyễn Trãi", role="pickup", address_city=None)
    assert res["tool_status"] == "AMBIGUOUS"
    assert res["clarification_kind"] == "city"
    assert len(res["candidates"]) == 2


def test_map_resolver_crm_profile():
    crm = {
        "phone": "0988888888",
        "home_address": {
            "formatted": "15 Lê Văn Lương, Hà Nội",
            "coords": {"lat": 20.9995, "lng": 105.8082},
            "components": {"province_city": "Hà Nội"},
            "location_precision": "exact",
        },
    }
    update = {
        "slot_name": "pickup",
        "value": "về nhà",
        "metadata": {"is_crm_alias": True, "crm_alias_type": "home"},
    }
    res = resolve_address_update(
        update=update,
        target="pickup",
        session_city="Hà Nội",
        existing_slots=get_initial_booking_slots(),
        crm_profile=crm,
    )
    assert res["tool_status"] == "SUCCESS"
    assert res["slot"]["requires_confirmation"] is True
    assert res["slot"]["formatted"] == "15 Lê Văn Lương, Hà Nội"


def test_map_resolver_api_error_handling():
    update = {
        "slot_name": "pickup",
        "value": "__TRIGGER_API_ERROR__",
        "metadata": {},
    }
    res = resolve_address_update(
        update=update,
        target="pickup",
        session_city="Hà Nội",
        existing_slots=get_initial_booking_slots(),
    )
    assert res["tool_status"] == "API_ERROR"
    assert res["slot"]["status"] == "needs_clarification"
