const BASE = "http://localhost:8000/api";

async function get(path) {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) {
    const body = await r.text();
    throw new Error(body || `${r.status} ${r.statusText}`);
  }
  return r.json();
}

async function post(path) {
  const r = await fetch(`${BASE}${path}`, { method: "POST" });
  if (!r.ok) {
    const body = await r.text();
    throw new Error(body || `${r.status} ${r.statusText}`);
  }
  return r.json();
}

export const api = {
  funds:           ()           => get("/funds"),
  holdings:        (fundId)     => get(`/funds/${fundId}/holdings`),
  proxy:           (ticker)     => get(`/proxies/${ticker}`),
  recommendations: (ticker)     => get(`/proxies/${ticker}/recommendations`),
  refresh:         (ticker)     => post(`/proxies/${ticker}/refresh`),
  policy:          ()           => get("/policy"),
};
