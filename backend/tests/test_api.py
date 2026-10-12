import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from conftest import ISO, future


# ---------- auth ----------
def test_register_and_login(client):
    res = client.post("/api/auth/register",
                      json={"name": "Sana", "email": "Sana@Example.com", "password": "password123"})
    assert res.status_code == 201
    assert res.get_json()["user"]["role"] == "user"

    ok = client.post("/api/auth/login", json={"email": "sana@example.com", "password": "password123"})
    assert ok.status_code == 200 and "token" in ok.get_json()

    bad = client.post("/api/auth/login", json={"email": "sana@example.com", "password": "wrong"})
    assert bad.status_code == 401


def test_register_validation_and_duplicate(client):
    assert client.post("/api/auth/register", json={"name": "A", "email": "nope", "password": "password123"}).status_code == 400
    assert client.post("/api/auth/register", json={"name": "A", "email": "a@b.co", "password": "short"}).status_code == 400
    body = {"name": "A", "email": "a@b.co", "password": "password123"}
    assert client.post("/api/auth/register", json=body).status_code == 201
    assert client.post("/api/auth/register", json=body).status_code == 409


def test_endpoints_require_token(client):
    assert client.get("/api/slots").status_code == 401
    assert client.post("/api/bookings", json={"slot_id": 1}).status_code == 401
    assert client.get("/api/slots", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_users_cannot_register_as_admin(client):
    res = client.post("/api/auth/register", json={
        "name": "Eve", "email": "eve@example.com", "password": "password123", "role": "admin"})
    assert res.get_json()["user"]["role"] == "user"


# ---------- booking rules ----------
def test_book_a_slot(client, h):
    _, headers = h.register()
    slot_id = h.slot()
    res = client.post("/api/bookings", json={"slot_id": slot_id, "note": "Bring ID"}, headers=headers)
    assert res.status_code == 201
    assert res.get_json()["service"] == "ID card renewal"

    slots = client.get("/api/slots", headers=headers).get_json()
    assert slots[0]["booked"] is True and slots[0]["my_booking_id"] == res.get_json()["id"]


def test_double_booking_is_rejected(client, h):
    _, first = h.register()
    _, second = h.register()
    slot_id = h.slot()
    assert client.post("/api/bookings", json={"slot_id": slot_id}, headers=first).status_code == 201
    res = client.post("/api/bookings", json={"slot_id": slot_id}, headers=second)
    assert res.status_code == 409


def test_cancel_frees_the_slot(client, h):
    _, first = h.register()
    _, second = h.register()
    slot_id = h.slot()
    booking = client.post("/api/bookings", json={"slot_id": slot_id}, headers=first).get_json()
    assert client.delete(f"/api/bookings/{booking['id']}", headers=first).status_code == 200
    assert client.post("/api/bookings", json={"slot_id": slot_id}, headers=second).status_code == 201


def test_cannot_cancel_someone_elses_booking(client, h):
    _, owner = h.register()
    _, other = h.register()
    booking = client.post("/api/bookings", json={"slot_id": h.slot()}, headers=owner).get_json()
    assert client.delete(f"/api/bookings/{booking['id']}", headers=other).status_code == 404
    admin = h.make_admin()
    assert client.delete(f"/api/bookings/{booking['id']}", headers=admin).status_code == 200


def test_same_user_cannot_hold_two_slots_at_the_same_time(client, h):
    _, headers = h.register()
    when = future(72)
    con = sqlite3.connect(h.app.config["DATABASE"])
    ids = [con.execute("INSERT INTO slots (service, starts_at) VALUES (?, ?)", (s, when)).lastrowid
           for s in ("ID card renewal", "Residency certificate")]
    con.commit()
    con.close()
    assert client.post("/api/bookings", json={"slot_id": ids[0]}, headers=headers).status_code == 201
    assert client.post("/api/bookings", json={"slot_id": ids[1]}, headers=headers).status_code == 409


def test_cannot_book_a_slot_in_the_past(client, h):
    _, headers = h.register()
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(ISO)
    con = sqlite3.connect(h.app.config["DATABASE"])
    slot_id = con.execute("INSERT INTO slots (service, starts_at) VALUES ('X', ?)", (past,)).lastrowid
    con.commit()
    con.close()
    assert client.post("/api/bookings", json={"slot_id": slot_id}, headers=headers).status_code == 409


def test_booking_input_validation(client, h):
    _, headers = h.register()
    slot_id = h.slot()
    assert client.post("/api/bookings", json={}, headers=headers).status_code == 400
    assert client.post("/api/bookings", json={"slot_id": "1"}, headers=headers).status_code == 400
    assert client.post("/api/bookings", json={"slot_id": 9999}, headers=headers).status_code == 404
    assert client.post("/api/bookings", json={"slot_id": slot_id, "note": "x" * 301},
                       headers=headers).status_code == 400


# ---------- admin ----------
def test_only_admin_can_manage_slots(client, h):
    _, user = h.register()
    admin = h.make_admin()
    payload = {"service": "Tax desk", "starts_at": future(96), "duration_min": 20}
    assert client.post("/api/slots", json=payload, headers=user).status_code == 403
    assert client.post("/api/slots", json=payload, headers=admin).status_code == 201
    assert client.post("/api/slots", json=payload, headers=admin).status_code == 409  # duplicate


def test_admin_cannot_delete_slot_with_active_booking(client, h):
    _, user = h.register()
    admin = h.make_admin()
    slot_id = h.slot()
    booking = client.post("/api/bookings", json={"slot_id": slot_id}, headers=user).get_json()
    assert client.delete(f"/api/slots/{slot_id}", headers=admin).status_code == 409
    client.delete(f"/api/bookings/{booking['id']}", headers=user)
    assert client.delete(f"/api/slots/{slot_id}", headers=admin).status_code == 204


# ---------- concurrency ----------
def test_simultaneous_requests_produce_exactly_one_booking(app, h):
    """8 different users race for the same slot at the same instant."""
    users = [h.register()[1] for _ in range(8)]
    slot_id = h.slot()
    barrier = threading.Barrier(len(users))
    results = []

    def attempt(headers):
        client = app.test_client()
        barrier.wait()
        results.append(client.post("/api/bookings", json={"slot_id": slot_id}, headers=headers).status_code)

    threads = [threading.Thread(target=attempt, args=(u,)) for u in users]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [201] + [409] * 7
    con = sqlite3.connect(app.config["DATABASE"])
    assert con.execute("SELECT COUNT(*) FROM bookings WHERE slot_id=? AND status='active'",
                       (slot_id,)).fetchone()[0] == 1
    con.close()
