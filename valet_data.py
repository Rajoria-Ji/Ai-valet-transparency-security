"""Database, sign-in, vehicle records, and audit helpers for the local demo."""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from audit_logger import AuditLogger

BASE_DIR = Path(__file__).resolve().parent

INSTANCE_DIR = BASE_DIR / "instance"

DATABASE_PATH = INSTANCE_DIR / "valet_demo.sqlite3"

SESSION_SECRET_PATH = INSTANCE_DIR / "session_secret"

UPLOAD_DIR = INSTANCE_DIR / "uploads"

AUDIT_LOGGER = AuditLogger(BASE_DIR / "logs" / "audit_log.jsonl")

STATUS_FLOW = (
    "CHECKED_IN",
    "IN_TRANSIT",
    "PARKED",
    "RETRIEVAL_REQUESTED",
    "COMPLETED",
)

DEMO_ACCOUNTS = (
    ("supervisor", "Demo Supervisor", "supervisor", "supervisor-demo"),
    ("valet", "Demo Valet", "valet", "valet-demo"),
)

PASSWORD_ITERATIONS = 240_000

SESSION_SECONDS = 8 * 60 * 60

MAX_PHOTO_BYTES = 4_000_000

SESSION_SECRET = b""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def password_digest(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    ).hex()


def initialize_database() -> None:
    global SESSION_SECRET
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with closing(connect_db()) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS users (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT NOT NULL UNIQUE,
                 display_name TEXT NOT NULL,
                 role TEXT NOT NULL CHECK (role IN ('supervisor', 'valet')),
                 password_salt TEXT NOT NULL,
                 password_hash TEXT NOT NULL,
                 active INTEGER NOT NULL DEFAULT 1,
                 created_at TEXT NOT NULL
               )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS vehicles (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 plate_number TEXT NOT NULL,
                 model TEXT NOT NULL,
                 color TEXT NOT NULL,
                 status TEXT NOT NULL,
                 created_at TEXT NOT NULL,
                 updated_at TEXT NOT NULL
               )"""
        )
        existing_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(vehicles)")
        }
        # Purane database ke records bachate hue zaroori columns add karte hain.
        if "assigned_user_id" not in existing_columns:
            connection.execute("ALTER TABLE vehicles ADD COLUMN assigned_user_id INTEGER")
        if "parking_slot" not in existing_columns:
            connection.execute("ALTER TABLE vehicles ADD COLUMN parking_slot TEXT")
        if "pickup_token_hash" not in existing_columns:
            connection.execute("ALTER TABLE vehicles ADD COLUMN pickup_token_hash TEXT")
        if "pickup_requested_at" not in existing_columns:
            connection.execute("ALTER TABLE vehicles ADD COLUMN pickup_requested_at TEXT")

        connection.execute(
            """CREATE TABLE IF NOT EXISTS vehicle_events (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 vehicle_id INTEGER NOT NULL,
                 actor_name TEXT NOT NULL,
                 event_type TEXT NOT NULL,
                 from_status TEXT,
                 to_status TEXT,
                 details TEXT NOT NULL DEFAULT '',
                 created_at TEXT NOT NULL,
                 FOREIGN KEY(vehicle_id) REFERENCES vehicles(id)
               )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS vehicle_photos (
                 photo_id TEXT PRIMARY KEY,
                 vehicle_id INTEGER NOT NULL,
                 kind TEXT NOT NULL,
                 storage_name TEXT NOT NULL,
                 content_type TEXT NOT NULL,
                 uploaded_by TEXT NOT NULL,
                 uploaded_at TEXT NOT NULL,
                 FOREIGN KEY(vehicle_id) REFERENCES vehicles(id)
               )"""
        )

        user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            for username, display_name, role, password in DEMO_ACCOUNTS:
                salt = secrets.token_bytes(16)
                connection.execute(
                    """INSERT INTO users
                       (username, display_name, role, password_salt, password_hash, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        username,
                        display_name,
                        role,
                        salt.hex(),
                        password_digest(password, salt),
                        now_utc(),
                    ),
                )
        connection.commit()

    if not SESSION_SECRET_PATH.exists():
        SESSION_SECRET_PATH.write_bytes(secrets.token_bytes(32))
        SESSION_SECRET_PATH.chmod(0o600)
    SESSION_SECRET = SESSION_SECRET_PATH.read_bytes()


def log_event(
    connection: sqlite3.Connection,
    vehicle_id: int,
    actor: str,
    event_type: str,
    from_status: str | None = None,
    to_status: str | None = None,
    details: str = "",
) -> None:
    connection.execute(
        """INSERT INTO vehicle_events
           (vehicle_id, actor_name, event_type, from_status, to_status, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (vehicle_id, actor, event_type, from_status, to_status, details[:200], now_utc()),
    )


def audit(action: str, actor: str, vehicle_id: int | None = None, status: str = "SUCCESS") -> None:
    details: dict[str, object] = {}
    if vehicle_id is not None:
        details["vehicle_id"] = vehicle_id
    AUDIT_LOGGER.log(user_id=actor, action=action, status=status, details=details)


def get_user(user_id: int) -> sqlite3.Row | None:
    with closing(connect_db()) as connection:
        return connection.execute(
            "SELECT id, username, display_name, role FROM users WHERE id = ? AND active = 1",
            (user_id,),
        ).fetchone()


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with closing(connect_db()) as connection:
        return connection.execute(
            "SELECT * FROM users WHERE username = ? AND active = 1", (username,)
        ).fetchone()


def get_valets() -> list[sqlite3.Row]:
    with closing(connect_db()) as connection:
        return list(
            connection.execute(
                "SELECT id, display_name FROM users WHERE role = 'valet' AND active = 1 ORDER BY display_name"
            )
        )


def create_session(user_id: int) -> str:
    payload = f"{user_id}|{int(time.time()) + SESSION_SECONDS}".encode("ascii")
    signature = hmac.new(SESSION_SECRET, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + b"." + signature).decode("ascii").rstrip("=")


def read_session(cookie_value: str) -> sqlite3.Row | None:
    try:
        padded = cookie_value + "=" * (-len(cookie_value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        if len(decoded) < 34 or decoded[-33:-32] != b".":
            return None
        payload, signature = decoded[:-33], decoded[-32:]
        expected = hmac.new(SESSION_SECRET, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        user_id_text, expires_text = payload.decode("ascii").split("|", 1)
        if int(expires_text) < int(time.time()):
            return None
        return get_user(int(user_id_text))
    except (ValueError, UnicodeError, TypeError):
        return None


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def display_time(value: str | None) -> str:
    if not value:
        return "—"
    return f"{value.replace('T', ' ')[:19]} UTC"


def mask_plate(plate: str) -> str:
    visible = 3
    letters = [index for index, char in enumerate(plate) if char.isalnum()]
    hide = max(0, len(letters) - visible)
    hidden_indexes = set(letters[:hide])
    return "".join("•" if index in hidden_indexes else char for index, char in enumerate(plate))


def generate_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    # Database me asli pickup link nahi, sirf uska hash rakhte hain.
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    return token, token_hash


def token_vehicle(token: str) -> sqlite3.Row | None:
    token_hash = hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()
    with closing(connect_db()) as connection:
        return connection.execute(
            """SELECT v.*, u.display_name AS assigned_name
               FROM vehicles v LEFT JOIN users u ON u.id = v.assigned_user_id
               WHERE v.pickup_token_hash = ?""",
            (token_hash,),
        ).fetchone()


def save_photo(photo: tuple[str, bytes] | None) -> tuple[str, str, str] | None:
    if photo is None:
        return None
    _original_name, content = photo
    if not content:
        return None
    if len(content) > MAX_PHOTO_BYTES:
        raise ValueError("Photo must be 4 MB or smaller.")
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        extension, content_type = ".png", "image/png"
    elif content.startswith(b"\xff\xd8\xff"):
        extension, content_type = ".jpg", "image/jpeg"
    else:
        raise ValueError("Choose a PNG or JPEG photo.")

    photo_id = secrets.token_hex(16)
    storage_name = f"{photo_id}{extension}"
    (UPLOAD_DIR / storage_name).write_bytes(content)
    return photo_id, storage_name, content_type


def record_photo(
    connection: sqlite3.Connection,
    vehicle_id: int,
    kind: str,
    saved: tuple[str, str, str] | None,
    actor: str,
) -> None:
    if saved is None:
        return
    photo_id, storage_name, content_type = saved
    connection.execute(
        """INSERT INTO vehicle_photos
           (photo_id, vehicle_id, kind, storage_name, content_type, uploaded_by, uploaded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (photo_id, vehicle_id, kind, storage_name, content_type, actor, now_utc()),
    )
    log_event(connection, vehicle_id, actor, "PHOTO_ADDED", details=f"{kind.title()} photo added")


def create_vehicle(
    plate: str,
    model: str,
    color: str,
    slot: str,
    assigned_user_id: int | None,
    actor: sqlite3.Row,
    photo: tuple[str, bytes] | None,
) -> tuple[int, str]:
    saved_photo = save_photo(photo)
    token, token_hash = generate_token()
    now = now_utc()
    connection = connect_db()
    try:
        cursor = connection.execute(
            """INSERT INTO vehicles
               (plate_number, model, color, status, created_at, updated_at,
                assigned_user_id, parking_slot, pickup_token_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                plate,
                model,
                color,
                STATUS_FLOW[0],
                now,
                now,
                assigned_user_id,
                slot or None,
                token_hash,
            ),
        )
        vehicle_id = int(cursor.lastrowid)
        log_event(connection, vehicle_id, actor["display_name"], "CHECKED_IN", to_status=STATUS_FLOW[0])
        if slot:
            log_event(connection, vehicle_id, actor["display_name"], "ASSIGNED", details=f"Parking slot {slot}")
        record_photo(connection, vehicle_id, "check-in", saved_photo, actor["display_name"])
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    audit("VEHICLE_CHECK_IN", actor["username"], vehicle_id, STATUS_FLOW[0])
    return vehicle_id, token


def get_vehicle(vehicle_id: int) -> sqlite3.Row | None:
    with closing(connect_db()) as connection:
        return connection.execute(
            """SELECT v.*, u.display_name AS assigned_name
               FROM vehicles v LEFT JOIN users u ON u.id = v.assigned_user_id
               WHERE v.id = ?""",
            (vehicle_id,),
        ).fetchone()


def list_vehicles(user: sqlite3.Row, query: str, status_filter: str) -> list[sqlite3.Row]:
    conditions: list[str] = []
    params: list[object] = []
    if user["role"] == "valet":
        conditions.append("v.assigned_user_id = ?")
        params.append(user["id"])
    if query:
        like = f"%{query}%"
        conditions.append("(v.plate_number LIKE ? OR v.model LIKE ? OR v.color LIKE ? OR u.display_name LIKE ? OR v.parking_slot LIKE ?)")
        params.extend([like, like, like, like, like])
    if status_filter in STATUS_FLOW:
        conditions.append("v.status = ?")
        params.append(status_filter)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    sql = """SELECT v.*, u.display_name AS assigned_name
             FROM vehicles v LEFT JOIN users u ON u.id = v.assigned_user_id""" + where + " ORDER BY v.updated_at DESC, v.id DESC"
    with closing(connect_db()) as connection:
        return list(connection.execute(sql, params))


def get_vehicle_events(vehicle_id: int) -> list[sqlite3.Row]:
    with closing(connect_db()) as connection:
        return list(
            connection.execute(
                "SELECT * FROM vehicle_events WHERE vehicle_id = ? ORDER BY id DESC",
                (vehicle_id,),
            )
        )


def get_vehicle_photos(vehicle_id: int) -> list[sqlite3.Row]:
    with closing(connect_db()) as connection:
        return list(
            connection.execute(
                "SELECT * FROM vehicle_photos WHERE vehicle_id = ? ORDER BY uploaded_at DESC",
                (vehicle_id,),
            )
        )


def dashboard_counts(user: sqlite3.Row) -> dict[str, int]:
    today = now_utc()[:10] + "%"
    scope = "" if user["role"] == "supervisor" else " AND assigned_user_id = ?"
    params: tuple[object, ...] = () if user["role"] == "supervisor" else (user["id"],)
    with closing(connect_db()) as connection:
        active = connection.execute(
            "SELECT COUNT(*) FROM vehicles WHERE status != 'COMPLETED'" + scope, params
        ).fetchone()[0]
        checkins = connection.execute(
            "SELECT COUNT(*) FROM vehicle_events e JOIN vehicles v ON v.id=e.vehicle_id WHERE e.event_type='CHECKED_IN' AND e.created_at LIKE ?" + scope,
            (today,) + params,
        ).fetchone()[0]
        pickups = connection.execute(
            "SELECT COUNT(*) FROM vehicle_events e JOIN vehicles v ON v.id=e.vehicle_id WHERE e.event_type='PICKUP_REQUESTED' AND e.created_at LIKE ?" + scope,
            (today,) + params,
        ).fetchone()[0]
        completed = connection.execute(
            "SELECT COUNT(*) FROM vehicle_events e JOIN vehicles v ON v.id=e.vehicle_id WHERE e.to_status='COMPLETED' AND e.created_at LIKE ?" + scope,
            (today,) + params,
        ).fetchone()[0]
        pickup_rows = list(
            connection.execute(
                """SELECT v.id, v.plate_number, v.model, v.parking_slot,
                          u.display_name AS assigned_name, v.pickup_requested_at
                   FROM vehicles v LEFT JOIN users u ON u.id=v.assigned_user_id
                   WHERE v.status='RETRIEVAL_REQUESTED'"""
                + (" AND v.assigned_user_id = ?" if user["role"] == "valet" else "")
                + " ORDER BY v.pickup_requested_at",
                params,
            )
        )
    return {
        "active": int(active),
        "checkins": int(checkins),
        "pickups": int(pickups),
        "completed": int(completed),
        "pickup_rows": pickup_rows,
    }


