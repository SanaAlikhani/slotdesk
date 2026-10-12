import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app import create_app

ISO = "%Y-%m-%dT%H:%M:%SZ"


@pytest.fixture()
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite"),
                       "SECRET_KEY": "test"})


@pytest.fixture()
def client(app):
    return app.test_client()


def future(hours=48):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime(ISO)


class Helpers:
    def __init__(self, app):
        self.app = app
        self.n = 0

    def register(self, client=None, name="Test User"):
        self.n += 1
        client = client or self.app.test_client()
        res = client.post("/api/auth/register", json={
            "name": name, "email": f"user{self.n}@example.com", "password": "password123"})
        assert res.status_code == 201, res.get_json()
        data = res.get_json()
        return data["user"]["id"], {"Authorization": f"Bearer {data['token']}"}

    def make_admin(self):
        user_id, headers = self.register(name="Admin")
        con = sqlite3.connect(self.app.config["DATABASE"])
        con.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
        con.commit()
        con.close()
        return headers

    def slot(self, service="ID card renewal", hours=48):
        """Insert a slot straight into the DB (bypasses the admin API)."""
        con = sqlite3.connect(self.app.config["DATABASE"])
        cur = con.execute("INSERT INTO slots (service, starts_at) VALUES (?, ?)",
                          (service, future(hours)))
        con.commit()
        slot_id = cur.lastrowid
        con.close()
        return slot_id


@pytest.fixture()
def h(app):
    return Helpers(app)
