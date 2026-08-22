function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function fmtTime(ts) {
  if (!ts) return "";
  try { return new Date(ts).toLocaleString(undefined, {month:"short", day:"numeric", hour:"2-digit", minute:"2-digit"}); }
  catch { return ts; }
}

function shortId(id) { return id ? id.slice(0, 8) : ""; }

async function api(path, opts) {
  const res = await fetch(path, opts);
  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const body = isJson ? await res.json() : null;
  if (!res.ok) throw new Error((body && body.error) || `Request failed (${res.status})`);
  return body;
}
