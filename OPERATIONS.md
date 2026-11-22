# Operations

Live at https://board.howcouldihelp.com/ (indexed; there is no other live version). The first address,
https://theguysaccount.github.io/response-ability-attention-gap-board/, redirects there. The apex, howcouldihelp.com,
serves a separate tool (a Volunteer Offer Planner, on Vercel) that this repo never touches.
Everything below runs on GitHub Actions in this repo. Nobody needs to do anything for the site to keep working.

## Automated jobs

| Workflow | When | What it does | How it fails safe |
|---|---|---|---|
| `refresh.yml` | Mondays 05:47 UTC and the 4th of each month 07:13 UTC, or by hand | `python -m board.refresh all`: (1) pageviews for the last 12 complete months from the Wikimedia REST API, human readers only; (2) fetches every source page and checks that the quoted phrase behind each toll is still there, and that every organisation and helpline link answers; (3) counts GitHub issues labelled `commitment`. Runs the tests on the new data, commits `data/`, dispatches `deploy.yml`, then opens or closes `ops-alert` issues. Keep-alive afterwards. | An unreachable source keeps its last good value. A pageview total that halves in one run is kept at its last good value and raises an alert (renamed or deleted article). If more than a quarter of articles fail, or no source page answers, that step writes nothing and the run ends red. Failing tests stop the commit. |
| `deploy.yml` | Pushes to `main` that touch the site, and every refresh that changed data | Tests, build, share images, headless-Chrome end-to-end run on the built site, Pages deploy (a second attempt if the first times out), the same end-to-end run on the live site, IndexNow. | Anything that fails before the deploy step leaves the last good deploy live. |
| `selftest.yml` | Thursdays 06:53 UTC, or by hand | Tests on `main`; `scripts/health.py` checks 15 live URLs, that indexing matches the configuration, that every cause page is in the sitemap, and that the data is fresh; then the live end-to-end run. Keep-alive afterwards. | Read-only. If the pageview window is a month behind or the source check is over 15 days old, it dispatches `refresh.yml` and passes with a warning; two months or 30 days behind fails the run. |
| `ci.yml` | Every push and pull request | The full test suite on Python 3.9 and 3.12, plus the Node tests. | — |

**Keep-alive.** `scripts/keepalive.sh` runs after every scheduled refresh and self-test. It re-enables every scheduled
workflow (except one someone disabled by hand) and pushes an empty commit after 40 quiet days, so GitHub never disables
the schedules. The weekly data commit normally keeps the repo active anyway.

**Schedules on this account fire late.** GitHub has started this account's crons hours late and skipped some. Nothing here
depends on exact times: every job is safe to re-run, and the self-test dispatches the refresh when data is stale.

## What to watch

| Signal | Where | Healthy |
|---|---|---|
| Runs | Actions tab; GitHub emails the account owner on failure | Weekly refresh and self-test green |
| `ops-alert` issues | Issues tab | None open. Each one says exactly what to change in `data/causes.json` |
| Figures under review | A yellow "under review" tag on the board | None. It means a publisher revised a figure (WHO revises fact sheets several times a year) |
| Public commitments | `/record/` and issues labelled `commitment` | Growing; the falsifier deadline is 21 May 2027 |
| Corrections | Issues labelled `correction` | Answered within a month |
| Activation (once analytics is on) | GoatCounter events `assignment`, `commit-copy`, `commit-ics`, `commit-public`, `share` | Over 20% of assignments followed by a commit action |

### When an alert opens

- **Source no longer shows the quoted figure**: open the source page, find the new estimate, and update `deaths`,
  `period` and `source.quote` (a phrase of 15 words or fewer, copied exactly) for that cause in `data/causes.json`. Push.
  The next refresh closes the alert.
- **Source page not found**: find the publisher's current page and update `source.url` and `source.quote`.
- **Pageviews fell by more than half**: the Wikipedia article was probably renamed or merged. Put the new title in
  `articles`, or keep it and add the old title under `aliases`.
- **Link not answering**: if the organisation moved, update its `url`.

Run `python3 -m unittest discover -s tests -t .` before pushing; the build refuses invalid data anyway.

## Scheduled Claude routine (optional, set up once by a person)

Actions has no model API key, so editorial work is a Claude Code routine. Monthly, in a checkout of this repo:

> In ~/code/response-ability-attention-gap-board (git pull first):
> 1. For every open issue labelled `ops-alert` or `correction`, check the publisher's own page and fix `data/causes.json`
>    exactly as OPERATIONS.md describes. Quote 15 words or fewer, copied exactly. Close each issue with a one-line comment.
> 2. Add up to three new preventable causes with a WHO (or comparable public-health body) fact sheet that states a yearly
>    death toll, using the same fields as the existing causes. Need ratings are 0–3 per capability; write the lever only
>    from the cited material; name an organisation that works on it and link its own site. No method details for
>    self-harm. Make no medical claims.
> 3. Run `python3 -m board.refresh pageviews` and `python3 -m board.refresh sources`, then the tests and
>    `node --test tests/js.test.mjs`. Commit and push. The push deploys. Do not post anywhere.

Without the routine the board keeps refreshing its attention data and flagging revised figures indefinitely.

## Keys Jack can turn later

| Key | Why | Exact steps |
|---|---|---|
| **Custom domain** (turned 2026-11-22) | Brand, a domain-level robots.txt, Search Console | In place since the domain rollout on 2026-11-22: Namecheap → howcouldihelp.com → Advanced DNS has `CNAME board → theguysaccount.github.io.`, the Pages custom domain is `board.howcouldihelp.com` with HTTPS enforced, and the repo variable `SITE_URL` is `https://board.howcouldihelp.com`, the one setting every page, sitemap and check reads. The apex and www records (the Volunteer Offer Planner on Vercel) are untouched. **To move to another host:** add its CNAME, then `~/.local/bin/gh api -X PUT repos/theguysaccount/response-ability-attention-gap-board/pages -f cname=<host>`, `~/.local/bin/gh variable set SITE_URL -R theguysaccount/response-ability-attention-gap-board -b https://<host>`, `~/.local/bin/gh workflow run deploy.yml -R theguysaccount/response-ability-attention-gap-board`, and once the certificate is issued `~/.local/bin/gh api -X PUT repos/theguysaccount/response-ability-attention-gap-board/pages -F https_enforced=true`; then delete the old CNAME. **To go back to github.io:** `~/.local/bin/gh api -X PUT repos/theguysaccount/response-ability-attention-gap-board/pages --input - <<< '{"cname":null}'`, `~/.local/bin/gh variable delete SITE_URL -R theguysaccount/response-ability-attention-gap-board`, `~/.local/bin/gh workflow run deploy.yml -R theguysaccount/response-ability-attention-gap-board`, then delete `CNAME board` at Namecheap straight away: a CNAME left pointing at GitHub Pages with no site claiming it can be taken over. |
| **Money: support link** | First revenue without breaking GitHub Pages' non-commercial terms | Create a GitHub Sponsors profile, Open Collective or grant page, then `gh variable set SUPPORT_URL -b <url>` (optionally `SUPPORT_LABEL`) and run `deploy.yml`. A link appears in every footer. |
| **Analytics** | Measure activation | Create a GoatCounter site, `gh variable set GOATCOUNTER_URL -b https://<code>.goatcounter.com/count`, run `deploy.yml`. Cookieless; the About page updates its privacy line automatically. |
| **Search Console** | Google indexing data (Bing and others get IndexNow already) | Needs Jack's Google account and one DNS TXT record for howcouldihelp.com at Namecheap. The site's own robots.txt and the account-root robots.txt already list the sitemap. |
| **Organisation intake (the evaluator's cheapest test)** | Whether named organisations want routed specialists | A person emails three listed organisations. If one agrees, add an `intake` URL to its entry in `causes.json` and show it on the assignment card. Never route people to an organisation that has not agreed. |
| **Expert review of need ratings** | Credibility | Ask a public-health reviewer to check the 0–3 ratings; record the review in `DECISIONS.md` and on the method page. |
| **Turn indexing off** | Only if a duplicate ever appears | `gh variable set SITE_INDEXABLE -b false` and run `deploy.yml`: noindex everywhere, robots.txt disallows, no sitemap, IndexNow skipped. |
