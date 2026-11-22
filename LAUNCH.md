# Launch and distribution

Launched 2026-11-22, indexed, and moved the same day to https://board.howcouldihelp.com/ (the first address,
theguysaccount.github.io/response-ability-attention-gap-board/, redirects there). Machine channels only: nothing is
posted, emailed or sent by or as a person.

## Channels that run themselves

| Channel | How |
|---|---|
| Search | The board answers "most neglected causes of death", "preventable deaths ranked", "deaths vs media attention". 35 cause pages answer "how many people die from <cause> each year" and "<cause> deaths per year", each with its own title, description, canonical URL, structured data and a sourced, dated figure. |
| IndexNow | Every deploy submits every URL (Bing, Yandex, Seznam, Naver). |
| robots.txt | `board.howcouldihelp.com/robots.txt` lists the sitemap, and so does the account root (`theguysaccount.github.io/robots.txt`), rebuilt daily. |
| Share loop | Every cause has a 1200×630 card ("0.0041 Wikipedia views per death"); the assignment's Share button sends the cause page; the native share sheet on phones. |
| Embed | `/embed/` card with copy-paste code on `/data/`, for blogs and course pages. |
| Open data | CSV/JSON under CC BY 4.0: citations become links. |
| GitHub | Public repo with description, topics and README. |

## The first 1,000 users (machine plan)

1. Week 1: IndexNow covers Bing-family engines; Google discovers the sitemap from the account root.
2. Weeks 2–8: cause pages pick up long-tail "how many people die from…" searches, which change little year to year, so
   pages that stay current (weekly source checks) should outrank stale listicles.
3. Ongoing: each share card carries the gap ratio, the most shareable fact on the site.

Targets at 60 days, once analytics is on: 1,000 board visitors, 15% computing an assignment, 20% of those taking a commit
action, 10 public commitments.

## Domain

`board.howcouldihelp.com` since 2026-11-22: one CNAME at Namecheap, added by the domain rollout session. The apex,
howcouldihelp.com, serves a separate Volunteer Offer Planner (Vercel), untouched. The settings, and how to move or roll
back, are in OPERATIONS.md ("Custom domain").
