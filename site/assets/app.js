// The declare -> assignment flow on the board page. Nothing typed here leaves the browser unless the visitor
// chooses to post a commitment on GitHub themselves.
import { LEVELS, assign, topCaps, encode, decode, addDays, icsFile, issueUrl, commitmentText } from "./core.js";

const board = JSON.parse(document.getElementById("board-data").textContent);
const form = document.getElementById("declare-form");
const out = document.getElementById("out");
const hint = document.getElementById("hint");
const runBtn = document.getElementById("run");
const state = { declared: {}, rarityIdx: null, scaleIdx: null };
board.capabilities.forEach((c) => (state.declared[c.id] = 0));

const esc = (s) => String(s).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
const fmt = (n) => Number(n).toLocaleString("en-US");
const count = (name) => { try { window.goatcounter && window.goatcounter.count({ path: name, title: name, event: true }); } catch (_) { /* analytics is optional */ } };
const base = board.site.url.replace(/\/$/, "") + "/";
const today = () => new Date().toISOString().slice(0, 10);

function press(group, value) {
  [...group.querySelectorAll("button")].forEach((b) => b.setAttribute("aria-pressed", String(b === value)));
}

function ready() {
  const anyCap = Object.values(state.declared).some((v) => v > 0);
  const ok = anyCap && state.rarityIdx !== null && state.scaleIdx !== null;
  runBtn.setAttribute("aria-disabled", String(!ok));
  hint.textContent = ok ? "One cause comes back. Not a list."
    : !anyCap ? "Set at least one capability above none, then rarity and scale."
      : "Answer rarity and scale: they multiply your score.";
  return ok;
}

form.addEventListener("click", (ev) => {
  const b = ev.target.closest("button[type=button]");
  if (!b) return;
  const seg = b.closest(".seg");
  if (seg.dataset.cap) state.declared[seg.dataset.cap] = Number(b.dataset.v);
  else if (seg.dataset.group === "rarity") state.rarityIdx = Number(b.dataset.i);
  else if (seg.dataset.group === "scale") state.scaleIdx = Number(b.dataset.i);
  press(seg, b);
  ready();
});

form.addEventListener("submit", (ev) => {
  ev.preventDefault();
  if (!ready()) { hint.focus?.(); return; }
  render(true);
});

function render(scroll) {
  const rarity = board.rarity[state.rarityIdx][1];
  const scale = board.scale[state.scaleIdx][1];
  const ranked = assign(board, state.declared, rarity, scale);
  history.replaceState(null, "", "#" + encode(state.declared, state.rarityIdx, state.scaleIdx));
  const win = ranked[0];
  if (!win || win.total === 0) {
    out.innerHTML = `<div class="assign"><div class="abody"><p>Nothing on this board matches what you declared. That is a real
      answer, not a failure: your ability to respond is somewhere this board does not cover yet.
      <a href="${esc(board.site.url)}/method/">How matching works</a>.</p></div></div>`;
    if (scroll) out.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  const c = board.causes.find((x) => x.id === win.id);
  const caps = topCaps(board, c, state.declared);
  const runners = ranked.slice(1, 4).map((r) => {
    const rc = board.causes.find((x) => x.id === r.id);
    return `<a href="${esc(rc.url)}">${esc(rc.name)}</a> (${r.total.toFixed(1)})`;
  }).join(" &middot; ");
  const refVpd = board.reference.vpd;
  const orgs = c.orgs.map((o) => `<a href="${esc(o.url)}" rel="noopener">${esc(o.name)}</a>`).join(" and ");
  const support = c.support_note ? `<aside class="support" role="note"><p><strong>${esc(board.support.text)}</strong></p><p>${
    board.support.links.map((l) => `<a href="${esc(l.url)}" rel="noopener">${esc(l.name)}</a>`).join(" ")}</p></aside>` : "";
  const due = addDays(today(), 90);
  out.innerHTML = `
  <div class="assign" data-assignment="${esc(c.id)}">
    <div class="ahead">
      <div class="aeyebrow">You have the greatest ability to respond to</div>
      <h2 class="atitle" id="assignment-title"><a href="${esc(c.url)}">${esc(c.name)}</a></h2>
      <div class="astat">Deaths a year: ${esc(c.toll)}${c.period === "annual" ? "" : ` (${esc(c.period)})`} &middot;
        ${esc(c.vpd_text)} Wikipedia views per death${c.support_note ? "" : ` &middot; a shark-attack death draws ${fmt(Math.round(refVpd / c.vpd))}&times; more`}</div>
    </div>
    <div class="abody">
      ${support}
      <div class="blk"><h3>What would move it</h3><p>${esc(c.lever)}</p></div>
      <div class="blk"><h3>Why you</h3><p>Your <strong>${caps.map((x) => esc(x.label.toLowerCase())).join(", ")}</strong>
        ${caps.length > 1 ? "capabilities are" : "capability is"} what this cause is short of. Your declaration matches
        <strong>${Math.round(win.fit * 100)}%</strong> of the shape of what it needs, and you said that
        <strong>${esc(board.rarity[state.rarityIdx][0])}</strong> of the people you know could do the same.</p></div>
      <div class="blk"><h3>The math, shown</h3><div class="math" data-math>
        neglect index <b>${win.neglect.toFixed(3)}</b> &times; fit&sup2; <b>${win.fit.toFixed(3)}</b> &times;
        rarity <b>${rarity}</b> &times; scale <b>${scale}</b> = <span class="win" data-total>${win.total.toFixed(1)}</span>
        <div>runners-up: ${runners}</div></div></div>
      <div class="blk"><h3>Someone already doing it</h3><p>${orgs}: read what they are blocked on before you build anything.
        Removing someone else's constraint is usually faster than starting a parallel effort. (Listed for reference; they do
        not run or endorse this board.)</p></div>
      <div class="blk"><h3>Write your resolution condition</h3>
        <p>One sentence that will be either true or false on a date. Not "raise awareness of". Not "explore".</p>
        <label class="lab" for="res-text">Resolution condition</label>
        <textarea class="res" id="res-text" rows="3" maxlength="600"
          placeholder="By [date], [specific thing] will have happened, and anyone can check it by [how]."></textarea>
        <label class="lab" for="res-date">Resolution date</label>
        <input class="datein" id="res-date" type="date" min="${addDays(today(), 1)}" value="${due}">
        <div class="actions">
          <button type="button" data-act="copy">Copy my commitment</button>
          <button type="button" class="secondary" data-act="ics">Add the date to my calendar</button>
          <a class="secondary" data-act="public" href="#" rel="noopener" target="_blank">Post it publicly (optional)</a>
          <button type="button" class="secondary" data-act="share">Share this cause</button>
        </div>
        <p class="status" id="act-status" role="status"></p>
        <p class="small">Nothing is stored or sent by this site. "Post it publicly" opens a GitHub issue form under your own
        GitHub account; close the issue as completed if the condition came true, or as not planned if it did not, and the
        <a href="${esc(board.site.url)}/record/">public record</a> counts it.</p>
      </div>
    </div>
  </div>`;
  wire(c);
  count("assignment");
  if (scroll) document.getElementById("assignment-title").scrollIntoView({ behavior: "smooth", block: "start" });
}

function wire(c) {
  const text = document.getElementById("res-text");
  const date = document.getElementById("res-date");
  const status = document.getElementById("act-status");
  const pub = out.querySelector('[data-act="public"]');
  const causeUrl = base + c.url;
  const valid = () => {
    if (!text.value.trim()) { status.textContent = "Write the condition first: one sentence that will be true or false."; text.focus(); return false; }
    if (!date.value || date.value <= today()) { status.textContent = "Pick a resolution date in the future."; date.focus(); return false; }
    return true;
  };
  const capsText = () => Object.entries(state.declared).filter(([, v]) => v > 0)
    .map(([k, v]) => `${board.capabilities.find((x) => x.id === k).label}: ${LEVELS[v]}`).join(", ");
  const updatePublic = () => {
    pub.href = issueUrl(board.site.repo, { cause: c.name, condition: text.value.trim(), date: date.value, capabilities: capsText() });
  };
  text.addEventListener("input", updatePublic);
  date.addEventListener("change", updatePublic);
  updatePublic();
  out.querySelector(".actions").addEventListener("click", async (ev) => {
    const act = ev.target.closest("[data-act]")?.dataset.act;
    if (!act) return;
    if (act === "share") {
      ev.preventDefault();
      const data = { title: `${c.name}: ${c.vpd_text} views per death`, text: `${c.name}: ${c.toll} deaths a year, ${c.vpd_text} Wikipedia views per death.`, url: causeUrl };
      try {
        if (navigator.share) await navigator.share(data);
        else { await navigator.clipboard.writeText(causeUrl); status.textContent = "Link to the cause page copied."; }
        count("share");
      } catch (_) { status.textContent = causeUrl; }
      return;
    }
    if (act === "public") {
      if (!valid()) { ev.preventDefault(); return; }
      updatePublic();
      count("commit-public");
      return;
    }
    if (!valid()) return;
    if (act === "copy") {
      const t = commitmentText({ cause: c.name, condition: text.value.trim(), date: date.value, url: causeUrl });
      try { await navigator.clipboard.writeText(t); status.textContent = "Copied. Keep it somewhere you will see it on the date."; }
      catch (_) { status.textContent = t; }
      count("commit-copy");
    } else if (act === "ics") {
      const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
      const ics = icsFile({ title: `Resolution check: ${c.name}`, description: `${text.value.trim()}\n\n${causeUrl}`, date: date.value,
        url: causeUrl, uid: `${c.id}-${date.value}-${Date.now()}@attention-gap-board`, stamp });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([ics], { type: "text/calendar" }));
      a.download = `resolution-${c.id}-${date.value}.ics`;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
      status.textContent = "Calendar file downloaded. Open it to add the date.";
      count("commit-ics");
    }
  });
}

function restore() {
  const d = decode(location.hash, board);
  if (!d) return false;
  Object.assign(state.declared, d.declared);
  state.rarityIdx = d.rarityIdx;
  state.scaleIdx = d.scaleIdx;
  form.querySelectorAll(".seg[data-cap]").forEach((seg) => {
    press(seg, seg.querySelector(`button[data-v="${state.declared[seg.dataset.cap] || 0}"]`));
  });
  if (state.rarityIdx !== null) press(form.querySelector('[data-group="rarity"]'), form.querySelector(`[data-group="rarity"] button[data-i="${state.rarityIdx}"]`));
  if (state.scaleIdx !== null) press(form.querySelector('[data-group="scale"]'), form.querySelector(`[data-group="scale"] button[data-i="${state.scaleIdx}"]`));
  return ready();
}

if (restore()) render(false);
else ready();

if (new URLSearchParams(location.search).has("selftest")) import("./selftest.js").then((m) => m.run("board"));
