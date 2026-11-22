"""Build the static site into dist/.

    python3 -m board.site [--out dist]

Settings come from the environment, so the same build serves GitHub Pages or a custom domain:

  SITE_URL         public base URL, no trailing slash (default: the GitHub Pages URL)
  SITE_REPO        owner/name of the GitHub repo (default: theguysaccount/response-ability-attention-gap-board)
  SITE_INDEXABLE   "false" adds noindex to every page, disallows crawling and drops the sitemap (default: true)
  GOATCOUNTER_URL  optional cookieless analytics endpoint, e.g. https://<code>.goatcounter.com/count
  SUPPORT_URL      optional support link shown in the footer (the money slot); SUPPORT_LABEL names it
  BUILD_DATE       optional YYYY-MM-DD used for "built on" (default: today, UTC)

The build refuses to run on invalid data (see board.data.validate_*), so a bad edit never reaches the site.
"""
import argparse
import csv
import datetime
import html
import io
import json
import math
import os
import shutil
import sys

from . import data as D
from .wiki import article_url

ROOT = D.ROOT
SITE = os.path.join(ROOT, "site")
DEFAULT_REPO = "theguysaccount/response-ability-attention-gap-board"
DEFAULT_URL = "https://theguysaccount.github.io/response-ability-attention-gap-board"
NAME = "The Attention Gap Board"
SHORT = "RESPONSE·ABILITY"
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def e(value):
    return html.escape(str(value), quote=True)


# ---------------------------------------------------------------- formatting

def fmt_int(n):
    return "{:,}".format(int(round(n)))


def fmt_big(n):
    """2,900,000 -> '2.9 million'; 740,000 -> '740,000'."""
    if n >= 1000000:
        v = n / 1000000.0
        s = ("%.2f" % v).rstrip("0").rstrip(".") if v < 10 else ("%.1f" % v).rstrip("0").rstrip(".")
        return s + " million"
    return fmt_int(n)


def fmt_ratio(x):
    """A ratio for prose: 3,544,000 -> '3.5 million', 242 -> '242'."""
    if x >= 1000000:
        return fmt_big(x)
    return fmt_int(x)


def sig(x):
    """Views per death, shown to two significant figures below 100 and as a whole number above."""
    if x <= 0:
        return "0"
    if x >= 100:
        return fmt_int(x)
    digits = max(0, 1 - int(math.floor(math.log10(x))))
    return ("%." + str(digits) + "f") % x


def toll(row, short=False):
    """The death toll as the source states it."""
    if row["bound"] == "range":
        return "%s–%s" % (fmt_int(row["deaths_low"]), fmt_int(row["deaths_high"]))
    prefix = {"exact": "", "about": "about " if not short else "", "more than": "more than "}[row["bound"]]
    return prefix + fmt_big(row["deaths"])


def period_note(row, fmt=" ({})"):
    """' (2021)' for a dated estimate; '' when the source only says 'each year'."""
    return "" if row["period"] == "annual" else fmt.format(row["period"])


def month_name(ym, short=False):
    y, m = ym.split("-")
    name = MONTHS[int(m) - 1]
    return "%s %s" % (name[:3] if short else name, y)


def long_date(iso):
    if not iso:
        return ""
    y, m, d = iso.split("-")
    return "%d %s %s" % (int(d), MONTHS[int(m) - 1], y)


def add_days(iso, days):
    d = datetime.date(*map(int, iso.split("-"))) + datetime.timedelta(days=days)
    return d.isoformat()


# ---------------------------------------------------------------- page shell

class Site(object):
    def __init__(self, out, env=None):
        env = os.environ if env is None else env
        self.out = out
        self.url = (env.get("SITE_URL") or DEFAULT_URL).rstrip("/")
        self.repo = env.get("SITE_REPO") or DEFAULT_REPO
        self.repo_url = "https://github.com/" + self.repo
        self.indexable = (env.get("SITE_INDEXABLE") or "true").strip().lower() not in ("false", "0", "no")
        self.goatcounter = (env.get("GOATCOUNTER_URL") or "").strip()
        self.support_url = (env.get("SUPPORT_URL") or "").strip()
        self.support_label = (env.get("SUPPORT_LABEL") or "Support this board").strip()
        self.built = env.get("BUILD_DATE") or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        self.pages = []   # (path, lastmod, indexable)

    def abs(self, path):
        return self.url + "/" + path.lstrip("/")

    def write(self, path, text):
        full = os.path.join(self.out, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)

    def page(self, path, title, description, body, lastmod, depth, og="default", ld=None, index=True,
             extra_head="", scripts=(), active=""):
        root = "../" * depth
        canonical = self.abs(path)
        robots = "" if (index and self.indexable) else '<meta name="robots" content="noindex">\n'
        ld_html = "".join('<script type="application/ld+json">%s</script>\n'
                          % json.dumps(item, ensure_ascii=False).replace("</", "<\\/") for item in (ld or []))
        gc = ('<script data-goatcounter="%s" async src="https://gc.zgo.at/count.js"></script>\n' % e(self.goatcounter)
              if self.goatcounter else "")
        nav = "".join('<a href="%s%s"%s>%s</a>' % (root, href, ' aria-current="page"' if key == active else "", label)
                      for key, href, label in (("board", "", "Board"), ("method", "method/", "Method"),
                                               ("record", "record/", "Public record"), ("data", "data/", "Data"),
                                               ("about", "about/", "About")))
        support = ('<p class="support-slot"><a href="%s" rel="noopener">%s</a></p>' % (e(self.support_url), e(self.support_label))
                   if self.support_url else "")
        script_tags = "".join('<script type="module" src="%sassets/%s"></script>\n' % (root, s) for s in scripts)
        doc = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
{robots}<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{name}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_url}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#141416">
<link rel="icon" href="{root}assets/icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{root}assets/style.css">
{ld}{extra}{gc}</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<div class="wrap">
<header class="top">
  <a class="brand" href="{root}"><span class="kicker">the war room</span><span class="mark">RESPONSE<span>·</span>ABILITY</span></a>
  <nav aria-label="Site">{nav}</nav>
</header>
<main id="main">
{body}
</main>
<footer>
  <p><b>Method</b>: views per death = English Wikipedia pageviews by human readers over the last 12 complete months
  &divide; annual deaths from the cited source. Every number links to its source and date. <a href="{root}method/">Full method</a>.</p>
  <p><b>Honest limit</b>: English Wikipedia pageviews measure anglophone attention, not world attention. The ranking is directional.</p>
  <p><b>Not medical advice.</b> The organisations named on this site are listed for reference; none of them runs, endorses or is affiliated with it.</p>
  <p>Open source: <a href="{repo_url}">code and data on GitHub</a> &middot; <a href="{repo_url}/issues/new?template=correction.yml">report an error</a> &middot; built {built}</p>
  {support}
</footer>
</div>
{scripts}</body>
</html>
""".format(title=e(title), desc=e(description), robots=robots, canonical=e(canonical), name=e(NAME),
           og_url=e(self.abs("og/%s.png" % og)), root=root, ld=ld_html, extra=extra_head, gc=gc, nav=nav,
           body=body, repo_url=e(self.repo_url), built=e(long_date(self.built)), support=support,
           scripts=script_tags)
        self.write(os.path.join(path, "index.html") if not path.endswith(".html") else path, doc)
        self.pages.append((path, lastmod, index))


# ---------------------------------------------------------------- shared fragments

def cause_path(row):
    return "cause/%s/" % row["id"]


def support_box(causes, root):
    s = causes["support"]
    links = " ".join('<a href="%s" rel="noopener">%s</a>' % (e(l["url"]), e(l["name"])) for l in s["links"])
    return '<aside class="support" role="note"><p><strong>%s</strong></p><p>%s</p></aside>' % (e(s["text"]), links)


def verification(row, sources):
    """'Checked on the source page on 22 November 2026 (page dated 3 November 2026)' or an under-review note."""
    entry = sources.get("sources", {}).get(row["id"], {})
    same = entry.get("quote") == row["source"]["quote"] and entry.get("url") == row["source"]["url"]
    if not same:
        return "pending", "Not yet checked by the weekly source check."
    status = entry.get("status")
    page_date = (" The page is dated %s." % long_date(entry["page_date"])) if entry.get("page_date") else ""
    if status == "changed":
        return "review", ("Under review: on %s the source page no longer showed this figure, so the publisher may have "
                          "revised it.%s" % (long_date(entry.get("checked", "")), page_date))
    if status == "gone":
        return "review", "Under review: the source page could not be found on %s." % long_date(entry.get("checked", ""))
    if entry.get("verified"):
        return "ok", "Figure found on the source page on %s.%s" % (long_date(entry["verified"]), page_date)
    return "pending", "Not yet confirmed by the weekly source check."


def sparkline(values, window, label):
    """A small inline SVG bar chart of monthly views."""
    w, h, gap = 240, 48, 2
    n = max(1, len(values))
    bw = (w - gap * (n - 1)) / float(n)
    top = max(values) if values and max(values) > 0 else 1
    bars = []
    for i, v in enumerate(values):
        bh = max(1.0, (v / float(top)) * (h - 2))
        bars.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f"><title>%s: %s views</title></rect>'
                    % (i * (bw + gap), h - bh, bw, bh, e(month_name(window[i])), fmt_int(v)))
    return ('<svg class="spark" viewBox="0 0 %d %d" role="img" aria-label="%s" preserveAspectRatio="none">%s</svg>'
            % (w, h, e(label), "".join(bars)))


def bar_width(row, lo, hi):
    if row["vpd"] <= 0 or hi <= lo:
        return 1.5
    return max(1.5, (math.log10(row["vpd"]) - lo) / (hi - lo) * 100)


# ---------------------------------------------------------------- the board (home)

def board_json(board, causes, sources, record, site):
    """What the browser needs: the ranked causes with need vectors, the reference row and the settings."""
    def row_out(r):
        out = {k: r[k] for k in ("id", "name", "measure", "deaths", "bound", "period", "views", "vpd", "rank",
                                 "neglect") if k in r}
        out["toll"] = toll(r)
        out["vpd_text"] = sig(r["vpd"])
        out["url"] = cause_path(r)
        out["source"] = {"publisher": r["source"]["publisher"], "url": r["source"]["url"]}
        if not r.get("is_reference"):
            out["need"] = r["need"]
            out["lever"] = r["lever"]
            out["orgs"] = r["orgs"]
            out["support_note"] = bool(r.get("support_note"))
        if r["bound"] == "range":
            out["deaths_low"], out["deaths_high"] = r["deaths_low"], r["deaths_high"]
        return out

    return {
        "capabilities": causes["capabilities"],
        "rarity": [list(x) for x in D.RARITY],
        "scale": [list(x) for x in D.SCALE],
        "causes": [row_out(r) for r in board["causes"]],
        "reference": row_out(board["reference"]),
        "window": board["window"],
        "pulled": board["pulled"],
        "support": causes["support"],
        "site": {"url": site.url, "repo": site.repo},
    }


def build_home(site, causes, board, sources, record, depth=0):
    root = ""
    ranked, ref = board["causes"], board["reference"]
    lowest = ranked[0]
    ratio = ref["vpd"] / lowest["vpd"]
    deaths_ratio = lowest["deaths"] / float(ref["deaths"])
    w0, w1 = board["window"][0], board["window"][-1]
    logs = [math.log10(r["vpd"]) for r in ranked + [ref] if r["vpd"] > 0]
    lo, hi = min(logs), max(logs)

    rows = []
    for r in ranked + [ref]:
        is_ref = r.get("is_reference")
        name = ('<a href="%s">%s</a>' % (cause_path(r), e(r["name"]))) if not is_ref else e(r["name"])
        tag = '<span class="reftag">reference</span>' if is_ref else ""
        status, _ = verification(r, sources)
        flag = ' <span class="flag" title="Figure under review">under review</span>' if status == "review" else ""
        rows.append(
            '<tr%s><td class="rk">%s</td><td class="l"><div class="gname">%s%s%s</div>'
            '<div class="gsrc"><a href="%s" rel="noopener">%s</a>%s</div><div class="gmob">%s deaths a year</div></td>'
            '<td class="num hidesm">%s</td><td class="num hidesm">%s</td><td class="num vpd">%s</td>'
            '<td class="hidesm barwrap"><div class="bar"><i style="width:%.1f%%"></i></div></td></tr>'
            % (' class="ref"' if is_ref else "", "" if is_ref else r["rank"], name, tag, flag,
               e(r["source"]["url"]), e(r["source"]["publisher"]), e(period_note(r, ", {}")),
               e(toll(r, short=True)), e(toll(r, short=True)), fmt_int(r["views"]), sig(r["vpd"]), bar_width(r, lo, hi)))

    data = json.dumps(board_json(board, causes, sources, record, site), ensure_ascii=False, separators=(",", ":"))
    body = """
<section class="intro">
  <h1>Which preventable deaths does the world look away from?</h1>
  <p class="flip">Responsibility is not a burden you are assigned. It is a measurement: <b>your responsibility is what
  you have the greatest ability to respond to.</b> This board ranks {n} preventable causes of death by how little attention
  each death gets, then gives you one assignment matched to what you can actually do.</p>
</section>

<section aria-labelledby="why">
  <h2 id="why">I. The gap</h2>
  <div class="hero">
    <div class="a"><div class="hlab">Most-watched death on the board</div><div class="hnum">{ref_vpd}</div>
      <div class="hsub">Wikipedia views per death: {ref_name} (reference)</div></div>
    <div class="mid">VS</div>
    <div class="b"><div class="hlab">Least-watched death on the board</div><div class="hnum">{low_vpd}</div>
      <div class="hsub">Wikipedia views per death: <a href="{low_url}">{low_name}</a></div></div>
  </div>
  <p class="ratio">A death from <strong>{low_name_lc}</strong> draws <b>{ratio}&times;</b> less attention than a death
  from a shark attack, and there are <b>{dratio}&times;</b> more of them every year.</p>
  <p class="note">Two public, checkable quantities: deaths a year from the cited source, and English Wikipedia pageviews by
  human readers from {w0} to {w1}. Dividing one by the other shows how much attention a death draws, by cause. The point is
  not that any death gets too much attention. It is that attention is not allocated by toll, and everything on the board is
  something we already know how to prevent.</p>
</section>

<section aria-labelledby="board">
  <h2 id="board">II. The board: ranked by how little the world is looking</h2>
  <div class="tablewrap"><table>
    <caption class="sr">Preventable causes of death ranked by Wikipedia views per death, lowest first</caption>
    <thead><tr><th class="rk">#</th><th class="l">Cause</th><th class="hidesm">Deaths / year</th><th class="hidesm">Views, 12 months</th>
      <th>Views per death</th><th class="hidesm"><span class="sr">Log scale bar</span></th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <p class="axisnote">Bars are log&#8321;&#8320; of views per death: the range spans {orders} orders of magnitude.
  Pageviews: Wikimedia REST API, en.wikipedia, all access, human readers only, {w0} to {w1}, pulled {pulled}, summed
  over the articles listed on each cause's page. Ranges use their midpoint. Rows overlap and are never added up.
  <a href="method/">Method</a> &middot; <a href="data/">Download the data</a></p>
</section>

<section aria-labelledby="declare" id="declare-section">
  <h2 id="declare">III. Declare what you can actually do</h2>
  <p>Not what you care about. Rate what you could put into the world in the next ninety days without asking anyone's
  permission. <strong>Nothing you enter leaves your browser</strong> unless you choose to post it.</p>
  <form id="declare-form" class="declare" novalidate>
    <div class="grid" id="caps">{cap_html}</div>
    <div class="modrow">
      <fieldset class="cap"><legend class="cn">Rarity</legend>
        <p class="cd">Of everyone you know, how many could do what you just described?</p>
        <div class="seg" data-group="rarity">{rarity_html}</div></fieldset>
      <fieldset class="cap"><legend class="cn">Scale</legend>
        <p class="cd">What do you control, and can commit without a vote?</p>
        <div class="seg" data-group="scale">{scale_html}</div></fieldset>
    </div>
    <div class="go">
      <button type="submit" id="run">Compute my assignment</button>
      <span class="hint" id="hint" aria-live="polite">Set at least one capability above none, then rarity and scale.</span>
    </div>
  </form>
  <div id="out" aria-live="polite"></div>
  <noscript><p class="note">The assignment needs JavaScript. The board above and every cause page work without it.</p></noscript>
</section>

<section aria-labelledby="refuse">
  <h2 id="refuse">IV. What this board refuses to do</h2>
  <div class="rules">
    <div><h3>No signature, no pledge</h3><p>A signature is a costless expression that ends in a number someone else
      reports. Nothing here can be signed.</p></div>
    <div><h3>No feed, no likes</h3><p>Every social metric measures you against other people. The only numbers on your
      assignment are the toll and the attention it gets.</p></div>
    <div><h3>One assignment at a time</h3><p>You cannot collect causes. Close one, then ask for another.</p></div>
    <div><h3>No score for intention</h3><p>No profile, no streak, no level. A resolution condition either came true by
      its date or it did not, and you are the one who wrote it.</p></div>
  </div>
  <p class="note"><b>Falsifier.</b> If no assignment issued here produces a resolution condition that comes true within
  180 days of launch, this board is a feed with extra steps, and the <a href="record/">public record</a> will say so.</p>
</section>

<section aria-labelledby="care">
  <h2 id="care">A note on suicide</h2>
  <p class="note">Suicide appears on this board as a public-health burden alongside other preventable causes of death.
  If it is personally relevant to you rather than professionally, you deserve support, not an assignment.</p>
  {support}
</section>
<script type="application/json" id="board-data">{data}</script>
""".format(
        n=len(ranked), ref_vpd=sig(ref["vpd"]), ref_name=e(ref["name"].lower()), low_vpd=sig(lowest["vpd"]),
        low_url=cause_path(lowest), low_name=e(lowest["name"]), low_name_lc=e(lowest["name"].lower()),
        ratio=e(fmt_ratio(ratio)), dratio=e(fmt_ratio(deaths_ratio)), w0=e(month_name(w0)), w1=e(month_name(w1)),
        rows="".join(rows), orders=int(math.floor(hi - lo)), pulled=e(long_date(board["pulled"])),
        cap_html="".join(
            '<fieldset class="cap"><legend class="cn">%s</legend><p class="cd">%s</p><div class="seg" data-cap="%s">%s</div></fieldset>'
            % (e(c["label"]), e(c["desc"]), e(c["id"]),
               "".join('<button type="button" data-v="%d" aria-pressed="%s">%s</button>' % (i, "true" if i == 0 else "false", lab)
                       for i, lab in enumerate(("none", "some", "strong", "decisive"))))
            for c in causes["capabilities"]),
        rarity_html="".join('<button type="button" data-i="%d" aria-pressed="false">%s</button>' % (i, e(lab))
                            for i, (lab, _) in enumerate(D.RARITY)),
        scale_html="".join('<button type="button" data-i="%d" aria-pressed="false">%s</button>' % (i, e(lab))
                           for i, (lab, _) in enumerate(D.SCALE)),
        support=support_box(causes, root), data=data.replace("</", "<\\/"))
    title = "The attention gap: preventable causes of death ranked by how little attention they get"
    desc = ("%d preventable causes of death ranked by Wikipedia views per death, from %s (%s views per death) to %s. "
            "Every toll sourced and dated. Then get one assignment matched to what you can do."
            % (len(ranked), lowest["name"].lower(), sig(lowest["vpd"]), ranked[-1]["name"].lower()))
    ld = [{
        "@context": "https://schema.org", "@type": "Dataset", "name": "The attention gap: deaths per Wikipedia pageview",
        "description": desc, "url": site.abs(""), "license": "https://creativecommons.org/licenses/by/4.0/",
        "creator": {"@type": "Organization", "name": NAME, "url": site.repo_url},
        "temporalCoverage": "%s/%s" % (w0, w1), "dateModified": board["pulled"], "isAccessibleForFree": True,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": site.abs("data/board.csv")},
                         {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": site.abs("data/board.json")}],
        "variableMeasured": ["deaths per year", "English Wikipedia pageviews (12 months)", "pageviews per death"],
    }, {"@context": "https://schema.org", "@type": "WebSite", "name": NAME, "url": site.abs("")}]
    site.page("", title, desc, body, board["pulled"], 0, og="default", ld=ld, scripts=("app.js",), active="board")


# ---------------------------------------------------------------- cause pages

def build_cause(site, causes, board, sources, row, prev_row, next_row):
    depth = 2
    root = "../../"
    ref = board["reference"]
    w0, w1 = board["window"][0], board["window"][-1]
    status, vtext = verification(row, sources)
    articles = "".join('<li><a href="%s" rel="noopener">%s</a>: %s views</li>' % (e(article_url(t)), e(t), fmt_int(v))
                       for t, v in row["per_article"])
    orgs = "".join('<li><a href="%s" rel="noopener">%s</a></li>' % (e(o["url"]), e(o["name"])) for o in row["orgs"])
    lever_src = ""
    if row.get("lever_source"):
        lever_src = '<p class="small">Also drawn from: <a href="%s" rel="noopener">%s</a>.</p>' % (
            e(row["lever_source"]["url"]), e(row["lever_source"]["title"]))
    support = support_box(causes, root) if row.get("support_note") else ""
    times = ref["vpd"] / row["vpd"] if row["vpd"] else 0
    range_note = ""
    if row["bound"] == "range":
        range_note = (" The board uses the midpoint, %s, for the arithmetic." % fmt_int(row["deaths"]))
    neighbours = []
    if prev_row:
        neighbours.append('<a href="../%s/">&larr; #%d %s</a>' % (prev_row["id"], prev_row["rank"], e(prev_row["name"])))
    if next_row:
        neighbours.append('<a href="../%s/">#%d %s &rarr;</a>' % (next_row["id"], next_row["rank"], e(next_row["name"])))
    body = """
<nav class="crumbs" aria-label="Breadcrumb"><a href="{root}">Board</a> &rsaquo; #{rank} of {n}</nav>
{support}
<article class="cause">
  <h1>{name}</h1>
  <p class="lede">{toll_text} {measure} a year{period_lede}, and {views} human views of the related English Wikipedia
  articles in the last 12 months: <strong>{vpd} views per death</strong>.</p>
  <div class="stats">
    <div><div class="hlab">Deaths a year</div><div class="hnum">{toll_short}</div><div class="hsub">{period_stat}</div></div>
    <div><div class="hlab">Views, {w0s} to {w1s}</div><div class="hnum">{views}</div>{spark}</div>
    <div><div class="hlab">Views per death</div><div class="hnum">{vpd}</div><div class="hsub">rank {rank} of {n}, lowest first</div></div>
  </div>
  {ratio_line}

  <h2>The figure and its source</h2>
  <blockquote cite="{src_url}"><p>&ldquo;{quote}&rdquo;</p>
  <footer>{publisher}, <a href="{src_url}" rel="noopener">{src_title}</a></footer></blockquote>
  <p class="verify verify-{status}">{vtext}{range_note}</p>

  <h2>What would move it</h2>
  <p>{lever}</p>
  {lever_src}

  <h2>Who is already working on it</h2>
  <ul>{orgs}</ul>
  <p class="small">Listed for reference so that you start by not duplicating them. They do not run or endorse this board.</p>

  <h2>Is this where your ability lies?</h2>
  <p>The board's assignment tool weighs this gap against {n_minus} others and what you can do.
  <a class="button" href="{root}#declare-section">Get your assignment</a></p>

  <h2>How the attention was measured</h2>
  <p>English Wikipedia pageviews by human readers (all devices; known bots excluded), {w0l} to {w1l}, summed over:</p>
  <ul>{articles}</ul>
  <p class="small">Pulled from the Wikimedia REST API on {pulled}. Neglect index {neglect} (1 = the most-watched cause on the
  board). <a href="{root}method/">Method and limits</a>.</p>

  <div class="share" data-share data-title="{share_title}" data-text="{share_text}">
    <button type="button" data-share-native hidden>Share</button>
    <button type="button" data-share-copy>Copy link</button>
    <a href="{root}og/{id}.png" rel="noopener">Share card (image)</a>
  </div>
</article>
<nav class="neighbours" aria-label="Neighbouring causes">{neighbours}</nav>
""".format(
        root=root, rank=row["rank"], n=len(board["causes"]), support=support, name=e(row["name"]),
        toll_text=e(toll(row)[0].upper() + toll(row)[1:]), measure=e(row["measure"]), period_lede=e(period_note(row)),
        period_stat=e(row["period"] if row["period"] != "annual" else "latest yearly estimate"),
        views=fmt_int(row["views"]), vpd=sig(row["vpd"]), toll_short=e(toll(row, short=True)),
        w0s=e(month_name(w0, True)), w1s=e(month_name(w1, True)),
        spark=sparkline(row["monthly"], board["window"], "Monthly Wikipedia views, %s to %s" % (month_name(w0), month_name(w1))),
        ratio_line=("" if row.get("support_note") else
                    '<p class="ratio">A shark-attack death drew <b>%s&times;</b> more Wikipedia attention than a death '
                    'from %s over the same months.</p>' % (e(fmt_ratio(times)), e(row["name"].lower()))),
        src_url=e(row["source"]["url"]),
        quote=e(row["source"]["quote"]), publisher=e(row["source"]["publisher"]), src_title=e(row["source"]["title"]),
        status=status, vtext=e(vtext), range_note=e(range_note), lever=e(row["lever"]), lever_src=lever_src,
        orgs=orgs, n_minus=len(board["causes"]) - 1, w0l=e(month_name(w0)), w1l=e(month_name(w1)), articles=articles,
        pulled=e(long_date(board["pulled"])), neglect="%.2f" % row["neglect"], id=e(row["id"]),
        share_title=e("%s: %s views per death" % (row["name"], sig(row["vpd"]))),
        share_text=e("%s: %s deaths a year, %s Wikipedia views per death." % (row["name"], toll(row, short=True), sig(row["vpd"]))),
        neighbours=" ".join(neighbours))
    title = "%s: %s deaths a year, %s Wikipedia views per death" % (row["name"], toll(row, short=True), sig(row["vpd"]))
    desc = ("%s estimates %s %s a year%s. The related English Wikipedia articles drew %s human views in 12 months: "
            "%s per death, rank %d of %d on the attention gap board."
            % (row["source"]["publisher"], toll(row), row["measure"], period_note(row), fmt_int(row["views"]),
               sig(row["vpd"]), row["rank"], len(board["causes"])))
    verified = sources.get("sources", {}).get(row["id"], {}).get("verified", "")
    lastmod = max(board["pulled"], verified or "")
    ld = [{"@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc,
           "url": site.abs(cause_path(row)), "dateModified": lastmod, "citation": row["source"]["url"],
           "isPartOf": {"@type": "WebSite", "name": NAME, "url": site.abs("")}},
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
              {"@type": "ListItem", "position": 1, "name": "Board", "item": site.abs("")},
              {"@type": "ListItem", "position": 2, "name": row["name"], "item": site.abs(cause_path(row))}]}]
    site.page(cause_path(row), title, desc, body, lastmod, depth, og=row["id"], ld=ld, scripts=("share.js",))


# ---------------------------------------------------------------- method, record, data, about, embed

def build_method(site, causes, board, sources):
    root = "../"
    ref = board["reference"]
    w0, w1 = board["window"][0], board["window"][-1]
    caps = ", ".join(c["label"].lower() for c in causes["capabilities"])
    rows = []
    for r in board["causes"] + [ref]:
        arts = "; ".join('<a href="%s" rel="noopener">%s</a>' % (e(article_url(t)), e(t)) for t, _ in r["per_article"])
        rows.append('<tr><td class="l">%s</td><td class="l">%s</td><td class="l small">%s, %s</td></tr>'
                    % (e(r["name"]) if r.get("is_reference") else '<a href="%s%s">%s</a>' % (root, cause_path(r), e(r["name"])),
                       arts, e(r["source"]["publisher"]), e(r["period"])))
    body = """
<h1>Method</h1>
<p class="lede">Every number on the board is either copied from a named source or computed from public pageview counts.
Nothing is estimated by us, and nothing is weighted by anyone's opinion of a cause.</p>

<h2>Deaths a year</h2>
<p>Each toll is copied from the cited publisher, almost always a World Health Organization fact sheet, with the exact phrase
quoted on the cause's page. A weekly job fetches every source page and checks that the quoted phrase is still there. If a
publisher revises a figure, the row is marked <em>under review</em> until the new figure is entered; the old figure is not
silently kept as if confirmed. Where a source gives a range, the board uses the midpoint and shows the range.</p>
<p><b>Rows overlap.</b> The tolls come from different methods and years ({years}). Some count deaths <em>caused</em> by a
condition, others deaths <em>attributable</em> to a risk factor, and AMR counts deaths <em>associated with</em> resistant
infections. The same death can appear in more than one row: a child who dies of diarrhoea is in both "Unsafe water,
sanitation and hygiene" and "Diarrhoeal disease in young children". The board compares attention per death within each row.
It never adds rows together.</p>

<h2>Attention</h2>
<p>Attention is the number of views of English Wikipedia articles about the cause, by human readers (the Wikimedia
<code>user</code> agent type, which excludes identified bots and crawlers), on all devices, over the last 12 complete months:
{w0} to {w1}. Each cause sums up to four articles, listed below and on its page, so that a cause is not penalised for
having its readers spread across several titles. When an article is renamed, both titles are counted. Data: the
<a href="https://wikimedia.org/api/rest_v1/">Wikimedia REST API</a>, refreshed weekly; a new month appears after
Wikimedia publishes it.</p>
<p><b>Honest limit.</b> English Wikipedia is a proxy for anglophone attention, not world attention, and it undercounts causes
discussed mostly in other languages. Article choice matters at the margin. The range on the board spans several orders of
magnitude, which no plausible proxy error closes, so read the ranking as directional.</p>

<h2>The reference row</h2>
<p>The benchmark is shark attacks: {ref_toll} confirmed shark-related deaths worldwide in {ref_period}, according to the
<a href="{ref_url}" rel="noopener">International Shark Attack File</a>, against {ref_views} views of the Wikipedia article
"Shark attack". It shows how much attention the world can give a rare death. An earlier prototype used a recent armed attack
as the benchmark; that read as ranking the victims of a political event, so a neutral, famously over-covered cause of death
replaced it. The reference row is never assigned.</p>

<h2>Views per death and the neglect index</h2>
<p><code>views per death = views in the 12-month window &divide; deaths a year</code>. The board is sorted by this, lowest first.
The <code>neglect index = log&#8321;&#8320;(deaths &divide; views) &minus; (the same value for the most-watched cause) + 1</code>, so the
most-watched cause scores 1 and the least-watched scores highest. It is logarithmic because raw deaths-per-view spans
several orders of magnitude: on a linear scale the single most neglected cause would win every assignment, whatever the
person could do.</p>

<h2>The assignment</h2>
<p>You rate nine capabilities ({caps}) from none (0) to decisive (3). Each cause carries a rating of how much it needs each
capability. Then:</p>
<p><code>score = neglect index &times; fit&sup2; &times; rarity &times; scale</code></p>
<ul>
<li><b>Fit</b> is the cosine similarity between what you declared and what the cause needs: a match of shape, not of volume,
so declaring more does not raise your score, only declaring the right things does. It is squared so that what you can do
dominates and neglect breaks ties between things you can do.</li>
<li><b>Rarity</b> (thousands 1, hundreds 2, dozens 4, a handful 8) and <b>scale</b> (myself 1, a team 2, a company 4,
capital 6, an institution 8) multiply your score. They are shown on the assignment, but they apply to every cause equally,
so they never change which cause you get.</li>
<li>The cause with the highest score is your assignment; ties go to the more neglected cause. The three runners-up are shown.
If nothing you declared matches anything a cause needs, the board says so instead of forcing a fit.</li>
</ul>
<p><b>Who rated the needs.</b> The need ratings and the "what would move it" summaries were written by the people who built this
board from the cited WHO material. They have not been reviewed by public-health experts or by the organisations listed.
<a href="{repo_url}/issues/new?template=correction.yml">Corrections are welcome</a>.</p>

<h2>The falsifier</h2>
<p>If no assignment issued here produces a resolution condition that comes true within 180 days of launch
({launched} to {deadline}), the board is a feed with extra steps. The <a href="{root}record/">public record</a> shows the
running count and will say so.</p>

<h2>Every article and source</h2>
<div class="tablewrap"><table class="method"><thead><tr><th class="l">Cause</th><th class="l">Wikipedia articles counted</th>
<th class="l">Toll source</th></tr></thead><tbody>{rows}</tbody></table></div>
""".format(years=e(", ".join(sorted({r["period"] for r in board["causes"]}))), w0=e(month_name(w0)), w1=e(month_name(w1)),
           ref_toll=e(toll(ref)), ref_period=e(ref["period"]), ref_url=e(ref["source"]["url"]), ref_views=fmt_int(ref["views"]),
           caps=e(caps), repo_url=e(site.repo_url), launched=e(long_date(causes["launched"])),
           deadline=e(long_date(add_days(causes["launched"], 180))), root=root, rows="".join(rows))
    desc = ("How the attention gap board measures deaths, attention and neglect: sourced death tolls, Wikipedia pageviews by "
            "human readers, the neglect index and the assignment formula, with every limit stated.")
    site.page("method/", "Method: how the attention gap board measures neglect", desc, body, board["pulled"], 1,
              active="method")


def falsifier_state(causes, record, today):
    """('running'|'passed'|'failed', sentence). Derived from the record, never hard-coded."""
    deadline = add_days(causes["launched"], 180)
    first = record.get("first_true") or ""
    if record.get("came_true", 0) > 0 and first and first <= deadline:
        return "passed", "Passed: the first publicly recorded condition came true on %s." % long_date(first)
    if today > deadline:
        return "failed", ("Failed: no publicly recorded condition came true between %s and %s. By its own test, "
                          "this board is a feed with extra steps." % (long_date(causes["launched"]), long_date(deadline)))
    return "running", ("Running: at least one publicly recorded condition must come true by %s."
                       % long_date(deadline))


def build_record(site, causes, record):
    state, sentence = falsifier_state(causes, record, site.built)
    issues = site.repo_url + "/issues?q=" + "is%3Aissue+label%3Acommitment"
    body = """
<h1>Public record</h1>
<p class="lede">Assignments are private: nothing you type on this site is sent anywhere. If you choose to, the assignment card
can open a public GitHub issue under your own GitHub account with your resolution condition and date. When the date comes,
close the issue as <em>completed</em> if the condition came true, or as <em>not planned</em> if it did not. This page counts
both.</p>
<div class="stats record">
  <div><div class="hlab">Public commitments</div><div class="hnum" data-record="total">{total}</div></div>
  <div><div class="hlab">Open, date not reached</div><div class="hnum">{open}</div></div>
  <div><div class="hlab">Past their date, not reported</div><div class="hnum">{overdue}</div></div>
  <div><div class="hlab">Came true</div><div class="hnum">{true_}</div></div>
  <div><div class="hlab">Did not</div><div class="hnum">{false_}</div></div>
</div>
<p class="falsifier falsifier-{state}" data-falsifier="{state}">{sentence}</p>
<p class="small">Counts come from GitHub issues labelled <code>commitment</code>, refreshed weekly{checked}. Issues marked
invalid, spam or duplicate are not counted. <a href="{issues}" rel="noopener">See every commitment</a>.</p>
<h2>Why a public record</h2>
<p>A resolution condition either comes true by its date or it does not. A public, dated record is the only honest way to
tell whether a board like this changes anything, which is why the falsifier depends on it.</p>
""".format(total=record.get("total", 0), open=record.get("open", 0), overdue=record.get("overdue", 0),
           true_=record.get("came_true", 0), false_=record.get("did_not", 0), state=state, sentence=e(sentence),
           checked=(", last on %s" % e(long_date(record["checked"]))) if record.get("checked") else "", issues=e(issues))
    desc = "The public record of commitments made from the attention gap board, and the board's own 180-day falsifier."
    site.page("record/", "Public record of commitments and the 180-day falsifier", desc, body,
              record.get("checked") or causes["launched"], 1, active="record")


def board_csv(board):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["rank", "id", "name", "measure", "deaths_per_year", "deaths_low", "deaths_high", "bound", "period",
                "source_publisher", "source_url", "views_12_months", "views_per_death", "neglect_index",
                "window_start", "window_end", "wikipedia_articles"])
    for r in board["causes"] + [board["reference"]]:
        w.writerow(["" if r.get("is_reference") else r["rank"], r["id"], r["name"], r["measure"], r["deaths"],
                    r.get("deaths_low", ""), r.get("deaths_high", ""), r["bound"], r["period"], r["source"]["publisher"],
                    r["source"]["url"], r["views"], "%.6g" % r["vpd"],
                    "" if r.get("is_reference") else "%.4f" % r["neglect"], board["window"][0], board["window"][-1],
                    " | ".join(t for t, _ in r["per_article"])])
    return buf.getvalue()


def build_data(site, causes, board, pageviews, sources):
    embed = ('<iframe src="%s" title="The attention gap" width="100%%" height="430" style="border:0;max-width:640px" '
             'loading="lazy"></iframe>' % site.abs("embed/"))
    body = """
<h1>Data</h1>
<p class="lede">Everything on the board, free to reuse. The compilation is licensed
<a href="https://creativecommons.org/licenses/by/4.0/" rel="noopener">CC BY 4.0</a>: credit "The Attention Gap Board" and link
back. Death tolls belong to their publishers, quoted briefly with attribution; Wikimedia pageview data is released by the
Wikimedia Foundation under CC0.</p>
<ul class="downloads">
<li><a href="board.csv" download>board.csv</a>: one row per cause, ranked, with tolls, sources, views and the neglect index</li>
<li><a href="board.json">board.json</a>: the same plus need ratings, levers and organisations (what the assignment tool uses)</li>
<li><a href="causes.json">causes.json</a>: the editorial file, exactly as maintained</li>
<li><a href="pageviews.json">pageviews.json</a>: monthly views per Wikipedia article for the window</li>
<li><a href="sources.json">sources.json</a>: the latest weekly check of every source page and link</li>
</ul>
<p class="small">Window {w0} to {w1}, pageviews pulled {pulled}. Source code and history:
<a href="{repo}" rel="noopener">{repo}</a>.</p>
<h2>Embed the board</h2>
<p>A compact card with the five least-watched causes and the reference row. Paste this into any page:</p>
<pre class="code"><code>{embed_code}</code></pre>
""".format(w0=e(month_name(board["window"][0])), w1=e(month_name(board["window"][-1])),
           pulled=e(long_date(board["pulled"])), repo=e(site.repo_url), embed_code=e(embed))
    desc = "Download the attention gap board: death tolls, Wikipedia pageviews and the neglect index as CSV and JSON (CC BY 4.0)."
    site.page("data/", "Data: download the attention gap board (CSV and JSON)", desc, body, board["pulled"], 1, active="data")
    site.write("data/board.csv", board_csv(board))
    site.write("data/causes.json", json.dumps(causes, indent=1, ensure_ascii=False) + "\n")
    site.write("data/pageviews.json", json.dumps(pageviews, indent=1, ensure_ascii=False) + "\n")
    site.write("data/sources.json", json.dumps(sources, indent=1, ensure_ascii=False) + "\n")


def build_about(site, causes, board):
    body = """
<h1>About</h1>
<p class="lede">The Attention Gap Board ranks preventable causes of death by how little attention each death gets, and turns
"what can I do?" into one concrete assignment with a dated test. It is free, has no accounts, and runs itself: scheduled jobs
refresh the attention data, re-check every source and rebuild the site.</p>
<h2>Who it is for</h2>
<p>People with real capability (founders, engineers, operators, clinicians, policy staff, researchers, organisers) who want
to do something consequential and would otherwise follow whatever the news cycle is watching.</p>
<h2>What it is not</h2>
<ul>
<li>Not medical advice, and not a ranking of how much any death matters. Every death on the board matters; the board measures
attention, not worth.</li>
<li>Not affiliated with the World Health Organization, the Wikimedia Foundation, the International Shark Attack File or any
organisation listed on a cause page. Organisations are named so that you can find people already doing the work.</li>
<li>Not a petition, feed or fundraiser. Nothing can be signed, liked or donated here.</li>
</ul>
<h2>Privacy</h2>
<p>No accounts and no cookies. Your declaration and resolution condition stay in your browser; the page address can hold your
declaration so that you can bookmark or share it, which is your choice. {analytics} If you post a commitment, it goes to
GitHub under your own account and follows GitHub's terms.</p>
<h2>Corrections</h2>
<p>Found a wrong figure, a broken source or a better organisation? <a href="{repo}/issues/new?template=correction.yml">Open a
correction</a>. Sources are re-checked automatically every week, and revised figures are flagged on the board until fixed.</p>
<h2>Sensitive content</h2>
<p>Suicide appears as a cause. The board follows safe-messaging practice: no method details, crisis resources on every page
that mentions it.</p>
{support}
""".format(analytics=("Visits are counted with GoatCounter, which uses no cookies and collects no personal data."
                      if site.goatcounter else "There are no analytics."),
           repo=e(site.repo_url), support=support_box(causes, "../"))
    desc = "What the attention gap board is, who it is for, what it refuses to do, and how it handles privacy and corrections."
    site.page("about/", "About the attention gap board", desc, body, board["pulled"], 1, active="about")


def build_embed(site, board):
    rows = "".join('<li><a href="%s" target="_top">%s</a><span>%s views per death</span></li>'
                   % (e(site.abs(cause_path(r))), e(r["name"]), sig(r["vpd"])) for r in board["causes"][:5])
    ref = board["reference"]
    doc = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The attention gap (embed)</title><meta name="robots" content="noindex"><link rel="canonical" href="{home}">
<link rel="stylesheet" href="../assets/style.css"></head>
<body class="embed"><div class="ecard">
<p class="kicker">The attention gap &middot; Wikipedia views per death</p>
<ol>{rows}</ol>
<p class="eref">Reference: {ref_name}, <b>{ref_vpd}</b> views per death.</p>
<p class="small">Window {w0} to {w1}. <a href="{home}" target="_top">See all {n} causes and get an assignment &rarr;</a></p>
</div></body></html>
""".format(home=e(site.abs("")), rows=rows, ref_name=e(ref["name"].lower()), ref_vpd=sig(ref["vpd"]),
           w0=e(month_name(board["window"][0], True)), w1=e(month_name(board["window"][-1], True)), n=len(board["causes"]))
    site.write("embed/index.html", doc)


def build_404(site):
    body = '<h1>Page not found</h1><p class="lede">That page is not on the board. <a href="%s/">Back to the board</a>.</p>' % e(site.url)
    site.page("404.html", "Page not found", "Page not found.", body, site.built, 0, index=False)
    site.pages.pop()   # never in the sitemap


# ---------------------------------------------------------------- share images (rendered later by scripts/og.py)

def og_card(title, big, small, foot):
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:1200px;height:630px;background:#141416;color:#fff;font-family:-apple-system,"Segoe UI",Inter,system-ui,sans-serif}}
.c{{box-sizing:border-box;width:1200px;height:630px;padding:64px 72px;display:flex;flex-direction:column;justify-content:space-between;border-left:10px solid #e8c35a}}
.k{{font:500 22px/1 ui-monospace,Menlo,monospace;letter-spacing:.28em;text-transform:uppercase;color:#a3a29a}}
h1{{font-size:64px;line-height:1.05;margin:26px 0 0;font-weight:700;letter-spacing:-.02em}}
.b{{font:600 50px/1.15 ui-monospace,Menlo,monospace;color:#e8c35a;margin-top:28px}}
.s{{font-size:30px;line-height:1.35;color:#c3c2b7;margin-top:14px}}
.f{{font:400 22px/1.3 ui-monospace,Menlo,monospace;color:#a3a29a}}
</style></head><body><div class="c"><div><div class="k">RESPONSE&middot;ABILITY &middot; the attention gap</div>
<h1>{title}</h1><div class="b">{big}</div><div class="s">{small}</div></div><div class="f">{foot}</div></div></body></html>
""".format(title=e(title), big=e(big), small=e(small), foot=e(foot))


def build_og_sources(site, board):
    ref = board["reference"]
    lowest = board["causes"][0]
    host = site.url.split("://", 1)[-1]
    cards = {"default": og_card("Which preventable deaths does the world look away from?",
                                "%s views per death" % sig(lowest["vpd"]),
                                "%s, against %s for a shark-attack death. %d causes ranked."
                                % (lowest["name"], sig(ref["vpd"]), len(board["causes"])), host)}
    for r in board["causes"]:
        t = toll(r, short=True)
        lead = "%s%s deaths a year%s." % (t[0].upper(), t[1:], period_note(r))
        tail = (" Help is available: findahelpline.com" if r.get("support_note")
                else " A shark-attack death draws %s views." % sig(ref["vpd"]))
        cards[r["id"]] = og_card(r["name"], "%s Wikipedia views per death" % sig(r["vpd"]), lead + tail,
                                 "%s · rank %d of %d" % (host, r["rank"], len(board["causes"])))
    for name, doc in cards.items():
        site.write("_og/%s.html" % name, doc)


# ---------------------------------------------------------------- robots, sitemap, assets

def build_meta(site, key):
    if site.indexable:
        robots = "User-agent: *\nAllow: /\n\nSitemap: %s\n" % site.abs("sitemap.xml")
        urls = ["<url><loc>%s</loc><lastmod>%s</lastmod></url>" % (e(site.abs(p)), lm)
                for p, lm, idx in site.pages if idx]
        site.write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n' % "\n".join(urls))
    else:
        robots = "User-agent: *\nDisallow: /\n"
    site.write("robots.txt", robots)
    site.write("%s.txt" % key, key + "\n")


def copy_assets(site):
    src = os.path.join(SITE, "assets")
    dst = os.path.join(site.out, "assets")
    shutil.copytree(src, dst)


def build(out=None, data_dir=D.DATA, env=None):
    out = out or os.path.join(ROOT, "dist")
    causes, pageviews, sources, record = D.load_all(data_dir)
    problems = D.validate_causes(causes) + D.validate_pageviews(causes, pageviews)
    if problems:
        raise SystemExit("refusing to build: " + "; ".join(problems))
    board = D.compute(causes, pageviews)
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    site = Site(out, env)
    copy_assets(site)
    build_home(site, causes, board, sources, record)
    ranked = board["causes"]
    for i, row in enumerate(ranked):
        build_cause(site, causes, board, sources, row, ranked[i - 1] if i else None,
                    ranked[i + 1] if i + 1 < len(ranked) else None)
    build_method(site, causes, board, sources)
    build_record(site, causes, record)
    build_data(site, causes, board, pageviews, sources)
    build_about(site, causes, board)
    build_embed(site, board)
    build_404(site)
    build_og_sources(site, board)
    with open(os.path.join(SITE, "indexnow-key.txt")) as fh:
        key = fh.read().strip()
    build_meta(site, key)
    site.write("data/board.json", json.dumps(board_json(board, causes, sources, record, site), indent=1,
                                             ensure_ascii=False) + "\n")
    urls = [site.abs(p) for p, _, idx in site.pages if idx] if site.indexable else []
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    with open(os.path.join(ROOT, "build", "urls.txt"), "w") as fh:
        fh.write("\n".join(urls) + ("\n" if urls else ""))
    return site, board


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    args = ap.parse_args(argv)
    site, board = build(args.out)
    print("built %d pages into %s (%s, %s)" % (len(site.pages), args.out, site.url,
                                               "indexable" if site.indexable else "noindex"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
