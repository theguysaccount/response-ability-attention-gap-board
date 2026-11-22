"""Load, validate and compute the board.

Three files in data/:

  causes.json     editorial: the causes, their sourced death tolls, what each needs. Changed by people.
  pageviews.json  machine: monthly English Wikipedia pageviews per article. Rewritten by board.refresh.
  sources.json    machine: when each source was last fetched and whether the quoted figure is still on it.
  record.json     machine: counts of public commitments (GitHub issues labelled "commitment").
"""
import json
import math
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
BOUNDS = ("exact", "about", "more than", "range")
LEVELS = (0, 1, 2, 3)
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_QUOTE_WORDS = 15   # quotations stay short and attributed


def read_json(name, default=None, data_dir=DATA):
    path = os.path.join(data_dir, name)
    if not os.path.exists(path):
        if default is None:
            raise IOError("missing data file: %s" % path)
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(name, value, data_dir=DATA):
    path = os.path.join(data_dir, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(value, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def all_rows(causes):
    """Every row with a toll and articles: the causes, then the reference row."""
    return list(causes["causes"]) + [causes["reference"]]


def all_articles(causes):
    seen, out = set(), []
    for row in all_rows(causes):
        for title in row["articles"]:
            if title not in seen:
                seen.add(title)
                out.append(title)
    return out


def validate_causes(causes):
    """Problems with the editorial file; an empty list means it is safe to build from."""
    problems = []
    cap_ids = [c["id"] for c in causes.get("capabilities", [])]
    if len(cap_ids) < 3 or len(set(cap_ids)) != len(cap_ids):
        problems.append("capabilities: need at least three, with unique ids")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", causes.get("launched", "")):
        problems.append("launched: must be an ISO date")
    seen_ids, seen_articles = set(), {}
    rows = all_rows(causes)
    for row in rows:
        rid = row.get("id", "?")
        is_ref = row is causes["reference"]

        def bad(msg, rid=rid):
            problems.append("%s: %s" % (rid, msg))

        if not SLUG.match(rid):
            bad("id must be a lower-case slug")
        if rid in seen_ids:
            bad("duplicate id")
        seen_ids.add(rid)
        for key in ("name", "measure", "period"):
            if not str(row.get(key, "")).strip():
                bad("missing %s" % key)
        deaths = row.get("deaths")
        if not isinstance(deaths, int) or deaths <= 0:
            bad("deaths must be a positive whole number")
        if row.get("bound") not in BOUNDS:
            bad("bound must be one of %s" % ", ".join(BOUNDS))
        if row.get("bound") == "range":
            low, high = row.get("deaths_low"), row.get("deaths_high")
            if not (isinstance(low, int) and isinstance(high, int) and 0 < low < high):
                bad("a range needs deaths_low < deaths_high")
            elif isinstance(deaths, int) and abs(deaths - (low + high) / 2.0) > 1:
                bad("deaths must be the midpoint of the range")
        elif "deaths_low" in row or "deaths_high" in row:
            bad("deaths_low/high only belong on a range")
        src = row.get("source", {})
        for key in ("publisher", "title", "url", "quote"):
            if not str(src.get(key, "")).strip():
                bad("source.%s missing" % key)
        if not str(src.get("url", "")).startswith("https://"):
            bad("source.url must be https")
        if len(str(src.get("quote", "")).split()) > MAX_QUOTE_WORDS:
            bad("source.quote is longer than %d words" % MAX_QUOTE_WORDS)
        articles = row.get("articles", [])
        if not (1 <= len(articles) <= 4) or any(not str(a).strip() or "_" in a for a in articles):
            bad("articles: one to four titles, written with spaces")
        for title in articles:
            if title in seen_articles:
                bad("article %r is already counted for %s" % (title, seen_articles[title]))
            seen_articles[title] = rid
        for canon, names in row.get("aliases", {}).items():
            if canon not in articles or not isinstance(names, list) or not names:
                bad("aliases must map one of this row's articles to a list of earlier titles")
        if is_ref:
            continue
        need = row.get("need", {})
        if sorted(need) != sorted(cap_ids):
            bad("need must rate every capability exactly once")
        elif any(v not in LEVELS for v in need.values()) or not any(need.values()):
            bad("need values are 0-3 and at least one must be above 0")
        lever = str(row.get("lever", ""))
        if not 80 <= len(lever) <= 620:
            bad("lever must be 80-620 characters (it is %d)" % len(lever))
        if "lever_source" in row:
            ls = row["lever_source"]
            if not str(ls.get("title", "")).strip() or not str(ls.get("url", "")).startswith("https://"):
                bad("lever_source needs a title and an https url")
        orgs = row.get("orgs", [])
        if not 1 <= len(orgs) <= 2:
            bad("orgs: one or two organisations")
        for org in orgs:
            if not str(org.get("name", "")).strip() or not str(org.get("url", "")).startswith("https://"):
                bad("each organisation needs a name and an https url")
    if len(causes.get("causes", [])) < 5:
        problems.append("the board needs at least five causes")
    support = causes.get("support", {})
    if not str(support.get("text", "")).strip() or not support.get("links"):
        problems.append("support: crisis-support text and at least one link are required")
    for link in support.get("links", []):
        if not str(link.get("name", "")).strip() or not str(link.get("url", "")).startswith("https://"):
            problems.append("support: each link needs a name and an https url")
    return problems


def validate_pageviews(causes, pageviews):
    problems = []
    window = pageviews.get("window", [])
    if len(window) != 12 or sorted(window) != window or len(set(window)) != 12:
        problems.append("pageviews.window must be 12 consecutive months in order")
    else:
        from .wiki import month_add
        if any(month_add(window[i], 1) != window[i + 1] for i in range(11)):
            problems.append("pageviews.window has a gap")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", pageviews.get("pulled", "")):
        problems.append("pageviews.pulled must be an ISO date")
    arts = pageviews.get("articles", {})
    for title in all_articles(causes):
        entry = arts.get(title)
        if not entry:
            problems.append("no pageviews for article %r" % title)
            continue
        months = entry.get("months", {})
        if any(not isinstance(v, int) or v < 0 for v in months.values()):
            problems.append("pageviews for %r must be whole numbers" % title)
    return problems


def article_views(pageviews, title):
    """Views of one article over the window (months without data count as zero)."""
    months = pageviews["articles"].get(title, {}).get("months", {})
    return sum(int(months.get(m, 0)) for m in pageviews["window"])


def article_months(pageviews, title):
    months = pageviews["articles"].get(title, {}).get("months", {})
    return [int(months.get(m, 0)) for m in pageviews["window"]]


def compute(causes, pageviews):
    """The ranked board: every cause with its views, views per death and neglect index.

    views per death = pageviews in the 12-month window / deaths per year
    neglect index   = log10(deaths per view) - (the lowest such value on the board) + 1
    Causes are ranked by views per death, lowest (least watched per death) first.
    """
    rows = []
    for row in all_rows(causes):
        per_article = [(t, article_views(pageviews, t)) for t in row["articles"]]
        views = sum(v for _, v in per_article)
        monthly = [sum(vals) for vals in zip(*[article_months(pageviews, t) for t in row["articles"]])]
        out = dict(row)
        out.update({
            "views": views,
            "per_article": per_article,
            "monthly": monthly,
            "vpd": (views / float(row["deaths"])) if views else 0.0,
            "is_reference": row is causes["reference"],
        })
        rows.append(out)
    ranked = sorted((r for r in rows if not r["is_reference"]), key=lambda r: (r["vpd"], r["id"]))
    logs = [math.log10(r["deaths"] / float(max(r["views"], 1))) for r in ranked]
    floor = min(logs)
    for rank, (row, lg) in enumerate(zip(ranked, logs), 1):
        row["rank"] = rank
        row["neglect"] = lg - floor + 1.0
    reference = [r for r in rows if r["is_reference"]][0]
    reference["rank"] = None
    reference["neglect"] = None
    return {"causes": ranked, "reference": reference, "window": list(pageviews["window"]),
            "pulled": pageviews["pulled"]}


def load_all(data_dir=DATA):
    causes = read_json("causes.json", data_dir=data_dir)
    pageviews = read_json("pageviews.json", data_dir=data_dir)
    sources = read_json("sources.json", {"checked": "", "sources": {}, "links": {}}, data_dir=data_dir)
    record = read_json("record.json", {"checked": "", "total": 0, "open": 0, "came_true": 0, "did_not": 0,
                                       "overdue": 0, "first_true": ""}, data_dir=data_dir)
    return causes, pageviews, sources, record


# ---------------------------------------------------------------- the assignment (mirrors site/assets/core.js)

RARITY = [("thousands", 1), ("hundreds", 2), ("dozens", 4), ("a handful", 8)]
SCALE = [("myself", 1), ("a team", 2), ("a company", 4), ("capital", 6), ("an institution", 8)]


def score(cause, caps, declared, rarity, scale):
    """One cause's score for a declaration: neglect x cosine(fit)^2 x rarity x scale."""
    dot = un = gn = 0.0
    for cap in caps:
        u, n = float(declared.get(cap, 0)), float(cause["need"].get(cap, 0))
        dot += u * n
        un += u * u
        gn += n * n
    cos = dot / (math.sqrt(un) * math.sqrt(gn)) if un and gn else 0.0
    fit = cos * cos
    return {"id": cause["id"], "cos": cos, "fit": fit, "neglect": cause["neglect"],
            "total": cause["neglect"] * fit * rarity * scale}


def assign(board, caps, declared, rarity, scale):
    """Every cause scored and sorted, best first. Ties go to the more neglected cause (lower rank)."""
    ranked = [score(c, caps, declared, rarity, scale) for c in board["causes"]]
    rank = {c["id"]: c["rank"] for c in board["causes"]}
    ranked.sort(key=lambda s: (-round(s["total"], 12), rank[s["id"]]))
    return ranked
