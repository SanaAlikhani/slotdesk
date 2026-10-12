CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin'))
);

CREATE TABLE IF NOT EXISTS slots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    service      TEXT NOT NULL,
    starts_at    TEXT NOT NULL,                      -- ISO 8601, UTC
    duration_min INTEGER NOT NULL DEFAULT 30 CHECK (duration_min BETWEEN 5 AND 240),
    UNIQUE (service, starts_at)
);

CREATE TABLE IF NOT EXISTS bookings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id    INTEGER NOT NULL REFERENCES slots(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    note       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- The rule that makes double-booking impossible, enforced by the database
-- itself: a slot can have at most ONE active booking. Cancelled bookings are
-- kept as history and do not count, so a cancelled slot becomes free again.
CREATE UNIQUE INDEX IF NOT EXISTS one_active_booking_per_slot
    ON bookings (slot_id) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings (user_id);
CREATE INDEX IF NOT EXISTS idx_slots_starts  ON slots (starts_at);
