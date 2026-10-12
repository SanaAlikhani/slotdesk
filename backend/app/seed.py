from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

ISO = "%Y-%m-%dT%H:%M:%SZ"
SERVICES = ["ID card renewal", "Residency certificate"]


def seed(db) -> None:
    """Demo data: one admin, one user, and slots for the next 5 working days."""
    for email, name, password, role in [
        ("admin@slotdesk.test", "Office Admin", "admin12345", "admin"),
        ("demo@slotdesk.test", "Demo User", "demo12345", "user"),
    ]:
        db.execute(
            "INSERT OR IGNORE INTO users (email, name, password_hash, role) VALUES (?, ?, ?, ?)",
            (email, name, generate_password_hash(password), role),
        )

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    days_added, offset = 0, 1
    while days_added < 5:
        day = today + timedelta(days=offset)
        offset += 1
        if day.weekday() >= 5:  # skip weekends
            continue
        days_added += 1
        for service in SERVICES:
            for i in range(6):
                start = day + timedelta(hours=8, minutes=30 * i)
                db.execute(
                    "INSERT OR IGNORE INTO slots (service, starts_at) VALUES (?, ?)",
                    (service, start.strftime(ISO)),
                )
    db.commit()
