"""Refresh the machine-maintained data files. Safe to run at any time, any number of times.

    python3 -m board.refresh pageviews   # Wikipedia pageviews for the last 12 complete months
    python3 -m board.refresh sources     # is each quoted figure still on its source page? do links answer?
    python3 -m board.refresh record      # counts of public commitments (GitHub issues)
    python3 -m board.refresh all

Every step fails safe: when a source cannot be reached the last good value is kept and a warning is
recorded. A step exits non-zero only when it could not do its job at all, and then writes nothing.
Warnings that need a person are written to refresh-report.json (read by scripts/alerts.py).
"""
import argparse
import datetime
import json
import os
import re
import sys
import time

from . import data as D
from . import wiki
from .net import BOT_WALLS, REPO_URL, fetch
from .textutil import has_quote, page_date, page_text

REPORT = os.path.join(D.ROOT, "refresh-report.json")
MIN_SHARE_OF_PREVIOUS = 0.5   # an article whose 12-month total halves in one run has been renamed or lost
MAX_FAILED_SHARE = 0.25       # more failures than this and the run writes nothing
SOURCE_PAUSE = 2.5            # seconds between requests to the same publisher
LINK_PAUSE = 1.0


def today_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


class Report(object):
    """Collects what a run did, for the job summary and for alerts."""

    def __init__(self):
        self.lines, self.alerts, self.changed = [], [], []

    def say(self, text):
        print(text, flush=True)
        self.lines.append(text)

    def warn(self, text):
        print(("::warning::%s" % text) if os.environ.get("GITHUB_ACTIONS") else "WARNING: " + text, flush=True)
        self.lines.append("- warning: " + text)

    def alert(self, key, title, body):
        self.alerts.append({"key": key, "title": title, "body": body})
        self.warn(title)

    def save(self, steps):
        with open(REPORT, "w", encoding="utf-8") as fh:
            json.dump({"steps": steps, "alerts": self.alerts, "changed": self.changed, "lines": self.lines},
                      fh, indent=1, ensure_ascii=False)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write("## Refresh\n\n" + "\n".join(self.lines) + "\n")


# ---------------------------------------------------------------- pageviews

def refresh_pageviews(report, today=None, data_dir=D.DATA, pause=0.12):
    today = today or today_utc()
    causes = D.read_json("causes.json", data_dir=data_dir)
    previous = D.read_json("pageviews.json", {"articles": {}, "window": []}, data_dir=data_dir)
    listed = D.all_articles(causes)
    aliases = {}
    for row in D.all_rows(causes):
        for canon, names in row.get("aliases", {}).items():
            aliases.setdefault(canon, []).extend(names)

    resolved = wiki.resolve_titles(listed)
    if resolved is None:
        report.warn("Wikipedia's title API did not answer; using the titles as listed")
        resolved = {}

    end = wiki.last_complete_month(today)
    first = wiki.month_add(end, -12)          # one month of slack to tell whether `end` is published yet
    fetched, failed = {}, []
    for title in listed:
        info = resolved.get(title, {"title": title, "missing": False})
        if info["missing"]:
            report.alert("article-missing:" + title, "Wikipedia article missing: %s" % title,
                         "The article `%s` listed in data/causes.json no longer exists on English Wikipedia. "
                         "Its last good pageviews are being kept. Replace the title in data/causes.json." % title)
        names = [title]
        for extra in [info["title"]] + aliases.get(title, []):
            if extra and extra not in names:
                names.append(extra)
        months, ok = {}, True
        for name in names:
            got = wiki.monthly_views(name, first, end)
            time.sleep(pause)
            if got is None:
                ok = False
                break
            for key, views in got.items():
                months[key] = months.get(key, 0) + views
        if not ok:
            failed.append(title)
            continue
        fetched[title] = {"canonical": info["title"], "titles": names, "months": months}
        if info["title"] != title and not info["missing"]:
            report.say("- note: `%s` now redirects to `%s`; both titles are counted" % (title, info["title"]))

    if not listed or len(failed) > MAX_FAILED_SHARE * len(listed):
        report.warn("pageviews: %d of %d articles could not be fetched; nothing written" % (len(failed), len(listed)))
        return False

    # Has Wikimedia published the newest month yet? If most articles lack it, end the window a month earlier.
    have_end = sum(1 for e in fetched.values() if end in e["months"])
    if have_end < 0.8 * max(1, sum(1 for e in fetched.values() if e["months"])):
        report.say("- %s is not published for most articles yet; the window ends a month earlier" % end)
        end = wiki.month_add(end, -1)
    window = wiki.window_ending(end, 12)

    if previous.get("window") and window[-1] < previous["window"][-1]:
        report.say("- pageviews: the window on file (%s) is newer than what is available (%s); unchanged"
                   % (previous["window"][-1], window[-1]))
        return True

    articles = {}
    for title in listed:
        old = previous.get("articles", {}).get(title)
        new = fetched.get(title)
        if new is None:
            if old:
                articles[title] = dict(old, kept=True)
                report.warn("pageviews for `%s` could not be fetched; last good numbers kept" % title)
            else:
                report.warn("pageviews for `%s` could not be fetched and none are on file" % title)
                return False
            continue
        new["months"] = {m: int(new["months"].get(m, 0)) for m in window}
        new_total = sum(new["months"].values())
        old_total = sum(int(v) for v in old["months"].values()) if old else 0
        if old and old_total >= 500 and new_total < MIN_SHARE_OF_PREVIOUS * old_total:
            articles[title] = dict(old, kept=True)
            report.alert("pageviews-drop:" + title, "Pageviews for %s fell by more than half in one run" % title,
                         "The 12-month total for `%s` went from %d to %d. A 12-month total cannot halve in a "
                         "month unless the article was renamed, merged or deleted, so the last good numbers "
                         "are being kept. Check the article and update `articles` (or add the old title under "
                         "`aliases`) in data/causes.json." % (title, old_total, new_total))
            continue
        new["kept"] = False
        articles[title] = new

    out = {"project": wiki.PROJECT, "access": wiki.ACCESS, "agent": wiki.AGENT, "pulled": today,
           "window": window, "articles": articles}
    comparable = lambda pv: (pv.get("window"), {t: e.get("months") for t, e in pv.get("articles", {}).items()})  # noqa: E731
    if comparable(out) == comparable(previous):
        report.say("- pageviews: unchanged (window %s to %s)" % (window[0], window[-1]))
        return True
    problems = D.validate_pageviews(causes, out)
    if problems:
        report.warn("pageviews: refusing to write invalid data: " + "; ".join(problems[:5]))
        return False
    D.write_json("pageviews.json", out, data_dir=data_dir)
    report.changed.append("pageviews")
    report.say("- pageviews: %d articles, window %s to %s, written" % (len(articles), window[0], window[-1]))
    return True


# ---------------------------------------------------------------- sources and links

def link_urls(causes):
    urls = []
    for row in causes["causes"]:
        urls += [o["url"] for o in row["orgs"]]
        if "lever_source" in row:
            urls.append(row["lever_source"]["url"])
    urls += [link["url"] for link in causes.get("support", {}).get("links", [])]
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


DNS_FAILURE = ("name or service not known", "nodename nor servname", "no address associated", "getaddrinfo failed",
               "temporary failure in name resolution")
UNREACHABLE_ALERT_DAYS = 28   # some sites drop connections from cloud runners; only a long silence is news


def classify_link(status, error=""):
    if 200 <= status < 400:
        return "ok"
    if status in BOT_WALLS:
        return "blocked"   # the site answers but refuses scripts; a person can still open it
    if status == 0 and not any(m in (error or "").lower() for m in DNS_FAILURE):
        return "unreachable"   # timeout or reset: often a firewall in front of runners, not a dead site
    return "broken"


def refresh_sources(report, today=None, data_dir=D.DATA, pause=SOURCE_PAUSE, link_pause=LINK_PAUSE):
    today = today or today_utc()
    causes = D.read_json("causes.json", data_dir=data_dir)
    previous = D.read_json("sources.json", {"sources": {}, "links": {}}, data_dir=data_dir)
    rows = D.all_rows(causes)
    sources, reached = {}, 0
    for row in rows:
        old = previous.get("sources", {}).get(row["id"], {})
        same_claim = old.get("quote") == row["source"]["quote"] and old.get("url") == row["source"]["url"]
        entry = {"url": row["source"]["url"], "quote": row["source"]["quote"], "checked": today,
                 "verified": old.get("verified", "") if same_claim else "",
                 "page_date": old.get("page_date", "") if same_claim else ""}
        res = fetch(row["source"]["url"], accept="text/html,*/*;q=0.8")
        entry["http"] = res.status
        if res.ok:
            reached += 1
            markup = res.text()
            if has_quote(page_text(markup), row["source"]["quote"]):
                entry["status"] = "verified"
                entry["verified"] = today
                entry["page_date"] = page_date(markup) or entry["page_date"]
            else:
                entry["status"] = "changed"
                report.alert("source-changed:" + row["id"], "Source no longer shows the quoted figure: %s" % row["name"],
                             "The page %s no longer contains the phrase\n\n> %s\n\nwhich supports the board's figure "
                             "of %s deaths for **%s**. The publisher has probably revised the estimate. The board "
                             "keeps the old figure and marks it as under review until `deaths`, `period` and "
                             "`source.quote` are updated in data/causes.json."
                             % (row["source"]["url"], row["source"]["quote"], "{:,}".format(row["deaths"]), row["name"]))
        elif res.status in (404, 410):
            entry["status"] = "gone"
            report.alert("source-gone:" + row["id"], "Source page not found: %s" % row["name"],
                         "%s answered HTTP %s. Find the publisher's current page for this figure and update "
                         "`source` in data/causes.json." % (row["source"]["url"], res.status))
        else:
            entry["status"] = "unreachable"
            report.say("- note: %s did not answer the checker (%s); last verification stands"
                       % (row["source"]["url"], res.error or res.status))
        sources[row["id"]] = entry
        time.sleep(pause)
    if rows and reached == 0:
        report.warn("sources: no source page could be reached; nothing written")
        return False

    links = {}
    for url in link_urls(causes):
        old = previous.get("links", {}).get(url, {})
        res = fetch(url, tries=2, accept="text/html,*/*;q=0.8", limit=200000)
        status = classify_link(res.status, res.error)
        entry = {"http": res.status, "status": status, "checked": today}
        if status in ("broken", "unreachable"):
            entry["since"] = old.get("since") if old.get("status") in ("broken", "unreachable") and old.get("since") else today
            days = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(entry["since"])).days
            if (status == "broken" and days >= 1) or (status == "unreachable" and days >= UNREACHABLE_ALERT_DAYS):
                report.alert("link-broken:" + url, "Link not answering: %s" % url,
                             "%s has failed since %s (%s). If the organisation moved, update the URL in "
                             "data/causes.json." % (url, entry["since"], res.error or "HTTP %s" % res.status))
        links[url] = entry
        time.sleep(link_pause)

    out = {"checked": today, "sources": sources, "links": links}
    if out != previous:
        D.write_json("sources.json", out, data_dir=data_dir)
        report.changed.append("sources")
    verified = sum(1 for e in sources.values() if e["status"] == "verified")
    count = lambda st: sum(1 for e in links.values() if e["status"] == st)  # noqa: E731
    report.say("- sources: %d of %d figures found on their source pages today; links: %d ok, %d blocked to scripts, "
               "%d not answering, %d broken" % (verified, len(sources), count("ok"), count("blocked"),
                                                 count("unreachable"), count("broken")))
    return True


# ---------------------------------------------------------------- public record

DATE_FIELD = re.compile(r"###\s*Resolution date\s+(\d{4}-\d{2}-\d{2})", re.I)


def summarise_issues(issues, today):
    """Counts for the public record from GitHub issue objects labelled 'commitment'."""
    out = {"total": 0, "open": 0, "overdue": 0, "came_true": 0, "did_not": 0, "first_true": ""}
    for issue in issues:
        if "pull_request" in issue:
            continue
        labels = {label["name"].lower() for label in issue.get("labels", [])}
        if labels & {"invalid", "spam", "duplicate"}:
            continue
        out["total"] += 1
        if issue.get("state") == "open":
            m = DATE_FIELD.search(issue.get("body") or "")
            if m and m.group(1) < today:
                out["overdue"] += 1
            else:
                out["open"] += 1
        elif issue.get("state_reason") == "completed":
            out["came_true"] += 1
            closed = (issue.get("closed_at") or "")[:10]
            if closed and (not out["first_true"] or closed < out["first_true"]):
                out["first_true"] = closed
        else:
            out["did_not"] += 1
    return out


def refresh_record(report, today=None, data_dir=D.DATA):
    today = today or today_utc()
    repo = os.environ.get("GITHUB_REPOSITORY") or REPO_URL.split("github.com/")[1]
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    issues = []
    for page in range(1, 11):
        url = "https://api.github.com/repos/%s/issues?labels=commitment&state=all&per_page=100&page=%d" % (repo, page)
        import urllib.request
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "response-ability-attention-gap-board"})
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                batch = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            report.warn("public record: the GitHub API did not answer (%s); last counts kept" % exc)
            return True
        issues += batch
        if len(batch) < 100:
            break
    out = summarise_issues(issues, today)
    previous = D.read_json("record.json", {}, data_dir=data_dir)
    if {k: v for k, v in previous.items() if k != "checked"} != out:
        D.write_json("record.json", dict(out, checked=today), data_dir=data_dir)
        report.changed.append("record")
    report.say("- public record: %(total)d commitments (%(open)d open, %(overdue)d past their date, "
               "%(came_true)d reported true, %(did_not)d reported false)" % out)
    return True


# ---------------------------------------------------------------- entry point

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["pageviews", "sources", "record", "all"])
    ap.add_argument("--today", help="pretend today is this date (YYYY-MM-DD)")
    args = ap.parse_args(argv)
    report = Report()
    steps = ["pageviews", "sources", "record"] if args.step == "all" else [args.step]
    results = {}
    for step in steps:
        fn = {"pageviews": refresh_pageviews, "sources": refresh_sources, "record": refresh_record}[step]
        results[step] = bool(fn(report, today=args.today))
    report.save(results)
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
