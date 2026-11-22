// node --test tests/js.test.mjs : the pure functions in site/assets/core.js.
import test from "node:test";
import assert from "node:assert/strict";
import { assign, encode, decode, icsFile, issueUrl, addDays, topCaps } from "../site/assets/core.js";

const caps = ["A", "B", "C"].map((id) => ({ id, label: id }));
const board = {
  capabilities: caps, rarity: [["x", 1], ["y", 2]], scale: [["s", 1], ["t", 2], ["u", 4]],
  causes: [
    { id: "most-neglected", rank: 1, neglect: 2.5, need: { A: 1, B: 1, C: 1 } },
    { id: "a-shaped", rank: 2, neglect: 2, need: { A: 3, B: 0, C: 0 } },
    { id: "c-shaped", rank: 3, neglect: 1, need: { A: 0, B: 0, C: 3 } },
  ],
};

test("a specialist goes to the cause shaped like them", () => {
  assert.equal(assign(board, { A: 3 }, 1, 1)[0].id, "a-shaped");
  assert.equal(assign(board, { C: 2 }, 1, 1)[0].id, "c-shaped");
});

test("declaring everything favours the broad, more neglected cause", () => {
  assert.equal(assign(board, { A: 3, B: 3, C: 3 }, 1, 1)[0].id, "most-neglected");
});

test("an empty declaration scores zero and ties go to the most neglected", () => {
  const r = assign(board, {}, 2, 4);
  assert.ok(r.every((x) => x.total === 0));
  assert.equal(r[0].id, "most-neglected");
});

test("rarity and scale scale the score but never change the winner", () => {
  const a = assign(board, { A: 2, C: 1 }, 1, 1).map((x) => x.id);
  const b = assign(board, { A: 2, C: 1 }, 8, 8).map((x) => x.id);
  assert.deepEqual(a, b);
});

test("the hash round-trips and rejects junk", () => {
  const h = encode({ A: 3, B: 0, C: 1 }, 1, 2);
  assert.equal(h, "c=A.3,C.1&r=1&s=2");
  assert.deepEqual(decode("#" + h, board), { declared: { A: 3, C: 1 }, rarityIdx: 1, scaleIdx: 2 });
  assert.deepEqual(decode("#c=A.9,Z.2,B.1&r=7&s=-1", board), { declared: { B: 1 }, rarityIdx: null, scaleIdx: null });
  assert.equal(decode("#nothing", board), null);
});

test("calendar file is a valid all-day event with folded lines", () => {
  const ics = icsFile({ title: "Resolution check: Drowning", description: "x".repeat(200) + ", with; commas\nand lines",
    date: "2027-02-20", url: "https://example.org/cause/drowning/", uid: "u@x", stamp: "20261122T080000Z" });
  assert.match(ics, /DTSTART;VALUE=DATE:20270220\r\n/);
  assert.match(ics, /DTEND;VALUE=DATE:20270221\r\n/);
  const unfolded = ics.replace(/\r\n /g, "");   // RFC 5545 folding may split an escape across lines
  assert.ok(unfolded.includes(String.raw`\, with\; commas\nand lines`), unfolded);
  for (const line of ics.split("\r\n")) assert.ok(line.length <= 75, line);
});

test("the public-commitment link prefills the issue form", () => {
  const u = new URL(issueUrl("o/r", { cause: "Drowning", condition: "By X, Y.", date: "2027-02-20", capabilities: "Field: strong" }));
  assert.equal(u.origin + u.pathname, "https://github.com/o/r/issues/new");
  assert.equal(u.searchParams.get("template"), "commitment.yml");
  assert.equal(u.searchParams.get("condition"), "By X, Y.");
  assert.equal(u.searchParams.get("date"), "2027-02-20");
});

test("dates and top capabilities", () => {
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.deepEqual(topCaps(board, board.causes[0], { A: 1, C: 3 }).map((x) => x.id), ["C", "A"]);
});
