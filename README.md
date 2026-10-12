# SlotDesk

A full-stack appointment booking app for a municipal service desk. Residents browse free time slots, book one, and cancel later. Office staff add slots and see every booking.

I built it to practise the parts of a booking system that are easy to get wrong: **double-booking under concurrent requests**, **role-based access**, and **clear API errors**. It uses synthetic data only.

**Stack:** React (Vite) · Python / Flask · SQLite (raw SQL) · pytest

## Features

- Register, log in, and stay logged in with signed, expiring tokens
- Browse upcoming slots grouped by day, filtered by service
- Book a slot with an optional note; see your bookings; cancel them
- Admin view: add slots, see all active bookings, cancel on a resident's behalf
- A user cannot hold two bookings at the same time, and past slots cannot be booked

## The interesting part: preventing double-booking

Checking "is this slot free?" and then inserting a booking is not safe on its own. Two requests can both pass the check before either inserts. SlotDesk enforces the rule in the database instead, with a **partial unique index**:

```sql
CREATE UNIQUE INDEX one_active_booking_per_slot
    ON bookings (slot_id) WHERE status = 'active';
```

A slot can have only one *active* booking. Cancelled bookings stay as history but no longer count, so a cancelled slot becomes bookable again. The API catches the resulting `IntegrityError` and returns a clean `409 Conflict`.

`tests/test_api.py::test_simultaneous_requests_produce_exactly_one_booking` starts 8 users at the same instant against one slot and asserts exactly one `201` and seven `409`s.

## Run it locally

Requires Python 3.10+ and Node 18+.

```bash
# 1. Backend  (http://127.0.0.1:5000)
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
flask --app run seed          # demo users and slots
python run.py

# 2. Frontend  (http://localhost:5173), in a second terminal
cd frontend
npm install
npm run dev
```

Demo accounts created by the seed command:

| Role  | Email                 | Password   |
|-------|-----------------------|------------|
| User  | demo@slotdesk.test    | demo12345  |
| Admin | admin@slotdesk.test   | admin12345 |

Set `SECRET_KEY` in the environment for anything beyond local use.

## Tests

```bash
cd backend && pytest
```

14 tests cover authentication, validation, booking rules, admin permissions, and the concurrency race.

## API

All routes are under `/api`. Everything except register and login needs `Authorization: Bearer <token>`.

| Method | Path | Who | Purpose |
|--------|------|-----|---------|
| POST | `/auth/register` | anyone | Create an account (always role `user`) |
| POST | `/auth/login` | anyone | Get a token |
| GET | `/services` | user | Services with upcoming slots |
| GET | `/slots?service=` | user | Upcoming slots with `booked` and `my_booking_id` |
| POST | `/slots` | admin | Create a slot |
| DELETE | `/slots/<id>` | admin | Delete a slot with no active booking |
| POST | `/bookings` | user | Book a slot (`201`, or `409` if taken) |
| GET | `/bookings` | user | My bookings |
| DELETE | `/bookings/<id>` | owner / admin | Cancel (soft delete) |
| GET | `/admin/bookings` | admin | All active bookings |

## Design decisions

- **Raw SQL with `sqlite3`** instead of an ORM, so the schema, constraints and queries are visible and reviewable.
- **Constraints in the schema** (`CHECK`, `UNIQUE`, foreign keys), not only in Python, so bad data cannot get in through any path.
- **Cancelling is a soft delete**, which keeps history and lets the unique index free the slot.
- **"Not found" and "not yours" return the same 404** when cancelling, so booking ids cannot be probed.
- **Times are stored in UTC** and shown in the viewer's local time in the browser.

## Project structure

```
backend/
  app/schema.sql   tables, constraints, the partial unique index
  app/routes.py    API endpoints
  app/auth.py      token creation and the login/admin decorator
  app/seed.py      demo data
  tests/           pytest suite
frontend/
  src/App.jsx      booking board, my bookings, admin view
  src/api.js       fetch wrapper and session handling
```

## What I would add next

- Email confirmation and reminders
- Rate limiting on login
- Slot capacity greater than one (group sessions)
- Docker Compose setup and a deployed demo
- Component tests for the React UI
