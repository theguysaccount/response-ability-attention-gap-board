"""English Wikipedia pageviews (Wikimedia REST API) and title resolution (MediaWiki API)."""
import time
import urllib.parse

from .net import fetch

PROJECT = "en.wikipedia"
AGENT = "user"          # human readers only: identified bots and spiders are not attention
ACCESS = "all-access"
PAGEVIEWS = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
MEDIAWIKI = "https://en.wikipedia.org/w/api.php"


def month_add(ym, n):
    """'2026-10' plus n months."""
    y, m = int(ym[:4]), int(ym[5:7])
    idx = y * 12 + (m - 1) + n
    return "%04d-%02d" % (idx // 12, idx % 12 + 1)


def window_ending(end, months=12):
    """The list of month keys in a window that ends with (and includes) `end`."""
    return [month_add(end, -i) for i in range(months - 1, -1, -1)]


def last_complete_month(today):
    """The month before the one `today` (YYYY-MM-DD) falls in."""
    return month_add(today[:7], -1)


def article_url(title):
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="()/:,'")


def resolve_titles(titles, pause=0.5):
    """Map each title to {'title': canonical title, 'missing': bool} following redirects.

    Returns None when the API cannot be reached, so the caller can keep what it had.
    """
    out = {}
    titles = list(titles)
    for i in range(0, len(titles), 40):
        chunk = titles[i:i + 40]
        res = fetch(MEDIAWIKI + "?action=query&format=json&redirects=1&titles="
                    + urllib.parse.quote("|".join(chunk)), accept="application/json")
        if not res.ok:
            return None
        try:
            query = res.json()["query"]
        except (ValueError, KeyError):
            return None
        norm = {n["from"]: n["to"] for n in query.get("normalized", [])}
        redirect = {r["from"]: r["to"] for r in query.get("redirects", [])}
        pages = {p["title"]: p for p in query.get("pages", {}).values()}
        for t in chunk:
            canon = norm.get(t, t)
            canon = redirect.get(canon, canon)
            out[t] = {"title": canon, "missing": "missing" in pages.get(canon, {"missing": ""})}
        time.sleep(pause)
    return out


def monthly_views(title, first, last):
    """{'YYYY-MM': views} for one exact title between two month keys (inclusive).

    Returns None when the API gives no usable answer. A 404 means the title has no recorded
    views in the range and yields {}.
    """
    end = month_add(last, 1)
    url = "%s/%s/%s/%s/%s/monthly/%s0100/%s0100" % (
        PAGEVIEWS, PROJECT, ACCESS, AGENT, urllib.parse.quote(title.replace(" ", "_"), safe=""),
        first.replace("-", ""), end.replace("-", ""))
    res = fetch(url, accept="application/json")
    if res.status == 404:
        return {}
    if not res.ok:
        return None
    try:
        items = res.json()["items"]
    except (ValueError, KeyError):
        return None
    out = {}
    for item in items:
        ts = item["timestamp"]
        key = "%s-%s" % (ts[:4], ts[4:6])
        if first <= key <= last:
            out[key] = int(item["views"])
    return out
