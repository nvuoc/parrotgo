"""In-memory SQLite geographical cache for places, aliases, gates, and streets."""

import json
import math
import os
import re
import sqlite3
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

CACHE_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS places (
    place_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    formatted_address TEXT NOT NULL,
    city TEXT NOT NULL,
    lat REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lng REAL NOT NULL CHECK (lng BETWEEN -180 AND 180),
    poi_type TEXT NOT NULL,
    is_mega_poi INTEGER NOT NULL CHECK (is_mega_poi IN (0, 1)),
    components_json TEXT NOT NULL,
    driver_note TEXT,
    source TEXT NOT NULL,
    verified INTEGER NOT NULL CHECK (verified IN (0, 1))
);

CREATE TABLE IF NOT EXISTS local_poi_alias (
    alias_key TEXT NOT NULL,
    place_id TEXT NOT NULL REFERENCES places(place_id) ON DELETE CASCADE,
    PRIMARY KEY(alias_key, place_id)
);

CREATE TABLE IF NOT EXISTS mega_poi_gates (
    gate_id TEXT PRIMARY KEY,
    place_id TEXT NOT NULL REFERENCES places(place_id) ON DELETE CASCADE,
    gate_code TEXT NOT NULL,
    gate_key TEXT NOT NULL,
    lat REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lng REAL NOT NULL CHECK (lng BETWEEN -180 AND 180),
    is_default_pickup INTEGER NOT NULL DEFAULT 0 CHECK (is_default_pickup IN (0, 1)),
    is_default_dropoff INTEGER NOT NULL DEFAULT 0 CHECK (is_default_dropoff IN (0, 1)),
    driver_instruction TEXT NOT NULL,
    source TEXT NOT NULL,
    verified INTEGER NOT NULL CHECK (verified IN (0, 1)),
    UNIQUE(place_id, gate_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS unique_default_pickup ON mega_poi_gates(place_id)
    WHERE is_default_pickup = 1;
CREATE UNIQUE INDEX IF NOT EXISTS unique_default_dropoff ON mega_poi_gates(place_id)
    WHERE is_default_dropoff = 1;

CREATE TABLE IF NOT EXISTS city_streets (
    street_id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    street_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    source TEXT NOT NULL,
    verified INTEGER NOT NULL CHECK (verified IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_streets_city ON city_streets(city, normalized_name);
"""


def remove_vietnamese_accents(text: str) -> str:
    """Normalize Vietnamese text to non-accent lowercase."""
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "d")
    return text.lower().strip()


def normalize_geo_key(text: str) -> str:
    """Canonical search key: strip accents, lower, single space."""
    plain = remove_vietnamese_accents(text)
    return " ".join(plain.split())


def normalize_city_key(text: str) -> str:
    """Compare city names across common speech and Vietmap administrative prefixes."""
    key = re.sub(r"[^a-z0-9 ]", " ", normalize_geo_key(text))
    key = " ".join(key.split())
    key = re.sub(r"^(?:thanh pho|tinh|tp)\s+", "", key)
    return {
        "hcm": "ho chi minh",
        "tphcm": "ho chi minh",
        "tp hcm": "ho chi minh",
        "sai gon": "ho chi minh",
        "saigon": "ho chi minh",
        "hn": "ha noi",
    }.get(key, key)


def strip_city_suffix(text: str, city: str | None = None) -> str:
    """Remove an explicit trailing city without weakening address/house-number matching."""
    key = re.sub(r"[,.;]", " ", normalize_geo_key(text))
    key = " ".join(key.split())
    city_names = [normalize_geo_key(city)] if city else []
    city_names.extend(
        [
            "thanh pho ho chi minh",
            "tp. ho chi minh",
            "tp ho chi minh",
            "ho chi minh",
            "tp. hcm",
            "tp hcm",
            "tphcm",
            "hcm",
            "sai gon",
            "thanh pho ha noi",
            "tp ha noi",
            "ha noi",
        ]
    )
    for city_name in sorted(set(city_names), key=len, reverse=True):
        if city_name and key.endswith(" " + city_name):
            return key[: -(len(city_name) + 1)].rstrip(" ,")
    return key


class GeoCache:
    """Single-process in-memory SQLite geographical cache."""

    def __init__(self, conn: sqlite3.Connection | None = None):
        # If no connection is passed, create and keep an open in-memory connection
        self.conn = conn or sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self.conn.executescript(CACHE_SCHEMA_SQL)
        self.conn.commit()

    def validate_dataset(self, dataset: dict[str, Any]) -> None:
        """Validate structure and integrity of dataset before ingestion."""
        if not isinstance(dataset, dict):
            raise TypeError("Geo dataset must be an object")
        for collection in ["places", "aliases", "gates", "streets"]:
            if not isinstance(dataset.get(collection, []), list):
                raise TypeError(f"Geo dataset {collection} must be a list")
        places = dataset.get("places", [])
        aliases = dataset.get("aliases", [])
        gates = dataset.get("gates", [])
        streets = dataset.get("streets", [])

        def flags(record: dict[str, Any], names: list[str]) -> None:
            for name in names:
                if name in record and not isinstance(record[name], bool):
                    raise TypeError(f"{name} must be a JSON boolean")

        def required_text(record: dict[str, Any], names: list[str]) -> None:
            for name in names:
                if not isinstance(record.get(name), str):
                    raise TypeError(f"{name} must be a string")
                if not record[name].strip():
                    raise ValueError(f"{name} must not be empty")

        place_ids = set()
        for p in places:
            if not isinstance(p, dict):
                raise TypeError("Each place must be an object")
            required_text(
                p, ["place_id", "canonical_name", "formatted_address", "city"]
            )
            flags(p, ["verified", "is_mega_poi"])
            if not isinstance(p.get("components", {}), dict):
                raise TypeError("Place components must be an object")
            pid = p.get("place_id")
            if not pid or not isinstance(pid, str):
                raise ValueError(f"Invalid place_id: {pid}")
            if pid in place_ids:
                raise ValueError(f"Duplicate place_id in dataset: {pid}")
            place_ids.add(pid)

            lat, lng = p.get("lat"), p.get("lng")
            if (
                not isinstance(lat, (int, float))
                or not isinstance(lng, (int, float))
                or isinstance(lat, bool)
                or isinstance(lng, bool)
                or not math.isfinite(lat)
                or not math.isfinite(lng)
                or not (-90 <= lat <= 90 and -180 <= lng <= 180)
            ):
                raise ValueError(f"Invalid coords for place {pid}: {lat}, {lng}")

        # Validate aliases
        for a in aliases:
            if not isinstance(a, dict):
                raise TypeError("Each alias must be an object")
            required_text(a, ["alias_key", "place_id"])
            pid = a.get("place_id")
            if pid not in place_ids:
                raise ValueError(f"Alias refers to unknown place_id: {pid}")
            if not a.get("alias_key"):
                raise ValueError("Missing alias_key in alias")

        # Validate gates
        seen_gate_keys = set()
        default_pickups = set()
        default_dropoffs = set()
        for g in gates:
            if not isinstance(g, dict):
                raise TypeError("Each gate must be an object")
            required_text(g, ["gate_id", "place_id", "gate_code", "driver_instruction"])
            flags(g, ["verified", "is_default_pickup", "is_default_dropoff"])
            gid = g.get("gate_id")
            pid = g.get("place_id")
            if not gid or not pid:
                raise ValueError("Gate requires gate_id and place_id")
            if pid not in place_ids:
                raise ValueError(f"Gate {gid} refers to unknown place_id {pid}")

            lat, lng = g.get("lat"), g.get("lng")
            if (
                not isinstance(lat, (int, float))
                or not isinstance(lng, (int, float))
                or isinstance(lat, bool)
                or isinstance(lng, bool)
                or not math.isfinite(lat)
                or not math.isfinite(lng)
                or not (-90 <= lat <= 90 and -180 <= lng <= 180)
            ):
                raise ValueError(f"Invalid coords for gate {gid}: {lat}, {lng}")

            g_code = g.get("gate_code", "")
            g_key = normalize_geo_key(g.get("gate_key") or g_code)
            pair = (pid, g_key)
            if pair in seen_gate_keys:
                raise ValueError(f"Duplicate gate_key '{g_key}' for place {pid}")
            seen_gate_keys.add(pair)

            if g.get("is_default_pickup"):
                if pid in default_pickups:
                    raise ValueError(f"Multiple default pickups for place {pid}")
                default_pickups.add(pid)
            if g.get("is_default_dropoff"):
                if pid in default_dropoffs:
                    raise ValueError(f"Multiple default dropoffs for place {pid}")
                default_dropoffs.add(pid)

        # Validate streets
        street_ids = set()
        for s in streets:
            if not isinstance(s, dict):
                raise TypeError("Each street must be an object")
            required_text(s, ["street_id", "city", "street_name"])
            flags(s, ["verified"])
            sid = s.get("street_id")
            if not sid or sid in street_ids:
                raise ValueError(f"Invalid or duplicate street_id: {sid}")
            street_ids.add(sid)

    def upsert_dataset(self, dataset: dict[str, Any], replace: bool = False) -> None:
        """Atomically upsert places, aliases, gates, and streets."""
        self.validate_dataset(dataset)
        places = dataset.get("places", [])
        aliases = dataset.get("aliases", [])
        gates = dataset.get("gates", [])
        streets = dataset.get("streets", [])

        # Perform atomic transaction
        cursor = self.conn.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION;")
            if replace:
                cursor.execute("DELETE FROM places;")
                cursor.execute("DELETE FROM city_streets;")
            for p in places:
                is_mega = (
                    1
                    if p.get("is_mega_poi")
                    or p.get("poi_type")
                    in {"mega_poi", "airport", "mall", "hospital", "station", "complex"}
                    else 0
                )
                cursor.execute(
                    """
                    INSERT INTO places (
                        place_id, canonical_name, formatted_address, city, lat, lng,
                        poi_type, is_mega_poi, components_json, driver_note, source, verified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(place_id) DO UPDATE SET
                        canonical_name = excluded.canonical_name,
                        formatted_address = excluded.formatted_address,
                        city = excluded.city,
                        lat = excluded.lat,
                        lng = excluded.lng,
                        poi_type = excluded.poi_type,
                        is_mega_poi = excluded.is_mega_poi,
                        components_json = excluded.components_json,
                        driver_note = excluded.driver_note,
                        source = excluded.source,
                        verified = excluded.verified;
                    """,
                    (
                        p["place_id"],
                        p["canonical_name"],
                        p["formatted_address"],
                        p["city"],
                        float(p["lat"]),
                        float(p["lng"]),
                        p.get("poi_type", "poi"),
                        is_mega,
                        json.dumps(p.get("components", {}), ensure_ascii=False),
                        p.get("driver_note"),
                        p.get("source", "manual"),
                        1 if p.get("verified", False) else 0,
                    ),
                )

            for a in aliases:
                key = normalize_geo_key(a["alias_key"])
                cursor.execute(
                    """
                    INSERT INTO local_poi_alias (alias_key, place_id)
                    VALUES (?, ?)
                    ON CONFLICT(alias_key, place_id) DO NOTHING;
                    """,
                    (key, a["place_id"]),
                )

            for g in gates:
                g_code = g["gate_code"]
                g_key = normalize_geo_key(g.get("gate_key") or g_code)
                cursor.execute(
                    """
                    INSERT INTO mega_poi_gates (
                        gate_id, place_id, gate_code, gate_key, lat, lng,
                        is_default_pickup, is_default_dropoff, driver_instruction, source, verified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(gate_id) DO UPDATE SET
                        gate_code = excluded.gate_code,
                        gate_key = excluded.gate_key,
                        lat = excluded.lat,
                        lng = excluded.lng,
                        is_default_pickup = excluded.is_default_pickup,
                        is_default_dropoff = excluded.is_default_dropoff,
                        driver_instruction = excluded.driver_instruction,
                        source = excluded.source,
                        verified = excluded.verified;
                    """,
                    (
                        g["gate_id"],
                        g["place_id"],
                        g_code,
                        g_key,
                        float(g["lat"]),
                        float(g["lng"]),
                        1 if g.get("is_default_pickup", False) else 0,
                        1 if g.get("is_default_dropoff", False) else 0,
                        g.get("driver_instruction", ""),
                        g.get("source", "manual"),
                        1 if g.get("verified", False) else 0,
                    ),
                )

            for s in streets:
                norm_name = normalize_geo_key(s["street_name"])
                cursor.execute(
                    """
                    INSERT INTO city_streets (
                        street_id, city, street_name, normalized_name, source, verified
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(street_id) DO UPDATE SET
                        city = excluded.city,
                        street_name = excluded.street_name,
                        normalized_name = excluded.normalized_name,
                        source = excluded.source,
                        verified = excluded.verified;
                    """,
                    (
                        s["street_id"],
                        s["city"],
                        s["street_name"],
                        norm_name,
                        s.get("source", "manual"),
                        1 if s.get("verified", False) else 0,
                    ),
                )

            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def hydrate_snapshot(self, path: str | Path) -> bool:
        """Replace cache from a validated snapshot; False means missing or empty data."""
        snapshot = Path(path)
        if not snapshot.exists():
            return False
        dataset = json.loads(snapshot.read_text(encoding="utf-8"))
        if not isinstance(dataset, dict):
            raise TypeError("Geo snapshot must contain a dataset object")
        self.upsert_dataset(dataset, replace=True)
        return bool(dataset.get("places"))

    def persist_snapshot(self, path: str | Path) -> None:
        """Atomically persist cache so CLI ingestion survives the next process."""
        snapshot = Path(path)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=snapshot.parent,
                prefix=snapshot.name + ".",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(self.export_dataset(), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, snapshot)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def get_place(
        self, place_id: str, allow_unverified: bool = False
    ) -> dict[str, Any] | None:
        """Fetch a stable cached place after a customer selected a candidate."""
        row = self.conn.execute(
            "SELECT * FROM places WHERE place_id = ?", (place_id,)
        ).fetchone()
        if not row or (not allow_unverified and not row["verified"]):
            return None
        return {
            "place_id": row["place_id"],
            "canonical_name": row["canonical_name"],
            "formatted_address": row["formatted_address"],
            "city": row["city"],
            "lat": row["lat"],
            "lng": row["lng"],
            "poi_type": row["poi_type"],
            "is_mega_poi": bool(row["is_mega_poi"]),
            "components": json.loads(row["components_json"]),
            "driver_note": row["driver_note"],
            "source": row["source"],
            "verified": bool(row["verified"]),
        }

    def delete_place_ids(self, place_ids: list[str]) -> None:
        """Delete places and cascading aliases and gates."""
        if not place_ids:
            return
        placeholders = ",".join("?" for _ in place_ids)
        with self.conn:
            self.conn.execute(
                f"DELETE FROM places WHERE place_id IN ({placeholders});",
                place_ids,
            )

    def lookup_poi_alias(
        self, raw_phrase: str, city: str | None = None, allow_unverified: bool = False
    ) -> list[dict[str, Any]]:
        """Lookup places by alias key and rank/filter by city."""
        key = normalize_geo_key(raw_phrase)
        verified_filter = "" if allow_unverified else "AND p.verified = 1"

        cursor = self.conn.execute(
            f"""
            SELECT p.* FROM places p
            JOIN local_poi_alias a ON p.place_id = a.place_id
            WHERE a.alias_key = ? {verified_filter};
            """,
            (key,),
        )
        rows = cursor.fetchall()
        results = []
        for r in rows:
            comps = json.loads(r["components_json"]) if r["components_json"] else {}
            results.append(
                {
                    "place_id": r["place_id"],
                    "canonical_name": r["canonical_name"],
                    "formatted_address": r["formatted_address"],
                    "city": r["city"],
                    "lat": r["lat"],
                    "lng": r["lng"],
                    "poi_type": r["poi_type"],
                    "is_mega_poi": bool(r["is_mega_poi"]),
                    "components": comps,
                    "driver_note": r["driver_note"],
                    "source": r["source"],
                    "verified": bool(r["verified"]),
                }
            )

        if city and results:
            city_norm = normalize_city_key(city)
            results = [x for x in results if normalize_city_key(x["city"]) == city_norm]

        return results

    def lookup_sub_poi(
        self, place_id: str, gate_code: str, allow_unverified: bool = False
    ) -> dict[str, Any] | None:
        """Lookup gate within a place by gate_code or normalized key."""
        g_key = normalize_geo_key(gate_code)
        verified_filter = "" if allow_unverified else "AND verified = 1"

        cursor = self.conn.execute(
            f"""
            SELECT * FROM mega_poi_gates
            WHERE place_id = ? AND (gate_key = ? OR lower(gate_code) = lower(?)) {verified_filter};
            """,
            (place_id, g_key, gate_code),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "gate_id": row["gate_id"],
            "place_id": row["place_id"],
            "gate_code": row["gate_code"],
            "lat": row["lat"],
            "lng": row["lng"],
            "is_default_pickup": bool(row["is_default_pickup"]),
            "is_default_dropoff": bool(row["is_default_dropoff"]),
            "driver_instruction": row["driver_instruction"],
            "source": row["source"],
            "verified": bool(row["verified"]),
        }

    def lookup_default_gate(
        self, place_id: str, role: str = "pickup", allow_unverified: bool = False
    ) -> dict[str, Any] | None:
        """Lookup default gate for place. Never returns place center coords."""
        col = "is_default_pickup" if role == "pickup" else "is_default_dropoff"
        verified_filter = "" if allow_unverified else "AND verified = 1"

        cursor = self.conn.execute(
            f"""
            SELECT * FROM mega_poi_gates
            WHERE place_id = ? AND {col} = 1 {verified_filter};
            """,
            (place_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "gate_id": row["gate_id"],
            "place_id": row["place_id"],
            "gate_code": row["gate_code"],
            "lat": row["lat"],
            "lng": row["lng"],
            "is_default_pickup": bool(row["is_default_pickup"]),
            "is_default_dropoff": bool(row["is_default_dropoff"]),
            "driver_instruction": row["driver_instruction"],
            "source": row["source"],
            "verified": bool(row["verified"]),
        }

    def fuzzy_street_match(
        self,
        street_input: str,
        city: str | None = None,
        allow_unverified: bool = False,
        limit: int = 3,
        threshold: float = 75.0,
    ) -> list[dict[str, Any]]:
        """Fuzzy match street names within city."""
        norm_input = normalize_geo_key(street_input)
        params: list[Any] = []
        where_clauses = []
        if city:
            where_clauses.append("normalized_name != '' AND (city = ? OR ? = '')")
            params.extend([city, city])
        if not allow_unverified:
            where_clauses.append("verified = 1")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        cursor = self.conn.execute(
            f"SELECT street_id, city, street_name, normalized_name FROM city_streets {where_sql};",
            params,
        )
        rows = cursor.fetchall()
        if not rows:
            return []

        choices = {r["street_id"]: r["normalized_name"] for r in rows}
        row_map = {r["street_id"]: r for r in rows}

        results = []
        extracted = process.extract(
            norm_input,
            choices,
            scorer=fuzz.WRatio,
            limit=limit,
            score_cutoff=threshold,
        )
        for _, score, sid in extracted:
            r = row_map[sid]
            results.append(
                {
                    "street_id": r["street_id"],
                    "city": r["city"],
                    "street_name": r["street_name"],
                    "score": float(score),
                }
            )
        return results

    def export_dataset(self) -> dict[str, Any]:
        """Export current in-memory dataset to serializable dictionary."""
        places_rows = self.conn.execute("SELECT * FROM places;").fetchall()
        aliases_rows = self.conn.execute("SELECT * FROM local_poi_alias;").fetchall()
        gates_rows = self.conn.execute("SELECT * FROM mega_poi_gates;").fetchall()
        streets_rows = self.conn.execute("SELECT * FROM city_streets;").fetchall()

        return {
            "places": [
                {
                    "place_id": r["place_id"],
                    "canonical_name": r["canonical_name"],
                    "formatted_address": r["formatted_address"],
                    "city": r["city"],
                    "lat": r["lat"],
                    "lng": r["lng"],
                    "poi_type": r["poi_type"],
                    "is_mega_poi": bool(r["is_mega_poi"]),
                    "components": json.loads(r["components_json"])
                    if r["components_json"]
                    else {},
                    "driver_note": r["driver_note"],
                    "source": r["source"],
                    "verified": bool(r["verified"]),
                }
                for r in places_rows
            ],
            "aliases": [
                {"alias_key": r["alias_key"], "place_id": r["place_id"]}
                for r in aliases_rows
            ],
            "gates": [
                {
                    "gate_id": r["gate_id"],
                    "place_id": r["place_id"],
                    "gate_code": r["gate_code"],
                    "gate_key": r["gate_key"],
                    "lat": r["lat"],
                    "lng": r["lng"],
                    "is_default_pickup": bool(r["is_default_pickup"]),
                    "is_default_dropoff": bool(r["is_default_dropoff"]),
                    "driver_instruction": r["driver_instruction"],
                    "source": r["source"],
                    "verified": bool(r["verified"]),
                }
                for r in gates_rows
            ],
            "streets": [
                {
                    "street_id": r["street_id"],
                    "city": r["city"],
                    "street_name": r["street_name"],
                    "source": r["source"],
                    "verified": bool(r["verified"]),
                }
                for r in streets_rows
            ],
        }


# Global in-memory cache singleton
geo_cache = GeoCache()
