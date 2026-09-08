let token = new URLSearchParams(
  typeof location !== "undefined" ? location.search : ""
).get("token") || "";

export function setToken(t) { token = t; }
export function getToken() { return token; }

export async function apiGet(path) {
  const r = await fetch(path, { headers: { "X-Sparks-Token": token } });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export async function apiPost(path, body = {}) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "X-Sparks-Token": token, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
