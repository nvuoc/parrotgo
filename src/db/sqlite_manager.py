"""Persistent SQLite manager for customers, sessions, messages, bookings and audit logs."""

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.state import ParrotGoGraphState
from src.core.time_utils import now_iso

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    phone TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    total_trips INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL REFERENCES customers(phone) ON DELETE CASCADE,
    label TEXT NOT NULL,
    address_key TEXT NOT NULL,
    address_json TEXT NOT NULL,
    frequency INTEGER NOT NULL DEFAULT 1,
    last_used TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(phone, label, address_key)
);

CREATE TABLE IF NOT EXISTS call_sessions (
    session_id TEXT PRIMARY KEY,
    customer_phone TEXT NOT NULL REFERENCES customers(phone),
    session_city TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    booking_status TEXT NOT NULL DEFAULT 'collecting'
        CHECK (booking_status IN ('collecting', 'ready_to_book', 'confirming',
               'booked', 'cancel_pending', 'canceled', 'operator_required')),
    fallback_count INTEGER NOT NULL DEFAULT 0 CHECK (fallback_count >= 0),
    started_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS bookings (
    booking_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE REFERENCES call_sessions(session_id),
    customer_phone TEXT NOT NULL REFERENCES customers(phone),
    customer_name TEXT NOT NULL,
    vehicle_type TEXT NOT NULL CHECK (vehicle_type IN ('xe_may', 'oto_4_cho', 'oto_7_cho')),
    pickup_time TEXT NOT NULL,
    slots_json TEXT NOT NULL,
    booking_revision INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    dispatch_status TEXT NOT NULL DEFAULT 'not_integrated'
        CHECK (dispatch_status IN ('not_integrated', 'pending', 'accepted', 'failed')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES call_sessions(session_id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL CHECK (turn_index > 0),
    turn_received_at TEXT NOT NULL,
    user_input TEXT NOT NULL,
    bot_response TEXT NOT NULL,
    intents_json TEXT NOT NULL,
    action_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, turn_index)
);

CREATE TABLE IF NOT EXISTS audit_trail (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES call_sessions(session_id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL,
    rule_triggered TEXT NOT NULL,
    action_selected TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    latency_ms REAL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, turn_index)
);

CREATE INDEX IF NOT EXISTS idx_fav_phone ON customer_favorites(phone);
CREATE INDEX IF NOT EXISTS idx_session_phone ON call_sessions(customer_phone);
CREATE INDEX IF NOT EXISTS idx_booking_phone ON bookings(customer_phone);
"""


class PersistenceError(Exception):
    """Raised when SQLite transaction fails."""
    pass


class SQLiteManager:
    def __init__(self, db_path: str = "data/parrotgo.db"):
        self.db_path = db_path
        p = Path(db_path)
        if not p.is_absolute() and not str(db_path).startswith(":memory:"):
            p.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    def compute_turn_payload_hash(
        self,
        session_id: str,
        turn_index: int,
        user_input: str,
        bot_response: str,
        intents: Any,
        action: Any,
        booking_status: str,
    ) -> str:
        payload = {
            "session_id": session_id,
            "turn_index": turn_index,
            "user_input": user_input,
            "bot_response": bot_response,
            "intents": sorted(intents) if isinstance(intents, list) else intents,
            "action": action,
            "booking_status": booking_status,
        }
        canonical_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    def start_session(
        self,
        session_id: str,
        phone: str,
        name: str,
        session_city: Optional[str],
        timezone: str,
        started_at: str,
    ) -> None:
        """Start a new session or verify existing session in one transaction."""
        conn = self.get_connection()
        try:
            with conn:
                # 1. Upsert customer
                conn.execute(
                    """
                    INSERT INTO customers (phone, name, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(phone) DO UPDATE SET
                        name = excluded.name,
                        updated_at = excluded.updated_at;
                    """,
                    (phone, name, started_at),
                )

                # 2. Check existing session
                cursor = conn.execute(
                    "SELECT session_id, customer_phone, booking_status FROM call_sessions WHERE session_id = ?;",
                    (session_id,),
                )
                existing = cursor.fetchone()
                if existing:
                    if existing["customer_phone"] != phone:
                        raise PersistenceError(f"Session {session_id} belongs to another customer")
                    if existing["booking_status"] in {"booked", "canceled", "operator_required"}:
                        raise PersistenceError(f"Phiên {session_id} đã kết thúc; cần session_id mới")
                    return

                # 3. Insert new session
                conn.execute(
                    """
                    INSERT INTO call_sessions (
                        session_id, customer_phone, session_city, timezone, booking_status, fallback_count, started_at
                    ) VALUES (?, ?, ?, ?, 'collecting', 0, ?);
                    """,
                    (session_id, phone, session_city, timezone, started_at),
                )
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise PersistenceError(f"Error starting session: {e}") from e
        finally:
            conn.close()

    def get_customer_crm_profile(self, phone: str) -> Optional[Dict[str, Any]]:
        """Fetch CRM profile and saved favorite locations."""
        conn = self.get_connection()
        try:
            cursor = conn.execute(
                "SELECT phone, name, total_trips, created_at FROM customers WHERE phone = ?;",
                (phone,),
            )
            cust = cursor.fetchone()
            if not cust:
                return None

            fav_cursor = conn.execute(
                "SELECT label, address_key, address_json, frequency FROM customer_favorites WHERE phone = ? ORDER BY frequency DESC;",
                (phone,),
            )
            favorites = []
            home_addr = None
            work_addr = None
            for row in fav_cursor.fetchall():
                addr_data = json.loads(row["address_json"])
                fav_entry = {
                    "label": row["label"],
                    "address_key": row["address_key"],
                    "address": addr_data,
                    "frequency": row["frequency"],
                }
                favorites.append(fav_entry)
                if row["label"].lower() == "nhà" or row["label"].lower() == "home":
                    home_addr = addr_data
                elif row["label"].lower() == "công ty" or row["label"].lower() == "work":
                    work_addr = addr_data

            return {
                "phone": cust["phone"],
                "name": cust["name"],
                "total_trips": cust["total_trips"],
                "created_at": cust["created_at"],
                "home_address": home_addr,
                "work_address": work_addr,
                "frequent_destinations": favorites,
            }
        finally:
            conn.close()

    def get_turn_outcome(self, session_id: str, turn_index: int) -> Optional[Dict[str, Any]]:
        """Lookup previously committed outcome for replay idempotency."""
        conn = self.get_connection()
        try:
            cursor = conn.execute(
                "SELECT booking_id FROM bookings WHERE session_id = ?;",
                (session_id,),
            )
            booking_row = cursor.fetchone()
            booking_id = booking_row["booking_id"] if booking_row else None

            msg_cursor = conn.execute(
                "SELECT payload_hash FROM session_messages WHERE session_id = ? AND turn_index = ?;",
                (session_id, turn_index),
            )
            msg_row = msg_cursor.fetchone()
            if not msg_row:
                return None

            return {"booking_id": booking_id, "payload_hash": msg_row["payload_hash"]}
        finally:
            conn.close()

    def persist_turn(self, state: ParrotGoGraphState, latency_ms: Optional[float] = None) -> Dict[str, Any]:
        """Commit entire turn into SQLite in one transaction."""
        session_id = state["session_id"]
        turn_index = state["turn_index"]
        phone = state["customer_phone"]
        name = state["customer_name"]
        user_input = state["user_current_input"]
        bot_response = state["final_response_text"]
        intents = state.get("intents", [])
        action = state.get("last_bot_action") or {}
        booking_status = state.get("booking_status", "collecting")
        slots = state["booking_slots"]

        payload_hash = self.compute_turn_payload_hash(
            session_id=session_id,
            turn_index=turn_index,
            user_input=user_input,
            bot_response=bot_response,
            intents=intents,
            action=action,
            booking_status=booking_status,
        )

        conn = self.get_connection()
        try:
            with conn:
                # 1. Verify session exists
                sess_cur = conn.execute(
                    "SELECT session_id, customer_phone FROM call_sessions WHERE session_id = ?;",
                    (session_id,),
                )
                sess = sess_cur.fetchone()
                if not sess:
                    raise PersistenceError(f"Session {session_id} not found")
                if sess["customer_phone"] != phone:
                    raise PersistenceError(f"Session customer mismatch: {sess['customer_phone']} != {phone}")

                # 2. Check if (session_id, turn_index) already recorded
                existing_msg = conn.execute(
                    "SELECT payload_hash FROM session_messages WHERE session_id = ? AND turn_index = ?;",
                    (session_id, turn_index),
                ).fetchone()

                if existing_msg:
                    if existing_msg["payload_hash"] == payload_hash:
                        # Replay idempotent
                        book_cur = conn.execute(
                            "SELECT booking_id FROM bookings WHERE session_id = ?;",
                            (session_id,),
                        ).fetchone()
                        return {"booking_id": book_cur["booking_id"] if book_cur else None}
                    else:
                        raise PersistenceError(f"Conflict: Turn {turn_index} already committed with different payload")

                now_ts = now_iso(state.get("timezone", "Asia/Ho_Chi_Minh"))

                # 3. Insert session_messages
                conn.execute(
                    """
                    INSERT INTO session_messages (
                        session_id, turn_index, turn_received_at, user_input, bot_response,
                        intents_json, action_json, payload_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        session_id,
                        turn_index,
                        state["turn_received_at"],
                        user_input,
                        bot_response,
                        json.dumps(intents, ensure_ascii=False),
                        json.dumps(action, ensure_ascii=False),
                        payload_hash,
                        now_ts,
                    ),
                )

                # 4. Insert audit_trail
                rule_name = action.get("action_type", "unknown")
                decision_payload = {
                    "ready_to_book": state.get("ready_to_book", False),
                    "pending_modify_target": state.get("pending_modify_target", False),
                    "fallback_count": state.get("fallback_count", 0),
                    "booking_revision": state.get("booking_revision", 0),
                    "handoff_reason": state.get("handoff_reason"),
                }
                conn.execute(
                    """
                    INSERT INTO audit_trail (
                        session_id, turn_index, rule_triggered, action_selected,
                        decision_json, latency_ms, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        session_id,
                        turn_index,
                        rule_name,
                        rule_name,
                        json.dumps(decision_payload, ensure_ascii=False),
                        latency_ms,
                        now_ts,
                    ),
                )

                # 5. Update call_sessions
                ended_at = now_ts if state.get("is_terminal") else None
                conn.execute(
                    """
                    UPDATE call_sessions SET
                        session_city = ?,
                        booking_status = ?,
                        fallback_count = ?,
                        ended_at = COALESCE(?, ended_at)
                    WHERE session_id = ?;
                    """,
                    (
                        state.get("session_city"),
                        booking_status,
                        state.get("fallback_count", 0),
                        ended_at,
                        session_id,
                    ),
                )

                # 6. Handle booking if status is booked
                booking_id = state.get("booking_id")
                if booking_status == "booked":
                    # Check if booking already exists for session
                    existing_booking = conn.execute(
                        "SELECT booking_id FROM bookings WHERE session_id = ?;",
                        (session_id,),
                    ).fetchone()

                    if not existing_booking:
                        if not booking_id:
                            booking_id = str(uuid.uuid4())
                        v_type = slots["vehicle_type"]["value"]
                        p_time = slots["pickup_time"]["value"]
                        slots_str = json.dumps(slots, ensure_ascii=False)
                        rev = state.get("booking_revision", 0)

                        conn.execute(
                            """
                            INSERT INTO bookings (
                                booking_id, session_id, customer_phone, customer_name,
                                vehicle_type, pickup_time, slots_json, booking_revision,
                                status, dispatch_status, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', 'not_integrated', ?);
                            """,
                            (
                                booking_id,
                                session_id,
                                phone,
                                name,
                                v_type,
                                p_time,
                                slots_str,
                                rev,
                                now_ts,
                            ),
                        )

                        # Increment total_trips
                        conn.execute(
                            "UPDATE customers SET total_trips = total_trips + 1, updated_at = ? WHERE phone = ?;",
                            (now_ts, phone),
                        )

                        # Upsert favorite destination
                        dest = slots.get("destination", {})
                        dest_key = dest.get("place_id") or dest.get("formatted") or dest.get("raw")
                        if dest_key:
                            dest_json_str = json.dumps(dest, ensure_ascii=False)
                            label = dest.get("formatted") or dest.get("raw") or "Điểm đến"
                            conn.execute(
                                """
                                INSERT INTO customer_favorites (phone, label, address_key, address_json, frequency, last_used)
                                VALUES (?, ?, ?, ?, 1, ?)
                                ON CONFLICT(phone, label, address_key) DO UPDATE SET
                                    frequency = customer_favorites.frequency + 1,
                                    last_used = excluded.last_used,
                                    address_json = excluded.address_json;
                                """,
                                (phone, label, str(dest_key), dest_json_str, now_ts),
                            )
                    else:
                        booking_id = existing_booking["booking_id"]

                conn.commit()
                return {"booking_id": booking_id}
        except Exception as e:
            conn.rollback()
            raise PersistenceError(f"Error persisting turn: {e}") from e
        finally:
            conn.close()

_default_db_manager: Optional[SQLiteManager] = None


def get_default_db_manager(db_path: Optional[str] = None) -> SQLiteManager:
    """Retrieve or initialize the active SQLiteManager."""
    global _default_db_manager
    if _default_db_manager is None:
        _default_db_manager = SQLiteManager(db_path=db_path or "data/parrotgo.db")
    return _default_db_manager


def set_default_db_manager(manager: SQLiteManager) -> None:
    """Set the active SQLiteManager instance."""
    global _default_db_manager
    _default_db_manager = manager

