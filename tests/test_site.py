"""The static build: every page, the sitemap, indexing switches, and states derived from data (never pinned)."""
import json
import os
import re
import shutil
import tempfile
import unittest

from board import data as D
from board import site as S


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.mkdtemp()
        cls.site, cls.board = S.build(os.path.join(cls.out, "dist"), env={"SITE_URL": "https://example.org/agb"})
        cls.dist = os.path.join(cls.out, "dist")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def read(self, path):
        with open(os.path.join(self.dist, path), encoding="utf-8") as fh:
            return fh.read()

    def test_every_cause_has_a_page_in_the_sitemap(self):
        sitemap = self.read("sitemap.xml")
        for row in self.board["causes"]:
            page = self.read("cause/%s/index.html" % row["id"])
            self.assertIn(row["source"]["url"], page)
            self.assertIn("https://example.org/agb/cause/%s/" % row["id"], sitemap)
            self.assertIn('<link rel="canonical" href="https://example.org/agb/cause/%s/">' % row["id"], page)

    def test_pages_are_indexable_and_robots_points_at_the_sitemap(self):
        self.assertNotIn("noindex", self.read("index.html"))
        self.assertIn("Sitemap: https://example.org/agb/sitemap.xml", self.read("robots.txt"))
        self.assertIn("noindex", self.read("embed/index.html"))

    def test_home_lists_every_cause_in_rank_order(self):
        home = self.read("index.html")
        positions = [home.index('href="cause/%s/"' % r["id"]) for r in self.board["causes"]]
        self.assertEqual(positions, sorted(positions))
        data = json.loads(re.search(r'<script type="application/json" id="board-data">(.*?)</script>', home, re.S).group(1))
        self.assertEqual([c["id"] for c in data["causes"]], [r["id"] for r in self.board["causes"]])

    def test_crisis_support_on_flagged_causes(self):
        causes = D.read_json("causes.json")
        for row in causes["causes"]:
            page = self.read("cause/%s/index.html" % row["id"])
            self.assertEqual(causes["support"]["links"][0]["url"] in page, bool(row.get("support_note")), row["id"])

    def test_csv_has_a_row_per_cause_plus_reference(self):
        lines = self.read("data/board.csv").strip().split("\n")
        self.assertEqual(len(lines), len(self.board["causes"]) + 2)

    def test_indexnow_key_is_published(self):
        key = open(os.path.join(S.SITE, "indexnow-key.txt")).read().strip()
        self.assertEqual(self.read("%s.txt" % key).strip(), key)

    def test_no_personal_contact_in_pages(self):
        for root, _, files in os.walk(self.dist):
            for f in files:
                if f.endswith((".html", ".json", ".xml", ".txt", ".csv")):
                    text = open(os.path.join(root, f), encoding="utf-8").read()
                    self.assertIsNone(re.search(r"[\w.+-]+@(gmail|yahoo|hotmail|outlook)\.com", text), f)


class Noindex(unittest.TestCase):
    def test_noindex_build_blocks_everything(self):
        out = tempfile.mkdtemp()
        try:
            S.build(os.path.join(out, "d"), env={"SITE_INDEXABLE": "false"})
            self.assertIn("Disallow: /", open(os.path.join(out, "d", "robots.txt")).read())
            self.assertFalse(os.path.exists(os.path.join(out, "d", "sitemap.xml")))
            self.assertIn('content="noindex"', open(os.path.join(out, "d", "index.html")).read())
        finally:
            shutil.rmtree(out, ignore_errors=True)


class Falsifier(unittest.TestCase):
    causes = {"launched": "2026-11-22"}

    def test_running_before_the_deadline(self):
        state, _ = S.falsifier_state(self.causes, {"came_true": 0}, "2026-12-01")
        self.assertEqual(state, "running")

    def test_passed_when_a_condition_came_true_in_time(self):
        state, text = S.falsifier_state(self.causes, {"came_true": 1, "first_true": "2027-02-01"}, "2027-08-01")
        self.assertEqual(state, "passed")
        self.assertIn("1 February 2027", text)

    def test_failed_after_the_deadline_without_one(self):
        state, _ = S.falsifier_state(self.causes, {"came_true": 0}, "2027-06-01")
        self.assertEqual(state, "failed")

    def test_late_success_does_not_rescue_it(self):
        state, _ = S.falsifier_state(self.causes, {"came_true": 1, "first_true": "2027-07-01"}, "2027-08-01")
        self.assertEqual(state, "failed")


class Verification(unittest.TestCase):
    row = {"id": "x", "source": {"quote": "q", "url": "https://u"}}

    def test_states(self):
        ok = {"sources": {"x": {"quote": "q", "url": "https://u", "status": "verified", "verified": "2026-11-22",
                                "page_date": "2026-11-03", "checked": "2026-11-22"}}}
        self.assertEqual(S.verification(self.row, ok)[0], "ok")
        changed = {"sources": {"x": dict(ok["sources"]["x"], status="changed")}}
        self.assertEqual(S.verification(self.row, changed)[0], "review")
        other_quote = {"sources": {"x": dict(ok["sources"]["x"], quote="old")}}
        self.assertEqual(S.verification(self.row, other_quote)[0], "pending")


class Formatting(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(S.sig(0.004148), "0.0041")
        self.assertEqual(S.sig(1.607), "1.6")
        self.assertEqual(S.sig(14702.2), "14,702")
        self.assertEqual(S.fmt_big(2900000), "2.9 million")
        self.assertEqual(S.fmt_big(740000), "740,000")
        self.assertEqual(S.toll({"bound": "range", "deaths_low": 81410, "deaths_high": 137880, "deaths": 109645}),
                         "81,410–137,880")


if __name__ == "__main__":
    unittest.main()
