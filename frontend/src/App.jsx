import { useCallback, useEffect, useMemo, useState } from "react";
import { api, session } from "./api";

const fmtDay = (iso) =>
  new Date(iso).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
const fmtTime = (iso) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
const fmtWhen = (iso) => `${fmtDay(iso)}, ${fmtTime(iso)}`;

export default function App() {
  const [auth, setAuth] = useState(() => session.load());
  const [tab, setTab] = useState("book");
  const [notice, setNotice] = useState(null);

  const say = useCallback((text, kind = "ok") => setNotice({ text, kind }), []);

  useEffect(() => {
    const onLogout = () => {
      setAuth(null);
      setNotice({ text: "Your session expired. Log in again.", kind: "error" });
    };
    window.addEventListener("slotdesk:logout", onLogout);
    return () => window.removeEventListener("slotdesk:logout", onLogout);
  }, []);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 5000);
    return () => clearTimeout(t);
  }, [notice]);

  const logout = () => {
    session.clear();
    setAuth(null);
    setTab("book");
  };

  return (
    <>
      <header className="bar">
        <div className="bar-inner">
          <span className="brand">SlotDesk</span>
          {auth && (
            <nav aria-label="Main">
              <button className={tab === "book" ? "tab on" : "tab"} onClick={() => setTab("book")}>Book a slot</button>
              <button className={tab === "mine" ? "tab on" : "tab"} onClick={() => setTab("mine")}>My bookings</button>
              {auth.user.role === "admin" && (
                <button className={tab === "admin" ? "tab on" : "tab"} onClick={() => setTab("admin")}>Manage</button>
              )}
            </nav>
          )}
          {auth && (
            <div className="who">
              <span>{auth.user.name}</span>
              <button className="link" onClick={logout}>Log out</button>
            </div>
          )}
        </div>
      </header>

      <main>
        {notice && <p role="status" className={`notice ${notice.kind}`}>{notice.text}</p>}
        {!auth && <AuthForm onAuth={(a) => { session.save(a); setAuth(a); }} say={say} />}
        {auth && tab === "book" && <BookTab say={say} />}
        {auth && tab === "mine" && <MyBookings say={say} />}
        {auth && tab === "admin" && auth.user.role === "admin" && <AdminTab say={say} />}
      </main>
    </>
  );
}

/* ---------- auth ---------- */
function AuthForm({ onAuth, say }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const body = mode === "login" ? { email: form.email, password: form.password } : form;
      onAuth(await api(`/auth/${mode === "login" ? "login" : "register"}`, { method: "POST", body }));
    } catch (err) {
      say(err.message, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="auth">
      <h1>Book a municipal service appointment</h1>
      <p className="lede">Pick a free time, get it confirmed, cancel any time.</p>
      <form onSubmit={submit}>
        {mode === "register" && (
          <label>Full name<input value={form.name} onChange={set("name")} autoComplete="name" required /></label>
        )}
        <label>Email<input type="email" value={form.email} onChange={set("email")} autoComplete="email" required /></label>
        <label>Password
          <input type="password" value={form.password} onChange={set("password")} minLength={mode === "register" ? 8 : undefined}
                 autoComplete={mode === "login" ? "current-password" : "new-password"} required />
        </label>
        <button className="primary" disabled={busy}>{mode === "login" ? "Log in" : "Create account"}</button>
      </form>
      <button className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "New here? Create an account" : "Already registered? Log in"}
      </button>
      <p className="hint">Demo: demo@slotdesk.test / demo12345 · Admin: admin@slotdesk.test / admin12345</p>
    </section>
  );
}

/* ---------- booking ---------- */
function BookTab({ say }) {
  const [services, setServices] = useState([]);
  const [service, setService] = useState("");
  const [slots, setSlots] = useState(null);
  const [picked, setPicked] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setSlots(await api(`/slots${service ? `?service=${encodeURIComponent(service)}` : ""}`));
    } catch (err) {
      say(err.message, "error");
    }
  }, [service, say]);

  useEffect(() => { api("/services").then(setServices).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);

  const days = useMemo(() => {
    const map = new Map();
    (slots || []).forEach((s) => {
      const key = new Date(s.starts_at).toDateString();
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(s);
    });
    return [...map.values()];
  }, [slots]);

  const confirm = async () => {
    setBusy(true);
    try {
      await api("/bookings", { method: "POST", body: { slot_id: picked.id, note } });
      say(`Booked: ${picked.service}, ${fmtWhen(picked.starts_at)}.`);
      setPicked(null);
      setNote("");
    } catch (err) {
      say(err.message, "error");
      setPicked(null);
    } finally {
      await load();
      setBusy(false);
    }
  };

  return (
    <section>
      <div className="row-head">
        <h2>Available times</h2>
        <label className="inline">Service
          <select value={service} onChange={(e) => setService(e.target.value)}>
            <option value="">All services</option>
            {services.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
      </div>

      {slots === null && <p className="empty">Loading times…</p>}
      {slots && slots.length === 0 && <p className="empty">No upcoming slots for this service. Check back soon.</p>}

      <div className="board">
        {days.map((daySlots) => (
          <div className="day" key={daySlots[0].starts_at.slice(0, 10)}>
            <h3>{fmtDay(daySlots[0].starts_at)}</h3>
            <ul>
              {daySlots.map((s) => {
                const mine = s.my_booking_id != null;
                const taken = s.booked && !mine;
                return (
                  <li key={s.id}>
                    <button
                      className={`cell ${taken ? "taken" : mine ? "mine" : "free"} ${picked?.id === s.id ? "picked" : ""}`}
                      disabled={s.booked}
                      onClick={() => setPicked(s)}
                      aria-label={`${s.service}, ${fmtWhen(s.starts_at)}, ${taken ? "taken" : mine ? "booked by you" : "available"}`}
                    >
                      <b>{fmtTime(s.starts_at)}</b>
                      <span>{s.service}</span>
                      <em>{taken ? "Taken" : mine ? "Yours" : `${s.duration_min} min`}</em>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      {picked && (
        <div className="confirm" role="dialog" aria-label="Confirm booking">
          <p><b>{picked.service}</b><br />{fmtWhen(picked.starts_at)} · {picked.duration_min} min</p>
          <label>Note for the office (optional)
            <textarea rows={2} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div className="actions">
            <button className="primary" onClick={confirm} disabled={busy}>Confirm booking</button>
            <button className="link" onClick={() => setPicked(null)}>Choose another time</button>
          </div>
        </div>
      )}
    </section>
  );
}

/* ---------- my bookings ---------- */
function BookingList({ items, onCancel, showUser }) {
  return (
    <ul className="list">
      {items.map((b) => (
        <li key={b.id} className={b.status === "cancelled" ? "gone" : ""}>
          <div>
            <b>{b.service}</b>
            <span>{fmtWhen(b.starts_at)} · {b.duration_min} min</span>
            {showUser && <span>{b.user_name} ({b.user_email})</span>}
            {b.note && <span className="note">“{b.note}”</span>}
          </div>
          {b.status === "active"
            ? <button className="danger" onClick={() => onCancel(b)}>Cancel booking</button>
            : <em>Cancelled</em>}
        </li>
      ))}
    </ul>
  );
}

function MyBookings({ say }) {
  const [items, setItems] = useState(null);
  const load = useCallback(() => api("/bookings").then(setItems).catch((e) => say(e.message, "error")), [say]);
  useEffect(() => { load(); }, [load]);

  const cancel = async (b) => {
    try {
      await api(`/bookings/${b.id}`, { method: "DELETE" });
      say(`Cancelled: ${b.service}, ${fmtWhen(b.starts_at)}.`);
    } catch (err) {
      say(err.message, "error");
    }
    load();
  };

  return (
    <section>
      <h2>My bookings</h2>
      {items === null && <p className="empty">Loading…</p>}
      {items && items.length === 0 && <p className="empty">You have no bookings yet. Pick a time under “Book a slot”.</p>}
      {items && <BookingList items={items} onCancel={cancel} />}
    </section>
  );
}

/* ---------- admin ---------- */
function AdminTab({ say }) {
  const [items, setItems] = useState(null);
  const [form, setForm] = useState({ service: "", when: "", duration: 30 });
  const load = useCallback(() => api("/admin/bookings").then(setItems).catch((e) => say(e.message, "error")), [say]);
  useEffect(() => { load(); }, [load]);

  const addSlot = async (e) => {
    e.preventDefault();
    try {
      await api("/slots", { method: "POST", body: {
        service: form.service, starts_at: new Date(form.when).toISOString(), duration_min: Number(form.duration),
      } });
      say(`Slot added: ${form.service}, ${fmtWhen(new Date(form.when).toISOString())}.`);
      setForm({ ...form, when: "" });
    } catch (err) {
      say(err.message, "error");
    }
  };

  const cancel = async (b) => {
    try {
      await api(`/bookings/${b.id}`, { method: "DELETE" });
      say(`Cancelled booking for ${b.user_name}.`);
    } catch (err) {
      say(err.message, "error");
    }
    load();
  };

  return (
    <section>
      <h2>Add a slot</h2>
      <form className="slot-form" onSubmit={addSlot}>
        <label>Service<input value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value })} required /></label>
        <label>Date and time<input type="datetime-local" value={form.when} onChange={(e) => setForm({ ...form, when: e.target.value })} required /></label>
        <label>Minutes<input type="number" min={5} max={240} value={form.duration} onChange={(e) => setForm({ ...form, duration: e.target.value })} required /></label>
        <button className="primary">Add slot</button>
      </form>

      <h2>Upcoming bookings</h2>
      {items === null && <p className="empty">Loading…</p>}
      {items && items.length === 0 && <p className="empty">No active bookings.</p>}
      {items && <BookingList items={items} onCancel={cancel} showUser />}
    </section>
  );
}
