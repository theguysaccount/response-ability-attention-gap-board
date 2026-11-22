# The Attention Gap Board (RESPONSE·ABILITY)

**Live:** https://board.howcouldihelp.com/

Preventable causes of death ranked by how little attention each death gets: annual deaths from the cited source
(mostly WHO fact sheets) divided into 12 months of English Wikipedia pageviews by human readers. A visitor then
declares what they can actually do, and the board returns exactly one assignment with a dated, falsifiable
resolution condition. No accounts, no feed, nothing stored.

- **35 causes**, each with a sourced, dated toll (exact phrase quoted and re-checked weekly), the Wikipedia articles
  counted, a 12-month attention sparkline, what would move it, and who already works on it.
- **The assignment**: neglect index × fit² × rarity × scale, with every term shown. A calendar file and an optional
  public GitHub issue give the commitment a date and a record.
- **A falsifier**: if no publicly recorded condition comes true within 180 days of launch, the record page says the
  board failed its own test.
- Open data: CSV and JSON under CC BY 4.0, plus an embeddable card.

## Run

```bash
python3 -m board.refresh all      # pageviews, source checks, public-record counts (network; polite and slow)
python3 -m board.site             # build into dist/
python3 scripts/og.py dist        # share images (needs Google Chrome; falls back to a default card)
python3 -m http.server 8871 --directory dist
```

Python 3.9+, standard library only. Node is only needed for the JavaScript tests and the screenshot script.

## Test

```bash
python3 -m unittest discover -s tests -t .    # data, refresh (fake network), build, JS/Python parity
node --test tests/js.test.mjs                 # the assignment logic in site/assets/core.js
scripts/e2e.sh                                # headless Chrome drives the built site (or pass a live URL)
node scripts/screens.mjs http://127.0.0.1:8871   # screenshots into docs/screens/
```

## Deploy

Pushing to `main` runs `.github/workflows/deploy.yml`: tests, build, share images, a headless end-to-end run, the
Pages deploy, a live end-to-end run and IndexNow. `refresh.yml` (weekly) commits new data and dispatches the deploy.
`selftest.yml` (weekly) checks the live site and dispatches the refresh if data is stale. Settings, keys and failure
modes: [OPERATIONS.md](OPERATIONS.md).

## Files

| Path | What |
|---|---|
| `data/causes.json` | Editorial: causes, sourced tolls, quoted phrases, Wikipedia articles, need ratings, levers, organisations |
| `data/pageviews.json` | Machine: monthly pageviews per article (written by `board.refresh pageviews`) |
| `data/sources.json` | Machine: the weekly check of every source page and link |
| `data/record.json` | Machine: counts of public commitments (GitHub issues labelled `commitment`) |
| `board/` | Validation, computation, refresh jobs and the static-site builder |
| `site/assets/` | CSS and the browser code (`core.js` is pure and tested in Node) |

Code: MIT. Data: CC BY 4.0. See [LICENSE](LICENSE).
