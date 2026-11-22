"""Weekly self-test of the live site: pages answer, the data is fresh, and indexing matches the configuration.

    python3 scripts/health.py [base_url]

Writes a report to $GITHUB_STEP_SUMMARY. Exits 1 when a page fails, when the configuration and the live site
disagree about indexing, or when the data is badly stale. When the data is only a little stale it dispatches
the refresh workflow (if GH_TOKEN is set) and passes with a warning, so a skipped schedule heals itself.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from board.wiki import month_add  # noqa: E402

DEFAULT_BASE = "https://theguysaccount.github.io/response-ability-attention-gap-board"
UA = "response-ability-attention-gap-board-selftest/1.0 (+https://github.com/theguysaccount/response-ability-attention-gap-board)"


def get(url, tries=3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            last = (exc.code, "")
        except Exception as exc:
            last = (0, str(exc))
        time.sleep(3 * (attempt + 1))
    return last


def dispatch_refresh(lines):
    if not os.environ.get("GH_TOKEN"):
        lines.append("- (no GH_TOKEN: refresh not dispatched)")
        return
    repo = os.environ.get("GITHUB_REPOSITORY", "theguysaccount/response-ability-attention-gap-board")
    res = subprocess.run(["gh", "workflow", "run", "refresh.yml", "-R", repo, "--ref", "main"], capture_output=True, text=True)
    lines.append("- dispatched refresh.yml: %s" % ("ok" if res.returncode == 0 else res.stderr.strip()[:200]))


def main(base, today=None):
    base = base.rstrip("/")
    today = today or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    indexable = (os.environ.get("SITE_INDEXABLE") or "true").strip().lower() not in ("false", "0", "no")
    lines, failed, stale = ["## Live site", ""], False, False
    bust = "?selftest-cache=%d" % int(time.time())

    status, raw = get(base + "/data/board.json" + bust)
    try:
        board = json.loads(raw)
        n = len(board["causes"])
        ok = status == 200 and n >= 5
    except Exception as exc:
        board, n, ok = None, 0, False
        lines.append("- FAIL data/board.json: %s" % exc)
    failed |= not ok
    lines.append("- %s data/board.json: %d causes" % ("ok  " if ok else "FAIL", n))

    pages = ["/", "/method/", "/record/", "/data/", "/about/", "/embed/", "/robots.txt", "/data/board.csv",
             "/og/default.png", "/assets/app.js", "/assets/core.js", "/assets/style.css"]
    if board:
        pages += ["/" + board["causes"][0]["url"], "/" + board["causes"][-1]["url"]]
    if indexable:
        pages.append("/sitemap.xml")
    bodies = {}
    for p in pages:
        st, body = get(base + p + bust)
        ok = st == 200 and len(body) > 50
        bodies[p] = body if ok else ""
        failed |= not ok
        lines.append("- %s %s (%s)" % ("ok  " if ok else "FAIL", p, st))

    # Indexing must match the configuration in both directions.
    robots = bodies.get("/robots.txt", "")
    home = bodies.get("/", "")
    blocks = bool(re.search(r"^Disallow:\s*/\s*$", robots, re.M))
    noindex = 'name="robots" content="noindex"' in home
    if indexable and (blocks or noindex):
        failed = True
        lines.append("- FAIL configured indexable, but the live site blocks crawlers")
    elif not indexable and not (blocks and noindex):
        failed = True
        lines.append("- FAIL configured noindex, but the live site is crawlable")
    else:
        lines.append("- ok   indexing matches the configuration (%s)" % ("indexable" if indexable else "noindex"))
    if indexable and board and "/sitemap.xml" in bodies:
        missing = [c["url"] for c in board["causes"] if (base + "/" + c["url"]) not in bodies["/sitemap.xml"]]
        failed |= bool(missing)
        lines.append("- %s sitemap lists every cause page%s" % ("ok  " if not missing else "FAIL",
                                                                 "" if not missing else " (missing %d)" % len(missing)))

    # Freshness: the pageview window should end within two months of today; sources are checked weekly.
    if board:
        current = today[:7]
        end = board["window"][-1]
        if end < month_add(current, -3):
            failed = stale = True
            lines.append("- FAIL pageviews end %s: more than two months behind" % end)
        elif end < month_add(current, -2):
            stale = True
            lines.append("- warn pageviews end %s: a month behind" % end)
        else:
            lines.append("- ok   pageviews window ends %s" % end)
    st, raw = get(base + "/data/sources.json" + bust)
    try:
        checked = json.loads(raw).get("checked", "")
        age = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(checked)).days
        if age > 30:
            failed = stale = True
            lines.append("- FAIL sources last checked %s (%d days ago)" % (checked, age))
        elif age > 15:
            stale = True
            lines.append("- warn sources last checked %s (%d days ago)" % (checked, age))
        else:
            lines.append("- ok   sources checked %s" % checked)
    except Exception as exc:
        failed = True
        lines.append("- FAIL sources.json: %s" % exc)
    if stale:
        dispatch_refresh(lines)

    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(text + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SITE_URL") or DEFAULT_BASE))
