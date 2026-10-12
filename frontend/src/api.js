const KEY = "slotdesk.session";

export const session = {
  load() {
    try {
      return JSON.parse(localStorage.getItem(KEY));
    } catch {
      return null;
    }
  },
  save(value) {
    localStorage.setItem(KEY, JSON.stringify(value));
  },
  clear() {
    localStorage.removeItem(KEY);
  },
};

/** Thin fetch wrapper: adds the token, parses JSON, throws Error(message) on failure. */
export async function api(path, { method = "GET", body } = {}) {
  const current = session.load();
  const res = await fetch(`/api${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(current ? { Authorization: `Bearer ${current.token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && current) {
      session.clear();
      window.dispatchEvent(new Event("slotdesk:logout"));
    }
    throw new Error(data.error || "Something went wrong. Try again.");
  }
  return data;
}
