"""Resolve addresses without silently selecting an ambiguous place."""

import copy
import re
from typing import Any

from src.core.state import AddressSlot, BookingSlots, empty_address_slot
from src.db.in_memory_cache import (
    geo_cache,
    normalize_city_key,
    normalize_geo_key,
    strip_city_suffix,
)
from src.services.vietmap_client import (
    GENERIC_BRANDS,
    _explicit_city,
    ambiguous_result,
    vietmap_client,
)


def join_notes(*notes: str | None) -> str | None:
    cleaned: list[str] = []
    for note in notes:
        if isinstance(note, str) and note.strip() and note.strip() not in cleaned:
            cleaned.append(note.strip())
    return "; ".join(cleaned) if cleaned else None


def prepare_address_updates(
    state: Any, city: str | None
) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, Any] | None]:
    prepared: list[tuple[str, dict[str, Any]]] = []
    stopover_operation = None
    existing_stops = (state.get("booking_slots") or {}).get("stopovers", [])
    for update in state.get("turn_extracted_slots", []):
        name = update.get("slot_name", "")
        if name in {"pickup", "destination"}:
            prepared.append((name, update))
        elif name == "stopovers":
            value, meta = update.get("value"), update.get("metadata") or {}
            operation = meta.get("operation", "replace")
            if operation == "clear":
                stopover_operation = {"operation": "clear", "items": []}
            elif isinstance(value, list):
                items = copy.deepcopy(existing_stops) if operation == "append" else []
                offset = len(items)
                for index, raw in enumerate(value, start=offset):
                    if isinstance(raw, dict):
                        sub_update = {
                            "slot_name": f"stopovers:{index}",
                            "value": raw.get("value"),
                            "source_text": raw.get("source_text", ""),
                            "metadata": raw.get("metadata") or {},
                        }
                    else:
                        sub_update = {
                            "slot_name": f"stopovers:{index}",
                            "value": str(raw),
                            "source_text": str(raw),
                            "metadata": {},
                        }
                    address = empty_address_slot()
                    address["raw"] = sub_update["source_text"] or str(
                        sub_update["value"] or ""
                    )
                    items.append({"order": index + 1, "address": address})
                    prepared.append((f"stopovers:{index}", sub_update))
                stopover_operation = {"operation": "replace", "items": items}
        elif name.startswith("stopovers:"):
            prepared.append((name, update))
    # Some LLM responses supply only the city after a clarification question.
    city_updates = [
        u
        for u in state.get("turn_extracted_slots", [])
        if u.get("slot_name") == "session_city"
        and (u.get("metadata") or {}).get("operation") != "clear"
    ]
    if city_updates and city:
        slots = state.get("booking_slots") or {}
        targets = [
            ("pickup", slots.get("pickup") or {}),
            ("destination", slots.get("destination") or {}),
        ]
        targets.extend(
            (f"stopovers:{i}", stop.get("address") or {})
            for i, stop in enumerate(existing_stops)
        )
        already = {target for target, _ in prepared}
        for target, address in targets:
            if (
                target not in already
                and address.get("raw")
                and address.get("status") == "needs_clarification"
            ):
                prepared.append(
                    (
                        target,
                        {
                            "slot_name": target,
                            "value": city,
                            "source_text": city_updates[-1].get("source_text")
                            or str(city),
                            "metadata": {
                                "operation": "augment",
                                "component_type": "city",
                                "address_city": city,
                            },
                        },
                    )
                )
    return prepared, stopover_operation


def _local_candidate(place: dict[str, Any]) -> dict[str, Any]:
    return {
        "place_id": place["place_id"],
        "name": place["canonical_name"],
        "formatted": place["formatted_address"],
        "city": place["city"],
        "coords": {"lat": place["lat"], "lng": place["lng"]},
        "components": place["components"],
        "is_mega_poi": place["is_mega_poi"],
        "location_precision": "poi",
        "source": place["source"],
        "verified": place["verified"],
    }


def _detail_key(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9/ ]", " ", normalize_geo_key(text)).split())


def _clarification_detail_keys(text: str) -> list[str]:
    """Clean only a matching copy; preserve the customer's complete raw/source text."""
    original = _detail_key(text)
    cleaned = original
    while cleaned:
        trimmed = re.sub(
            r"^(?:chi nhanh|dia diem|vi tri|o|tai|da|em|anh|chi|toi|minh|chon)\s+",
            "",
            cleaned,
        )
        trimmed = re.sub(r"\s+(?:nhe|nha|a|em|anh|chi)$", "", trimmed)
        if trimmed == cleaned:
            break
        cleaned = trimmed.strip()
    return list(dict.fromkeys(key for key in [original, cleaned] if key))


def _candidate_matches_detail(
    candidate: dict[str, Any], detail: str, component: str | None
) -> bool:
    if component in {"district", "ward"}:
        area = (
            (candidate.get("components") or {}).get(component)
            or candidate.get(component)
            or ""
        )
        prefix = r"^(?:quan|huyen|thi xa|thanh pho|phuong|xa|thi tran)\s+"
        return bool(area) and re.sub(prefix, "", _detail_key(area)) == re.sub(
            prefix, "", detail
        )
    phrase = re.compile(r"(?:^| )" + re.escape(detail) + r"(?: |$)")
    return any(
        phrase.search(_detail_key(candidate.get(field) or ""))
        for field in ["name", "formatted"]
    )


def _apply_result(slot: AddressSlot, result: dict[str, Any]) -> dict[str, Any]:
    known_city = (slot.get("components") or {}).get("province_city")
    for field in [
        "formatted",
        "coords",
        "components",
        "location_precision",
        "candidates",
        "clarification_kind",
        "place_id",
        "is_mega_poi",
        "requires_confirmation",
    ]:
        if field in result:
            slot[field] = copy.deepcopy(result[field])  # type: ignore[literal-required]
    if known_city and not (slot.get("components") or {}).get("province_city"):
        slot["components"] = {
            **(slot.get("components") or {}),
            "province_city": known_city,
        }
    status = result.get("tool_status", "SUCCESS")
    slot["status"] = "extracted" if status == "SUCCESS" else "needs_clarification"
    return {"slot": slot, "tool_status": status}


def _from_local(
    slot: AddressSlot, place: dict[str, Any], role: str, meta: dict[str, Any]
) -> dict[str, Any]:
    slot.update(
        {
            "place_id": place["place_id"],
            "formatted": place["formatted_address"],
            "coords": {"lat": place["lat"], "lng": place["lng"]},
            "components": copy.deepcopy(place["components"]),
            "is_mega_poi": place["is_mega_poi"],
            "location_precision": "poi",
        }
    )
    slot["note"] = join_notes(
        slot.get("note"), place.get("driver_note"), meta.get("driver_note")
    )
    if role in {"pickup", "stopover"}:
        if slot["is_mega_poi"]:
            gate_hint = meta.get("sub_poi")
            gate = (
                geo_cache.lookup_sub_poi(place["place_id"], str(gate_hint))
                if gate_hint
                else None
            )
            if gate:
                slot.update(
                    {
                        "gate_id": gate["gate_id"],
                        "coords": {"lat": gate["lat"], "lng": gate["lng"]},
                        "gate_resolved": True,
                        "location_precision": "anchor",
                    }
                )
                slot["note"] = join_notes(
                    slot.get("note"), gate.get("driver_instruction")
                )
            else:
                slot["status"] = "needs_clarification"
                slot["clarification_kind"] = "mega_poi_gate"
                return {"slot": slot, "tool_status": "AMBIGUOUS"}
        else:
            slot["location_precision"] = "anchor"
            slot["requires_confirmation"] = True
    slot["status"] = "extracted"
    return {"slot": slot, "tool_status": "SUCCESS"}


def _resolve_candidate(
    slot: AddressSlot,
    candidate: dict[str, Any],
    role: str,
    city: str | None,
    meta: dict[str, Any],
) -> dict[str, Any]:
    if city:
        slot["components"]["province_city"] = city
    place = (
        geo_cache.get_place(candidate.get("place_id"))
        if candidate.get("place_id")
        else None
    )
    if place:
        return _from_local(slot, place, role, meta)
    if candidate.get("ref_id"):
        query = (
            candidate.get("name") or candidate.get("formatted") or slot.get("raw") or ""
        )
        result = vietmap_client.resolve_address(
            query,
            role=role,
            address_city=city,
            metadata={**meta, "selected_candidate": candidate},
        )
        return _apply_result(slot, result)
    # Offline road candidates provide a city, not a safe pickup point.
    result = vietmap_client.resolve_address(
        slot.get("raw") or candidate.get("formatted") or "",
        role=role,
        address_city=candidate.get("city") or city,
        metadata=meta,
    )
    return _apply_result(slot, result)


def resolve_address_update(
    update: dict[str, Any],
    target: str,
    session_city: str | None,
    existing_slots: BookingSlots,
    crm_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    role = "stopover" if target.startswith("stopovers:") else target
    meta = dict(update.get("metadata") or {})
    value = update.get("value")
    source_text = update.get("source_text") or (str(value) if value is not None else "")
    raw_full = meta.get("raw_full") or source_text
    if role == "stopover":
        try:
            index = int(target.split(":", 1)[1])
        except (ValueError, IndexError):
            index = -1
        stops = existing_slots.get("stopovers", [])
        existing = (
            stops[index]["address"] if 0 <= index < len(stops) else empty_address_slot()
        )
    else:
        existing = existing_slots.get(target) or empty_address_slot()
    augment = (
        meta.get("operation") == "augment"
        or meta.get("action") == "disambiguation_resolve"
    )
    slot = empty_address_slot()
    if meta.get("operation") == "clear":
        return {"slot": slot, "tool_status": "SUCCESS"}
    slot["raw"] = (
        f"{existing.get('raw') or ''}, {raw_full}".strip(", ") if augment else raw_full
    )
    slot["note"] = join_notes(
        existing.get("note") if augment else None,
        meta.get("driver_note"),
        f"Hướng: {meta['direction_modifier']}"
        if meta.get("direction_modifier")
        else None,
    )
    query = (
        f"{existing.get('raw') or ''} {value or ''}".strip()
        if augment
        else str(value or raw_full)
    )
    city = (
        meta.get("address_city") or (_explicit_city(str(value or ""))) or session_city
    )
    if augment and meta.get("component_type") == "city":
        city = meta.get("address_city") or str(value)
        city_source = (
            source_text
            if normalize_city_key(source_text) == normalize_city_key(city)
            else str(city)
        )
        slot["raw"] = f"{existing.get('raw') or ''}, {city_source}".strip(", ")
        query = f"{existing.get('raw') or ''} {city}".strip()
    if city:
        slot["components"]["province_city"] = city
    selection = meta.get("candidate_selection")
    candidates = existing.get("candidates") or []
    if isinstance(selection, int) and not isinstance(selection, bool):
        if 0 <= selection < len(candidates):
            selected = candidates[selection]
            return _resolve_candidate(
                slot, selected, role, selected.get("city") or city, meta
            )
        return _apply_result(slot, ambiguous_result(candidates, city))
    if augment and existing.get("place_id") and meta.get("sub_poi"):
        place = geo_cache.get_place(existing["place_id"])
        if place:
            return _from_local(slot, place, role, meta)
    if augment and candidates:
        if meta.get("component_type") == "city":
            matches = [
                candidate
                for candidate in candidates
                if normalize_city_key(candidate.get("city") or "")
                == normalize_city_key(city or "")
            ]
        else:
            matches = []
            for detail in _clarification_detail_keys(str(value or "")):
                matches = [
                    candidate
                    for candidate in candidates
                    if _candidate_matches_detail(
                        candidate, detail, meta.get("component_type")
                    )
                ]
                if matches:
                    break
        if len(matches) == 1 and (
            matches[0].get("place_id") or matches[0].get("ref_id")
        ):
            result = _resolve_candidate(slot, matches[0], role, city, meta)
            if (
                result["tool_status"] == "SUCCESS"
                and meta.get("component_type") == "city"
            ):
                result["slot"]["requires_confirmation"] = True
            return result
        if matches:
            return _apply_result(slot, ambiguous_result(matches, city))
    if meta.get("is_crm_alias"):
        profile = crm_profile or {}
        crm_type = meta.get("crm_alias_type", "")
        crm_target = None
        if crm_type in {"home", "nhà"}:
            crm_target = profile.get("home_address")
        elif crm_type in {"work", "công ty"}:
            crm_target = profile.get("work_address")
        elif crm_type in {"frequent", "frequent_destination", "favorite", "chỗ cũ"}:
            frequent = profile.get("frequent_destinations") or []
            if frequent:
                crm_target = frequent[0].get("address")
        if crm_target:
            slot.update(
                {
                    "formatted": crm_target.get("formatted") or crm_target.get("raw"),
                    "coords": crm_target.get("coords"),
                    "components": copy.deepcopy(crm_target.get("components") or {}),
                    "location_precision": crm_target.get(
                        "location_precision", "unknown"
                    ),
                    "requires_confirmation": True,
                    "status": "extracted",
                }
            )
            return {"slot": slot, "tool_status": "SUCCESS"}
        # Missing home/work information is an address question, never an unrelated favorite.
        return _apply_result(
            slot, {"tool_status": "NOT_FOUND", "clarification_kind": "narrow"}
        )
    local_matches = geo_cache.lookup_poi_alias(query)
    if not local_matches:
        local_matches = geo_cache.lookup_poi_alias(strip_city_suffix(query, city))
    if local_matches:
        filtered = (
            [
                place
                for place in local_matches
                if normalize_city_key(place["city"]) == normalize_city_key(city)
            ]
            if city
            else local_matches
        )
        if not filtered:
            return _apply_result(
                slot,
                ambiguous_result(
                    [_local_candidate(place) for place in local_matches], None, "city"
                ),
            )
        if len(filtered) > 1:
            return _apply_result(
                slot,
                ambiguous_result([_local_candidate(place) for place in filtered], city),
            )
        result = _from_local(slot, filtered[0], role, meta)
        if (
            strip_city_suffix(query, city) in GENERIC_BRANDS
            and result["tool_status"] == "SUCCESS"
        ):
            result["slot"]["requires_confirmation"] = True
        return result
    result = vietmap_client.resolve_address(
        query, role=role, address_city=city, metadata=meta
    )
    if augment and candidates and result.get("tool_status") == "NOT_FOUND":
        return _apply_result(
            slot, ambiguous_result(candidates, city, "narrow" if city else "city")
        )
    return _apply_result(slot, result)
