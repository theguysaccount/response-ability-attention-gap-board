"""The refresh jobs against a fake network: they must keep last good data and raise alerts instead of guessing."""
import json
import os
import shutil
import tempfile
import unittest
import urllib.parse
from unittest import mock

from board import data as D
from board import refresh as R
from board import wiki
from board.net import Fetch

CAPS = ["CAPITAL", "BUILD", "MANUFACTURE", "POLICY", "DISTRIBUTE", "CLINICAL", "FIELD", "SCIENCE", "CONVENE"]


def cause(i, article):
    return {"id": "cause-%d" % i, "name": "Cause %d" % i, "measure": "deaths from cause %d" % i,
            "deaths": 1000 * (i + 1), "bound": "about", "period": "2024",
            "source": {"publisher": "Pub", "title": "Sheet %d" % i, "url": "https://src.example/%d" % i,
                       "quote": "about %d deaths in 2024" % (1000 * (i + 1))},
            "articles": [article], "need": {c: (1 if c == CAPS[i % 9] else 0) for c in CAPS},
            "lever": "x" * 100, "orgs": [{"name": "Org %d" % i, "url": "https://org.example/%d" % i}]}


def synthetic():
    return {"schema": 1, "launched": "2026-01-01",
            "support": {"text": "Help is available.", "links": [{"name": "Helpline", "url": "https://help.example/"}]},
            "capabilities": [{"id": c, "label": c.title(), "desc": c} for c in CAPS],
            "reference": {"id": "ref", "name": "Reference", "measure": "deaths", "deaths": 10, "bound": "exact",
                          "period": "2025", "articles": ["Ref article"],
                          "source": {"publisher": "Pub", "title": "Ref", "url": "https://src.example/ref",
                                     "quote": "10 confirmed deaths"}},
            "causes": [cause(i, "Article %d" % i) for i in range(6)]}


class FakeNet(object):
    def __init__(self, months):
        self.views = {}          # article -> {YYYY-MM: views}
        self.months = months
        self.failing = set()     # articles whose pageview request fails
        self.pages = {}          # url -> (status, body)

    def __call__(self, url, **kw):
        if url.startswith(wiki.MEDIAWIKI):
            titles = urllib.parse.unquote(url.split("titles=", 1)[1]).split("|")
            pages = {str(-i - 1): {"title": t} for i, t in enumerate(titles)}
            return Fetch(200, json.dumps({"query": {"pages": pages}}).encode(), url)
        if url.startswith(wiki.PAGEVIEWS):
            parts = url.split("/")
            article = urllib.parse.unquote(parts[-4]).replace("_", " ")
            if article in self.failing:
                return Fetch(0, url=url, error="timeout")
            series = self.views.get(article)
            if series is None:
                return Fetch(404, url=url)
            first, end = parts[-2][:6], parts[-1][:6]
            items = [{"timestamp": m.replace("-", "") + "0100", "views": v} for m, v in sorted(series.items())
                     if first <= m.replace("-", "") < end]
            return Fetch(200, json.dumps({"items": items}).encode(), url)
        status, body = self.pages.get(url, (0, ""))
        return Fetch(status, body.encode(), url, error="" if status else "unreachable")


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.causes = synthetic()
        D.write_json("causes.json", self.causes, data_dir=self.dir)
        months = [wiki.month_add("2025-10", i) for i in range(13)]   # 2025-10 .. 2026-10
        self.net = FakeNet(months)
        for row in D.all_rows(self.causes):
            for a in row["articles"]:
                self.net.views[a] = {m: 100 for m in months}
        patches = [mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "", "GITHUB_STEP_SUMMARY": ""}),
                   mock.patch.object(wiki, "fetch", self.net), mock.patch.object(R, "fetch", self.net),
                   mock.patch.object(wiki.time, "sleep", lambda s: None), mock.patch.object(R.time, "sleep", lambda s: None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.report = R.Report()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def pv(self):
        return D.read_json("pageviews.json", data_dir=self.dir)


class Pageviews(Base):
    def test_last_twelve_complete_months(self):
        self.assertTrue(R.refresh_pageviews(self.report, today="2026-11-22", data_dir=self.dir, pause=0))
        pv = self.pv()
        self.assertEqual(pv["window"][0], "2025-11")
        self.assertEqual(pv["window"][-1], "2026-10")
        self.assertEqual(D.validate_pageviews(self.causes, pv), [])

    def test_unpublished_month_shifts_the_window(self):
        for a in self.net.views:
            self.net.views[a].pop("2026-10")
        self.assertTrue(R.refresh_pageviews(self.report, today="2026-11-02", data_dir=self.dir, pause=0))
        self.assertEqual(self.pv()["window"][-1], "2026-09")

    def test_a_collapse_keeps_last_good_numbers_and_alerts(self):
        R.refresh_pageviews(self.report, today="2026-11-22", data_dir=self.dir, pause=0)
        for m in self.net.views["Article 2"]:
            self.net.views["Article 2"][m] = 1
        self.net.views["Article 2"]["2026-11"] = 1
        for a in self.net.views:
            self.net.views[a].setdefault("2026-11", 100)
        report = R.Report()
        self.assertTrue(R.refresh_pageviews(report, today="2026-12-20", data_dir=self.dir, pause=0))
        entry = self.pv()["articles"]["Article 2"]
        self.assertTrue(entry["kept"])
        self.assertEqual(sum(entry["months"].values()), 1200)
        self.assertIn("pageviews-drop:Article 2", [a["key"] for a in report.alerts])

    def test_too_many_failures_write_nothing(self):
        R.refresh_pageviews(self.report, today="2026-11-22", data_dir=self.dir, pause=0)
        before = self.pv()
        self.net.failing = {"Article 0", "Article 1", "Article 2"}
        self.assertFalse(R.refresh_pageviews(R.Report(), today="2026-12-22", data_dir=self.dir, pause=0))
        self.assertEqual(self.pv(), before)

    def test_rerun_is_a_no_op(self):
        R.refresh_pageviews(self.report, today="2026-11-22", data_dir=self.dir, pause=0)
        report = R.Report()
        self.assertTrue(R.refresh_pageviews(report, today="2026-11-23", data_dir=self.dir, pause=0))
        self.assertNotIn("pageviews", report.changed)


class Sources(Base):
    def page(self, row, text):
        self.net.pages[row["source"]["url"]] = (200, "<h1>x</h1><p>3 March 2026</p><h2>Key facts</h2><p>%s</p>" % text)

    def setUp(self):
        super().setUp()
        for row in D.all_rows(self.causes):
            self.page(row, row["source"]["quote"] + ".")
        for row in self.causes["causes"]:
            for o in row["orgs"]:
                self.net.pages[o["url"]] = (200, "ok")
        self.net.pages["https://help.example/"] = (200, "ok")

    def run_sources(self, today, report=None):
        return R.refresh_sources(report or self.report, today=today, data_dir=self.dir, pause=0, link_pause=0)

    def test_verified_with_page_date(self):
        self.assertTrue(self.run_sources("2026-11-22"))
        s = D.read_json("sources.json", data_dir=self.dir)["sources"]["cause-0"]
        self.assertEqual((s["status"], s["verified"], s["page_date"]), ("verified", "2026-11-22", "2026-03-03"))

    def test_revised_figure_is_flagged_not_trusted(self):
        self.page(self.causes["causes"][1], "about 9999 deaths in 2025")
        self.assertTrue(self.run_sources("2026-11-22"))
        s = D.read_json("sources.json", data_dir=self.dir)["sources"]["cause-1"]
        self.assertEqual(s["status"], "changed")
        self.assertIn("source-changed:cause-1", [a["key"] for a in self.report.alerts])

    def test_unreachable_keeps_the_last_verification(self):
        self.run_sources("2026-11-01")
        self.net.pages[self.causes["causes"][2]["source"]["url"]] = (0, "")
        self.run_sources("2026-11-08", R.Report())
        s = D.read_json("sources.json", data_dir=self.dir)["sources"]["cause-2"]
        self.assertEqual((s["status"], s["verified"]), ("unreachable", "2026-11-01"))

    def test_gone_page_alerts(self):
        self.net.pages[self.causes["causes"][3]["source"]["url"]] = (404, "")
        self.run_sources("2026-11-22")
        self.assertIn("source-gone:cause-3", [a["key"] for a in self.report.alerts])

    def test_nothing_reachable_writes_nothing(self):
        for url in list(self.net.pages):
            self.net.pages[url] = (0, "")
        self.assertFalse(self.run_sources("2026-11-22"))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "sources.json")))

    def test_broken_link_alerts_only_on_a_second_day(self):
        url = self.causes["causes"][0]["orgs"][0]["url"]
        self.net.pages[url] = (500, "")
        first = R.Report()
        self.run_sources("2026-11-21", first)
        self.assertNotIn("link-broken:" + url, [a["key"] for a in first.alerts])
        second = R.Report()
        self.run_sources("2026-11-28", second)
        self.assertIn("link-broken:" + url, [a["key"] for a in second.alerts])

    def test_a_dropped_connection_alerts_only_after_four_weeks(self):
        url = self.causes["causes"][0]["orgs"][0]["url"]
        self.net.pages[url] = (0, "")      # FakeNet reports error "unreachable": not a DNS failure
        self.run_sources("2026-11-01")
        week = R.Report()
        self.run_sources("2026-11-08", week)
        self.assertNotIn("link-broken:" + url, [a["key"] for a in week.alerts])
        month = R.Report()
        self.run_sources("2026-11-29", month)
        self.assertIn("link-broken:" + url, [a["key"] for a in month.alerts])

    def test_bot_walls_are_not_broken(self):
        url = self.causes["causes"][0]["orgs"][0]["url"]
        self.net.pages[url] = (403, "")
        self.run_sources("2026-11-21")
        self.assertEqual(D.read_json("sources.json", data_dir=self.dir)["links"][url]["status"], "blocked")


class Record(unittest.TestCase):
    def issue(self, state, reason=None, date="2027-01-01", closed=None, labels=("commitment",)):
        return {"state": state, "state_reason": reason, "closed_at": closed,
                "labels": [{"name": n} for n in labels], "body": "### Resolution date\n\n%s\n" % date}

    def test_counts(self):
        issues = [self.issue("open"), self.issue("open", date="2026-01-01"),
                  self.issue("closed", "completed", closed="2026-12-03T10:00:00Z"),
                  self.issue("closed", "completed", closed="2026-12-01T10:00:00Z"),
                  self.issue("closed", "not_planned", closed="2026-12-05T10:00:00Z"),
                  self.issue("open", labels=("commitment", "spam")), dict(self.issue("open"), pull_request={})]
        out = R.summarise_issues(issues, "2026-12-10")
        self.assertEqual((out["total"], out["open"], out["overdue"], out["came_true"], out["did_not"]), (5, 1, 1, 2, 1))
        self.assertEqual(out["first_true"], "2026-12-01")


if __name__ == "__main__":
    unittest.main()
