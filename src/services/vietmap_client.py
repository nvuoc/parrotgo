"""Vietmap client supporting both offline mock fixtures and live HTTP API."""

import copy
import re
from typing import Any

import httpx

from src.config import settings
from src.core.time_utils import valid_coords

# Mock fixture database for 17 deterministic testing scenarios
MOCK_VIETMAP_FIXTURES: dict[str, dict[str, Any]] = {
    "15 le van luong": {
        "formatted": "15 Lê Văn Lương, Nhân Chính, Thanh Xuân, Hà Nội",
        "coords": {"lat": 20.9995, "lng": 105.8082},
        "components": {
            "detail": "15",
            "street": "Lê Văn Lương",
            "ward": "Nhân Chính",
            "district": "Thanh Xuân",
            "province_city": "Hà Nội",
        },
        "location_precision": "exact",
        "tool_status": "SUCCESS",
        "candidates": [],
    },
    "12 cau giay": {
        "formatted": "12 Cầu Giấy, Quan Hoa, Cầu Giấy, Hà Nội",
        "coords": {"lat": 21.0315, "lng": 105.7985},
        "components": {
            "detail": "12",
            "street": "Cầu Giấy",
            "ward": "Quan Hoa",
            "district": "Cầu Giấy",
            "province_city": "Hà Nội",
        },
        "location_precision": "exact",
        "tool_status": "SUCCESS",
        "candidates": [],
    },
    "ngo 78 cau giay": {
        "formatted": "Ngõ 78 Cầu Giấy, Quan Hoa, Cầu Giấy, Hà Nội",
        "coords": {"lat": 21.0320, "lng": 105.7990},
        "components": {
            "street": "Ngõ 78 Cầu Giấy",
            "ward": "Quan Hoa",
            "district": "Cầu Giấy",
            "province_city": "Hà Nội",
        },
        "location_precision": "anchor",
        "tool_status": "SUCCESS",
        "candidates": [],
    },
    "benh vien 108": {
        "formatted": "Bệnh viện Trung ương Quân đội 108, 1 Trần Hưng Đạo, Hai Bà Trưng, Hà Nội",
        "coords": {"lat": 21.0185, "lng": 105.8595},
        "components": {
            "detail": "1",
            "street": "Trần Hưng Đạo",
            "ward": "Bạch Đằng",
            "district": "Hai Bà Trưng",
            "province_city": "Hà Nội",
        },
        "location_precision": "exact",
        "tool_status": "SUCCESS",
        "candidates": [],
    },
    "vien 108": {
        "formatted": "Bệnh viện Trung ương Quân đội 108, 1 Trần Hưng Đạo, Hai Bà Trưng, Hà Nội",
        "coords": {"lat": 21.0185, "lng": 105.8595},
        "components": {
            "detail": "1",
            "street": "Trần Hưng Đạo",
            "ward": "Bạch Đằng",
            "district": "Hai Bà Trưng",
            "province_city": "Hà Nội",
        },
        "location_precision": "exact",
        "tool_status": "SUCCESS",
        "candidates": [],
    },
    "san bay noi bai": {
        "formatted": "Sân bay Quốc tế Nội Bài, Phú Cường, Sóc Sơn, Hà Nội",
        "coords": {"lat": 21.2212, "lng": 105.8072},
        "components": {
            "ward": "Phú Cường",
            "district": "Sóc Sơn",
            "province_city": "Hà Nội",
        },
        "location_precision": "poi",
        "is_mega_poi": True,
        "place_id": "noi_bai",
        "tool_status": "SUCCESS",
        "candidates": [],
    },
    "noi bai": {
        "formatted": "Sân bay Quốc tế Nội Bài, Phú Cường, Sóc Sơn, Hà Nội",
        "coords": {"lat": 21.2212, "lng": 105.8072},
        "components": {
            "ward": "Phú Cường",
            "district": "Sóc Sơn",
            "province_city": "Hà Nội",
        },
        "location_precision": "poi",
        "is_mega_poi": True,
        "place_id": "p_noi_bai",
        "tool_status": "SUCCESS",
        "candidates": [],
    },
    "ga ha noi": {
        "formatted": "Ga Hà Nội, 120 Lê Duẩn, Văn Miếu, Đống Đa, Hà Nội",
        "coords": {"lat": 21.0245, "lng": 105.8415},
        "components": {
            "detail": "120",
            "street": "Lê Duẩn",
            "ward": "Văn Miếu",
            "district": "Đống Đa",
            "province_city": "Hà Nội",
        },
        "location_precision": "exact",
        "tool_status": "SUCCESS",
        "candidates": [],
    },
    "ho guom": {
        "formatted": "Hồ Gươm, Hoàn Kiếm, Hà Nội",
        "coords": {"lat": 21.0285, "lng": 105.8542},
        "components": {
            "district": "Hoàn Kiếm",
            "province_city": "Hà Nội",
        },
        "location_precision": "poi",
        "tool_status": "SUCCESS",
        "candidates": [],
    },
    "bo ho": {
        "formatted": "Hồ Gươm, Hoàn Kiếm, Hà Nội",
        "coords": {"lat": 21.0285, "lng": 105.8542},
        "components": {
            "district": "Hoàn Kiếm",
            "province_city": "Hà Nội",
        },
        "location_precision": "poi",
        "tool_status": "SUCCESS",
        "candidates": [],
    },
    "times city": {
        "formatted": "Vinhomes Times City, 458 Minh Khai, Hai Bà Trưng, Hà Nội",
        "coords": {"lat": 20.995, "lng": 105.867},
        "components": {
            "detail": "458",
            "street": "Minh Khai",
            "district": "Hai Bà Trưng",
            "province_city": "Hà Nội",
        },
        "location_precision": "poi",
        "is_mega_poi": True,
        "place_id": "times_city",
        "tool_status": "SUCCESS",
        "candidates": [],
    },
    "bao tang ha noi": {
        "formatted": "Bảo tàng Hà Nội, Phạm Hùng, Mễ Trì, Nam Từ Liêm, Hà Nội",
        "coords": {"lat": 21.0112, "lng": 105.7865},
        "components": {
            "street": "Phạm Hùng",
            "ward": "Mễ Trì",
            "district": "Nam Từ Liêm",
            "province_city": "Hà Nội",
        },
        "location_precision": "poi",
        "tool_status": "SUCCESS",
        "candidates": [],
    },
    "ha noi": {
        "formatted": "Thành phố Hà Nội",
        "coords": None,
        "components": {
            "province_city": "Hà Nội",
        },
        "location_precision": "ward",
        "tool_status": "AMBIGUOUS",
        "candidates": [],
    },
}


def normalize_lookup_key(text: str) -> str:
    """Normalize text for mock matching."""
    from src.db.in_memory_cache import normalize_geo_key

    return normalize_geo_key(text)


GENERIC_BRANDS = {
    "vincom",
    "vincom center",
    "vincom plaza",
    "vincom mega mall",
    "aeon",
    "aeon mall",
    "lotte",
}


def _text_key(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9/ ]", " ", normalize_lookup_key(text)).split())


def _explicit_city(raw_address: str) -> str | None:
    key = _text_key(raw_address)
    for suffix, city in [
        ("ho chi minh", "TP. Hồ Chí Minh"),
        ("tphcm", "TP. Hồ Chí Minh"),
        ("hcm", "TP. Hồ Chí Minh"),
        ("sai gon", "TP. Hồ Chí Minh"),
        ("ha noi", "Hà Nội"),
        ("da nang", "Đà Nẵng"),
        ("hai phong", "Hải Phòng"),
        ("can tho", "Cần Thơ"),
    ]:
        if key == suffix or key.endswith(" " + suffix):
            return city
    return None


def _result(tool_status: str, **fields: Any) -> dict[str, Any]:
    return {
        "formatted": None,
        "coords": None,
        "components": {},
        "location_precision": "unknown",
        "tool_status": tool_status,
        "candidates": [],
        **fields,
    }


def ambiguous_result(
    candidates: list[dict[str, Any]], city: str | None = None, kind: str | None = None
) -> dict[str, Any]:
    """Match flowchart: Filter Top 2 if city is present."""
    if city and len(candidates) > 2:
        candidates = candidates[:2]

    if not kind:
        kind = "city" if not city else "ab" if len(candidates) == 2 else "narrow"
    elif kind == "ab" and len(candidates) != 2:
        kind = "city" if not city else "narrow"
    return _result(
        "AMBIGUOUS",
        candidates=list(candidates),
        components={"province_city": city} if city else {},
        clarification_kind=kind,
    )


def _components(place: dict[str, Any]) -> dict[str, Any]:
    components = {
        "detail": place.get("hs_num"),
        "street": place.get("street"),
        "ward": place.get("ward"),
        "district": place.get("district"),
        "province_city": place.get("city"),
    }
    for boundary in place.get("boundaries") or []:
        if not isinstance(boundary, dict):
            continue
        key = {0: "province_city", 1: "district", 2: "ward"}.get(boundary.get("type"))
        if key and not components.get(key):
            components[key] = boundary.get("full_name") or boundary.get("name")
    return components


def _candidate(place: dict[str, Any]) -> dict[str, Any]:
    components = _components(place)
    return {
        "ref_id": place.get("ref_id"),
        "name": place.get("name"),
        "formatted": place.get("display") or place.get("name") or place.get("address"),
        "city": components.get("province_city"),
        "components": components,
    }


ADMIN_PREFIX = re.compile(
    r"^(?:thanh pho|tp|tinh|quan|huyen|thi xa|tx|phuong|xa|thi tran|duong|pho)\s+",
    re.IGNORECASE,
)


def _strip_admin_prefix(text: str) -> str:
    cleaned = text.strip()
    while True:
        sub = ADMIN_PREFIX.sub("", cleaned).strip()
        if sub == cleaned:
            break
        cleaned = sub
    return cleaned


def _strip_house_prefix(text: str) -> str:
    return re.sub(r"^(?:so\s+nha|so|nha)\s+", "", text.strip(), flags=re.IGNORECASE)


def _normalize_alley_notation(text: str) -> str:
    """Normalize deep alley transpositions: 'ngach 51/16' -> 'ngach 16 ngo 51'."""
    t = re.sub(r"\b(?:ngach|ngo|hem)\s+(\d+)/(\d+)\b", r"ngach \2 ngo \1", text)
    t = re.sub(r"\bngo\s+(\d+)\s+ngach\s+(\d+)\b", r"ngach \2 ngo \1", t)
    return t


def _match_score(query: str, candidate: dict[str, Any]) -> int:
    """Prefer the named destination itself over a shop whose name contains it."""
    name = _text_key(candidate.get("name") or "")
    query = _text_key(query)
    formatted = _text_key(candidate.get("formatted") or "")
    if formatted == query or formatted.startswith(query + " "):
        return 100
    q_no_so = _strip_house_prefix(query)
    name_no_so = _strip_house_prefix(name)
    house = re.match(r"^(\d+[a-z]?(?:/\d+[a-z]?)*)\b", q_no_so)
    candidate_house = re.match(r"^(\d+[a-z]?(?:/\d+[a-z]?)*)\b", name_no_so)
    if house and (not candidate_house or house.group(1) != candidate_house.group(1)):
        return 0
    if name == query or name_no_so == q_no_so:
        return 100
    norm_name = _normalize_alley_notation(name_no_so)
    norm_query = _normalize_alley_notation(q_no_so)
    if norm_name == norm_query:
        return 100
    clean_name = _strip_admin_prefix(name)
    clean_query = _strip_admin_prefix(query)
    if clean_name and clean_query and clean_name == clean_query:
        return 100
    clean_norm_name = _strip_admin_prefix(norm_name)
    clean_norm_query = _strip_admin_prefix(norm_query)
    if clean_norm_name and clean_norm_query and clean_norm_name == clean_norm_query:
        return 100
    if name and query.startswith(name + " "):
        return 70
    if clean_name and clean_query and clean_query.startswith(clean_name + " "):
        return 70
    if query and name.startswith(query + " "):
        return 85 - min(20, 4 * (len(name.split()) - len(query.split())))
    if clean_query and clean_name and clean_name.startswith(clean_query + " "):
        return 85 - min(20, 4 * (len(clean_name.split()) - len(clean_query.split())))
    if query and query in name:
        return 65 - min(20, 4 * (len(name.split()) - len(query.split())))
    if clean_query and clean_name and clean_query in clean_name:
        return 65 - min(20, 4 * (len(clean_name.split()) - len(clean_query.split())))
    from rapidfuzz import fuzz

    base_fuzz = int(fuzz.ratio(query, name))
    norm_fuzz = int(fuzz.ratio(norm_query, norm_name))
    token_fuzz = int(fuzz.token_set_ratio(clean_query, clean_name))
    return max(base_fuzz, norm_fuzz, token_fuzz)


def _deduplicate_destination_branches(
    candidates: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    """Collapse duplicate mall-center records, while keeping outlets and entrances distinct."""
    from src.db.in_memory_cache import normalize_city_key

    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        name = _text_key(candidate.get("name") or "")
        components = candidate.get("components") or {}
        is_explicit_mall = (
            name.startswith(("vincom ", "aeon mall "))
            and name not in GENERIC_BRANDS
            and (name == _text_key(query) or _text_key(query).startswith(name + " "))
            and ":POI:" in (candidate.get("ref_id") or "").upper()
            and all(
                components.get(field) for field in ["ward", "district", "province_city"]
            )
            and not any(
                word in _text_key(candidate.get("formatted") or "")
                for word in ["cong ", "sanh ", "loi vao"]
            )
        )
        if not is_explicit_mall:
            result.append(candidate)
            continue
        key = (
            name,
            _text_key(components["ward"]),
            _text_key(components["district"]),
            normalize_city_key(components["province_city"]),
        )
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = candidate
            result.append(candidate)
        else:
            # Prefer the center record that includes a street address over a complex-only record.
            display = _text_key(candidate.get("formatted") or "")
            existing_display = _text_key(existing.get("formatted") or "")
            address = display[len(name) :].strip() if display.startswith(name) else ""
            old_address = (
                existing_display[len(name) :].strip()
                if existing_display.startswith(name)
                else ""
            )
            if re.match(r"^\d+[a-z]?\b", address) and not re.match(
                r"^\d+[a-z]?\b", old_address
            ):
                result[result.index(existing)] = candidate
                grouped[key] = candidate
    return result


class VietmapClient:
    def __init__(self, mode: str | None = None, api_key: str | None = None):
        self.mode = mode or settings.MAP_MODE
        self.api_key = api_key or settings.VIETMAP_API_KEY
        if self.mode == "live" and not self.api_key:
            raise ValueError("Live MAP_MODE requires VIETMAP_API_KEY configuration")

    def resolve_address(
        self,
        raw_address: str,
        role: str = "pickup",
        address_city: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = metadata or {}
        if not isinstance(raw_address, str) or not raw_address.strip():
            return _result("NOT_FOUND")
        if "__TRIGGER_API_ERROR__" in raw_address:
            return _result("API_ERROR")
        city = meta.get("address_city") or _explicit_city(raw_address) or address_city
        if self.mode == "mock":
            return self._resolve_mock(raw_address, role, city, meta)
        return self._resolve_live(raw_address, role, city, meta)

    def _resolve_mock(
        self,
        raw_address: str,
        role: str,
        address_city: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        from src.db.in_memory_cache import normalize_city_key, strip_city_suffix

        query = (
            metadata.get("head_alley") or metadata.get("anchor_landmark") or raw_address
        )
        key = normalize_lookup_key(query)
        fixture = MOCK_VIETMAP_FIXTURES.get(key) or MOCK_VIETMAP_FIXTURES.get(
            strip_city_suffix(query, address_city)
        )
        if fixture:
            res = copy.deepcopy(fixture)
            fixture_city = res["components"].get("province_city")
            if (
                address_city
                and fixture_city
                and normalize_city_key(address_city) != normalize_city_key(fixture_city)
            ):
                candidate = {
                    "name": res["formatted"],
                    "formatted": res["formatted"],
                    "city": fixture_city,
                    "components": res["components"],
                    "coords": res["coords"],
                    "location_precision": res["location_precision"],
                    "place_id": res.get("place_id"),
                    "is_mega_poi": res.get("is_mega_poi", False),
                }
                return ambiguous_result([candidate], None, "city")
            if (
                role == "pickup"
                and res["location_precision"] == "poi"
                and not res.get("is_mega_poi")
            ):
                res["location_precision"] = "anchor"
                res["requires_confirmation"] = True
            return res
        road_key = strip_city_suffix(query, address_city)
        road_key = re.sub(r"^duong\s+", "", road_key)
        if road_key in {"nguyen trai", "cau giay", "le van luong"}:
            street = {
                "nguyen trai": "Nguyễn Trãi",
                "cau giay": "Cầu Giấy",
                "le van luong": "Lê Văn Lương",
            }[road_key]
            if not address_city:
                return _result(
                    "AMBIGUOUS",
                    formatted=f"Đường {street}",
                    components={"street": street},
                    location_precision="road",
                    clarification_kind="city",
                    candidates=[
                        {"city": "Hà Nội", "formatted": f"Đường {street}, Hà Nội"},
                        {
                            "city": "TP. Hồ Chí Minh",
                            "formatted": f"Đường {street}, TP. Hồ Chí Minh",
                        },
                    ]
                    if road_key == "nguyen trai"
                    else [],
                )
            return _result(
                "AMBIGUOUS" if role == "pickup" else "SUCCESS",
                formatted=f"Đường {street}, {address_city}",
                components={"street": street, "province_city": address_city},
                location_precision="road",
                clarification_kind="narrow",
            )
        return _result(
            "NOT_FOUND",
            components={"province_city": address_city} if address_city else {},
        )

    def _resolve_live(
        self,
        raw_address: str,
        role: str,
        address_city: str | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        from src.db.in_memory_cache import normalize_city_key, strip_city_suffix

        try:
            with httpx.Client(
                timeout=getattr(settings, "MAP_TIMEOUT_SECONDS", 5.0)
            ) as client:
                selected = metadata.get("selected_candidate")
                if not isinstance(selected, dict) or not selected.get("ref_id"):
                    text = raw_address
                    if address_city and not _explicit_city(raw_address):
                        text = f"{raw_address}, {address_city}"
                    params = {"apikey": self.api_key, "text": text}
                    focus = metadata.get("focus_coords")
                    if valid_coords(focus):
                        params["focus"] = f"{focus['lat']},{focus['lng']}"
                    response = client.get(
                        "https://maps.vietmap.vn/api/search/v3", params=params
                    )
                    if response.status_code != 200:
                        return _result("API_ERROR")
                    data = response.json()
                    rows = (
                        data
                        if isinstance(data, list)
                        else data.get("data", [])
                        if isinstance(data, dict)
                        else []
                    )
                    candidates = [
                        _candidate(row)
                        for row in rows
                        if isinstance(row, dict) and row.get("ref_id")
                    ]
                    if not candidates:
                        return _result("NOT_FOUND")
                    if address_city:
                        filtered = [
                            c
                            for c in candidates
                            if normalize_city_key(c.get("city") or "")
                            == normalize_city_key(address_city)
                        ]
                        if not filtered:
                            return ambiguous_result(candidates, None, "city")
                        candidates = filtered
                    query = (
                        raw_address
                        if any(
                            _strip_admin_prefix(_text_key(c.get("name") or ""))
                            == _strip_admin_prefix(_text_key(raw_address))
                            for c in candidates
                        )
                        else strip_city_suffix(raw_address, address_city)
                    )
                    if role == "destination":
                        candidates = _deduplicate_destination_branches(
                            candidates, query
                        )
                    candidates.sort(key=lambda c: _match_score(query, c), reverse=True)
                    scores = [_match_score(query, c) for c in candidates]
                    house_dominant = False
                    if scores and scores[0] >= 75:
                        house = re.match(r"^(?:so |ngo |ngach |hem |kiet |duong )?(\d+[a-z]?(?:/\d+[a-z]?)*)\b", query)
                        c0_name = _text_key(candidates[0].get("name") or "")
                        c0_house = re.match(r"^(?:so |ngo |ngach |hem |kiet |duong )?(\d+[a-z]?(?:/\d+[a-z]?)*)\b", c0_name)
                        if (
                            house
                            and c0_house
                            and house.group(1) == c0_house.group(1)
                            and (len(scores) == 1 or (scores[0] - scores[1] >= 15))
                        ):
                            house_dominant = True
                    if (
                        _text_key(query) in GENERIC_BRANDS
                        or (scores[0] < 85 and not house_dominant)
                        or (len(scores) > 1 and scores[0] - scores[1] < 12 and not house_dominant)
                    ):
                        return ambiguous_result(candidates, address_city)
                    selected = candidates[0]
                return self._place_result(
                    client, selected, raw_address, role, address_city
                )
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            # Error text/URLs must not escape: provider URLs contain the API key.
            return _result("API_ERROR")

    def _place_result(
        self,
        client: httpx.Client,
        selected: dict[str, Any],
        raw_address: str,
        role: str,
        address_city: str | None,
    ) -> dict[str, Any]:
        from src.db.in_memory_cache import normalize_city_key

        response = client.get(
            "https://maps.vietmap.vn/api/place/v3",
            params={"apikey": self.api_key, "refid": selected["ref_id"]},
        )
        detail: dict[str, Any] = {}
        if response.status_code == 200:
            res_json = response.json()
            if isinstance(res_json, dict):
                detail = res_json
        elif response.status_code == 429:
            # Vietmap place/v3 rate limited (HTTP 429). Fallback to search candidate data.
            detail = {}
        else:
            return _result("API_ERROR")
        components = {
            **(selected.get("components") or {}),
            **{k: v for k, v in _components(detail).items() if v},
        }
        coords = None
        try:
            if detail.get("lat") and detail.get("lng"):
                point = {"lat": float(detail["lat"]), "lng": float(detail["lng"])}
                if valid_coords(point):
                    coords = point
        except (KeyError, TypeError, ValueError):
            pass

        # Fallback approximate coords for known city if place/v3 was rate limited
        if not coords and components.get("province_city"):
            city_low = components["province_city"].lower()
            if "hà nội" in city_low or "ha noi" in city_low:
                coords = {"lat": 21.0285, "lng": 105.8542}
            elif "hồ chí minh" in city_low or "ho chi minh" in city_low:
                coords = {"lat": 10.8231, "lng": 106.6297}
            elif "đà nẵng" in city_low or "da nang" in city_low:
                coords = {"lat": 16.0544, "lng": 108.2022}
            elif "quảng ninh" in city_low or "hạ long" in city_low or "ha long" in city_low:
                coords = {"lat": 20.9505, "lng": 107.0734}
            elif "hải phòng" in city_low or "hai phong" in city_low:
                coords = {"lat": 20.8449, "lng": 106.6881}
            elif "cần thơ" in city_low or "can tho" in city_low:
                coords = {"lat": 10.0452, "lng": 105.7469}
        formatted = detail.get("display") or selected.get("formatted")
        resolved = {
            **selected,
            "formatted": formatted,
            "components": components,
            "city": components.get("province_city"),
            "coords": coords,
        }
        if not components.get("province_city") or (
            address_city
            and normalize_city_key(components["province_city"])
            != normalize_city_key(address_city)
        ):
            return ambiguous_result([resolved], None, "city")
        requested_house = re.match(
            r"^(\d+[a-zA-Z]?(?:/\d+[a-zA-Z]?)*)\b",
            _strip_house_prefix(_text_key(raw_address)),
        )
        if requested_house and _text_key(components.get("detail") or "") != _text_key(
            requested_house.group(1)
        ):
            return ambiguous_result([resolved], address_city)
        reference = selected["ref_id"].upper()
        name = _text_key(selected.get("name") or detail.get("name") or "")
        mega = any(
            token in name
            for token in [
                "vincom",
                "san bay",
                "noi bai",
                "benh vien",
                "ben xe",
                "times city",
                "royal city",
                "aeon",
                "ga ha noi",
            ]
        )
        if ":ENTRY_POINT:" in reference:
            precision = "anchor" if coords else "unknown"
            mega = False
        elif ":POI:" in reference:
            precision = "poi"
        elif ":ADDRESS:" in reference and components.get("detail") and coords:
            precision = "exact"
        elif ":CITY:" in reference or ":WARD:" in reference or ":DIST:" in reference:
            precision = "ward"
        else:
            precision = "road" if components.get("street") else "unknown"
        fields = {
            "formatted": formatted,
            "coords": coords,
            "components": components,
            "location_precision": precision,
            "place_id": selected["ref_id"],
            "is_mega_poi": mega,
        }
        if role in {"pickup", "stopover"}:
            if mega:
                return _result(
                    "AMBIGUOUS", **fields, clarification_kind="mega_poi_gate"
                )
            if precision == "poi" and coords:
                return _result(
                    "SUCCESS",
                    **{**fields, "location_precision": "anchor"},
                    requires_confirmation=True,
                )
            if not coords or precision not in {"exact", "anchor"}:
                return _result("AMBIGUOUS", **fields, clarification_kind="narrow")
            requires_confirm = False
            raw_k = _text_key(raw_address)
            name_k = _text_key(selected.get("name") or "")
            fmt_k = _text_key(formatted or "")
            if raw_k != name_k and not fmt_k.startswith(raw_k + " ") and fmt_k != raw_k:
                requires_confirm = True
            return _result("SUCCESS", **fields, requires_confirmation=requires_confirm)
        return _result("SUCCESS", **fields)


vietmap_client = VietmapClient()
