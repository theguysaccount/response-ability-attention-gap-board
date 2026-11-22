// Pure functions behind the assignment. No DOM access, so node --test can import this file.
// The scoring mirrors board/data.py (score/assign); tests/test_parity.py checks they agree.

export const LEVELS = ["none", "some", "strong", "decisive"];

export function score(cause, caps, declared, rarity, scale) {
  let dot = 0, un = 0, gn = 0;
  for (const cap of caps) {
    const u = Number(declared[cap] || 0);
    const n = Number(cause.need[cap] || 0);
    dot += u * n;
    un += u * u;
    gn += n * n;
  }
  const cos = un && gn ? dot / (Math.sqrt(un) * Math.sqrt(gn)) : 0;
  const fit = cos * cos;
  return { id: cause.id, cos, fit, neglect: cause.neglect, total: cause.neglect * fit * rarity * scale };
}

const r12 = (x) => Math.round(x * 1e12) / 1e12;

// Every cause scored, best first. Ties go to the more neglected cause (the lower rank).
export function assign(board, declared, rarity, scale) {
  const caps = board.capabilities.map((c) => c.id);
  const rank = Object.fromEntries(board.causes.map((c) => [c.id, c.rank]));
  return board.causes
    .map((c) => score(c, caps, declared, rarity, scale))
    .sort((a, b) => r12(b.total) - r12(a.total) || rank[a.id] - rank[b.id]);
}

// The capabilities that drive the match: largest need x declared first, at most n.
export function topCaps(board, cause, declared, n = 3) {
  return board.capabilities
    .map((c) => ({ id: c.id, label: c.label, v: Number(cause.need[c.id] || 0) * Number(declared[c.id] || 0) }))
    .filter((x) => x.v > 0)
    .sort((a, b) => b.v - a.v)
    .slice(0, n);
}

// Declarations live in the URL fragment so a link reproduces an assignment: #c=BUILD.3,FIELD.2&r=1&s=2
export function encode(declared, rarityIdx, scaleIdx) {
  const c = Object.entries(declared).filter(([, v]) => v > 0).map(([k, v]) => `${k}.${v}`).join(",");
  return `c=${c}&r=${rarityIdx}&s=${scaleIdx}`;
}

export function decode(hash, board) {
  const params = new URLSearchParams(String(hash || "").replace(/^#/, ""));
  if (!params.has("c")) return null;
  const valid = new Set(board.capabilities.map((c) => c.id));
  const declared = {};
  for (const part of (params.get("c") || "").split(",")) {
    const [k, v] = part.split(".");
    const n = Number(v);
    if (valid.has(k) && Number.isInteger(n) && n >= 0 && n <= 3) declared[k] = n;
  }
  const r = Number(params.get("r"));
  const s = Number(params.get("s"));
  const rarityIdx = Number.isInteger(r) && r >= 0 && r < board.rarity.length ? r : null;
  const scaleIdx = Number.isInteger(s) && s >= 0 && s < board.scale.length ? s : null;
  return { declared, rarityIdx, scaleIdx };
}

export function addDays(iso, days) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

const icsEscape = (s) => String(s).replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");

// Fold lines at 75 octets as RFC 5545 asks (counting UTF-16 units is close enough for our ASCII-heavy text).
const fold = (line) => {
  const out = [];
  let rest = line;
  while (rest.length > 74) {
    out.push(rest.slice(0, 74));
    rest = " " + rest.slice(74);
  }
  out.push(rest);
  return out.join("\r\n");
};

// An all-day calendar event on the resolution date. Generated in the browser; nothing is sent.
export function icsFile({ title, description, date, url, uid, stamp }) {
  const day = date.replace(/-/g, "");
  const next = addDays(date, 1).replace(/-/g, "");
  const lines = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//attention-gap-board//assignment//EN", "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT", `UID:${uid}`, `DTSTAMP:${stamp}`, `DTSTART;VALUE=DATE:${day}`, `DTEND;VALUE=DATE:${next}`,
    `SUMMARY:${icsEscape(title)}`, `DESCRIPTION:${icsEscape(description)}`, `URL:${url}`,
    "BEGIN:VALARM", "ACTION:DISPLAY", `DESCRIPTION:${icsEscape(title)}`, "TRIGGER:-PT0M", "END:VALARM",
    "END:VEVENT", "END:VCALENDAR",
  ];
  return lines.map(fold).join("\r\n") + "\r\n";
}

// A prefilled GitHub issue form. The visitor submits it under their own account, or not at all.
export function issueUrl(repo, { cause, condition, date, capabilities }) {
  const title = `${cause}: resolves ${date}`;
  const q = new URLSearchParams({ template: "commitment.yml", title, cause, condition, date, capabilities });
  return `https://github.com/${repo}/issues/new?${q.toString()}`;
}

export function commitmentText({ cause, condition, date, url }) {
  return `My assignment from the attention gap board: ${cause}.\nResolution condition: ${condition}\nResolves on: ${date}\n${url}`;
}
