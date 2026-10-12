import re
import sqlite3
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from .auth import error, login_required, make_token
from .db import get_db

bp = Blueprint("api", __name__)

ISO = "%Y-%m-%dT%H:%M:%SZ"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------- helpers ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).strftime(ISO)


def parse_start(value) -> str:
    """Validate an ISO timestamp with timezone and normalise it to UTC, minute precision."""
    if not isinstance(value, str):
        raise ValueError("starts_at must be an ISO 8601 string.")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("starts_at must include a timezone.")
    return dt.astimezone(timezone.utc).replace(second=0, microsecond=0).strftime(ISO)


def json_body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


# ---------- auth ----------
@bp.post("/auth/register")
def register():
    body = json_body()
    name = str(body.get("name", "")).strip()
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))

    if not name:
        return error("Enter your name.", 400)
    if not EMAIL_RE.match(email):
        return error("Enter a valid email address.", 400)
    if len(password) < 8:
        return error("Use a password of at least 8 characters.", 400)

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
            (email, name, generate_password_hash(password)),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return error("An account with this email already exists.", 409)

    user = {"id": cur.lastrowid, "email": email, "name": name, "role": "user"}
    return jsonify({"token": make_token(cur.lastrowid), "user": user}), 201


@bp.post("/auth/login")
def login():
    body = json_body()
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))

    row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return error("Email or password is incorrect.", 401)

    user = {k: row[k] for k in ("id", "email", "name", "role")}
    return jsonify({"token": make_token(row["id"]), "user": user})


# ---------- slots ----------
@bp.get("/services")
@login_required()
def list_services():
    rows = get_db().execute(
        "SELECT DISTINCT service FROM slots WHERE starts_at >= ? ORDER BY service", (now_iso(),)
    ).fetchall()
    return jsonify([r["service"] for r in rows])


@bp.get("/slots")
@login_required()
def list_slots():
    service = request.args.get("service")
    sql = """
        SELECT s.id, s.service, s.starts_at, s.duration_min,
               EXISTS (SELECT 1 FROM bookings b
                       WHERE b.slot_id = s.id AND b.status = 'active') AS booked,
               (SELECT b.id FROM bookings b
                WHERE b.slot_id = s.id AND b.status = 'active' AND b.user_id = ?) AS my_booking_id
        FROM slots s
        WHERE s.starts_at >= ?
    """
    params: list = [g.user["id"], now_iso()]
    if service:
        sql += " AND s.service = ?"
        params.append(service)
    sql += " ORDER BY s.starts_at, s.service LIMIT 500"

    rows = get_db().execute(sql, params).fetchall()
    return jsonify([{**dict(r), "booked": bool(r["booked"])} for r in rows])


@bp.post("/slots")
@login_required(admin=True)
def create_slot():
    body = json_body()
    service = str(body.get("service", "")).strip()
    duration = body.get("duration_min", 30)
    if not service or len(service) > 80:
        return error("Enter a service name (up to 80 characters).", 400)
    if not isinstance(duration, int) or not 5 <= duration <= 240:
        return error("Duration must be between 5 and 240 minutes.", 400)
    try:
        starts_at = parse_start(body.get("starts_at"))
    except ValueError as exc:
        return error(str(exc), 400)
    if starts_at <= now_iso():
        return error("Choose a time in the future.", 400)

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO slots (service, starts_at, duration_min) VALUES (?, ?, ?)",
            (service, starts_at, duration),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return error("This service already has a slot at that time.", 409)
    return jsonify({"id": cur.lastrowid, "service": service, "starts_at": starts_at,
                    "duration_min": duration}), 201


@bp.delete("/slots/<int:slot_id>")
@login_required(admin=True)
def delete_slot(slot_id: int):
    db = get_db()
    if db.execute("SELECT 1 FROM slots WHERE id = ?", (slot_id,)).fetchone() is None:
        return error("Slot not found.", 404)
    if db.execute(
        "SELECT 1 FROM bookings WHERE slot_id = ? AND status = 'active'", (slot_id,)
    ).fetchone():
        return error("This slot has an active booking. Cancel the booking first.", 409)
    db.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
    db.commit()
    return "", 204


# ---------- bookings ----------
BOOKING_SELECT = """
    SELECT b.id, b.slot_id, b.note, b.status, b.created_at,
           s.service, s.starts_at, s.duration_min,
           u.name AS user_name, u.email AS user_email
    FROM bookings b
    JOIN slots s ON s.id = b.slot_id
    JOIN users u ON u.id = b.user_id
"""


@bp.post("/bookings")
@login_required()
def create_booking():
    body = json_body()
    slot_id = body.get("slot_id")
    note = str(body.get("note", "")).strip()
    if not isinstance(slot_id, int) or isinstance(slot_id, bool):
        return error("Choose a slot to book.", 400)
    if len(note) > 300:
        return error("Keep the note under 300 characters.", 400)

    db = get_db()
    slot = db.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if slot is None:
        return error("Slot not found.", 404)
    if slot["starts_at"] <= now_iso():
        return error("This slot has already started. Choose a later one.", 409)

    clash = db.execute(
        """SELECT 1 FROM bookings b JOIN slots s ON s.id = b.slot_id
           WHERE b.user_id = ? AND b.status = 'active' AND s.starts_at = ?""",
        (g.user["id"], slot["starts_at"]),
    ).fetchone()
    if clash:
        return error("You already have a booking at this time.", 409)

    # The pre-checks above give friendly messages, but they are not what keeps
    # the data correct: two requests can pass them at the same moment. The
    # partial unique index in schema.sql is the real guarantee, so we rely on
    # it and translate its error into a clean 409.
    try:
        cur = db.execute(
            "INSERT INTO bookings (slot_id, user_id, note) VALUES (?, ?, ?)",
            (slot_id, g.user["id"], note),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return error("Someone just booked this slot. Choose another one.", 409)

    row = db.execute(BOOKING_SELECT + " WHERE b.id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@bp.get("/bookings")
@login_required()
def my_bookings():
    rows = get_db().execute(
        BOOKING_SELECT + " WHERE b.user_id = ? ORDER BY s.starts_at DESC", (g.user["id"],)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.get("/admin/bookings")
@login_required(admin=True)
def all_bookings():
    rows = get_db().execute(
        BOOKING_SELECT + " WHERE b.status = 'active' ORDER BY s.starts_at"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.delete("/bookings/<int:booking_id>")
@login_required()
def cancel_booking(booking_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    # Same answer for "doesn't exist" and "not yours" so ids can't be probed.
    if row is None or (row["user_id"] != g.user["id"] and g.user["role"] != "admin"):
        return error("Booking not found.", 404)
    if row["status"] == "cancelled":
        return error("This booking is already cancelled.", 409)
    db.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
    db.commit()
    return jsonify({"id": booking_id, "status": "cancelled"})
