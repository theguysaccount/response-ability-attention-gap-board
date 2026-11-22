// End-to-end self-test, loaded only with ?selftest=1. It drives the real page and checks the result against its
// own scoring code (independent of core.js). scripts/e2e.sh reads <body data-selftest="pass|fail: ...">.
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function until(fn, what, ms = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const v = fn();
    if (v) return v;
    await wait(25);
  }
  throw new Error("timed out waiting for " + what);
}

function expectedWinner(board, declared) {
  // Independent re-implementation: cosine of shape, squared, times the neglect index.
  let best = null;
  for (const c of board.causes) {
    let dot = 0, a = 0, b = 0;
    for (const cap of board.capabilities) {
      const u = declared[cap.id] || 0, n = c.need[cap.id] || 0;
      dot += u * n; a += u * u; b += n * n;
    }
    const s = a && b ? c.neglect * (dot * dot) / (a * b) : 0;
    if (!best || s > best.s + 1e-12 || (Math.abs(s - best.s) <= 1e-12 && c.rank < best.c.rank)) best = { c, s };
  }
  return best;
}

async function board(log) {
  const data = JSON.parse(document.getElementById("board-data").textContent);
  const rows = document.querySelectorAll("tbody tr");
  if (rows.length !== data.causes.length + 1) throw new Error(`table has ${rows.length} rows, data has ${data.causes.length} + 1`);
  const ranks = [...rows].slice(0, -1).map((r) => Number(r.querySelector(".rk").textContent));
  if (ranks.some((v, i) => v !== i + 1)) throw new Error("ranks are not 1..n in order");
  const vpds = data.causes.map((c) => c.vpd);
  if (vpds.some((v, i) => i && v < vpds[i - 1])) throw new Error("board is not sorted by views per death");
  log.push(`board: ${data.causes.length} causes in order, reference row last`);

  const declared = { CLINICAL: 3, FIELD: 2 };
  for (const [cap, v] of Object.entries(declared)) document.querySelector(`.seg[data-cap="${cap}"] button[data-v="${v}"]`).click();
  document.querySelector('[data-group="rarity"] button[data-i="2"]').click();
  document.querySelector('[data-group="scale"] button[data-i="1"]').click();
  document.getElementById("run").click();
  const card = await until(() => document.querySelector("[data-assignment]"), "the assignment card");
  const want = expectedWinner(data, declared);
  if (card.dataset.assignment !== want.c.id) throw new Error(`assigned ${card.dataset.assignment}, expected ${want.c.id}`);
  const total = Number(card.querySelector("[data-total]").textContent);
  const expect = want.s * data.rarity[2][1] * data.scale[1][1];
  if (Math.abs(total - expect) > 0.051) throw new Error(`total ${total}, expected ${expect.toFixed(2)}`);
  log.push(`assignment: ${want.c.name} (score ${total}), matches the independent check`);
  if (!/c=CLINICAL\.3,FIELD\.2&r=2&s=1|c=FIELD\.2,CLINICAL\.3&r=2&s=1/.test(location.hash)) throw new Error("hash not written: " + location.hash);

  document.getElementById("res-text").value = "By the date, a named clinic will have adopted the protocol, confirmed in writing.";
  document.getElementById("res-text").dispatchEvent(new Event("input"));
  const pub = card.querySelector('[data-act="public"]').getAttribute("href");
  const u = new URL(pub);
  if (u.hostname !== "github.com" || u.searchParams.get("template") !== "commitment.yml" || !u.searchParams.get("condition"))
    throw new Error("public-commitment link is wrong: " + pub);
  log.push("public-commitment link prefilled");

  return log;
}

async function cause(log) {
  const h1 = document.querySelector("h1");
  if (!h1 || !h1.textContent.trim()) throw new Error("no heading");
  const src = document.querySelector("blockquote footer a");
  if (!src || !/^https:\/\//.test(src.href)) throw new Error("no source link");
  const bars = document.querySelectorAll(".spark rect");
  if (bars.length !== 12) throw new Error(`sparkline has ${bars.length} bars`);
  if (!document.querySelector(".verify")) throw new Error("no verification line");
  log.push(`cause page: ${h1.textContent.trim()}, source and 12-month sparkline present`);
  return log;
}

export async function run(kind) {
  const log = [];
  const pre = document.createElement("pre");
  pre.id = "selftest";
  try {
    await (kind === "board" ? board(log) : cause(log));
    document.body.dataset.selftest = "pass";
  } catch (err) {
    log.push("FAIL: " + err.message);
    document.body.dataset.selftest = "fail: " + err.message;
  }
  pre.textContent = log.join("\n");
  document.body.appendChild(pre);
}
