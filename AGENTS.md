# AGENTS.md

Scrapes London Curzon cinema showtimes from curzon.com, stores them in SQLite
and publishes a plain-text listings page (today, tomorrow or the weekend, and
everything ahead, by film and by cinema). It runs from cron on the owner's
Linux server out of `/home/imiell/git/curzon-listings` and publishes to
`/var/www/ianmiell.com/curzon-listings/`.

## Pipeline

| Step | File | What it does |
|------|------|--------------|
| 1. Capture | `capture_curzon_headless.js` | Headless puppeteer visits `https://www.curzon.com/venues/aldgate/`, then each other venue in `SITE_ALLOWLIST` that has no showtimes yet, and merges the site's `VistaOmnichannelComponents::browsing-domain-store` localStorage entry (`filmsById`, `showtimesById`, `sitesById`) across them. Writes everything to `curzon_tokens.json`. |
| 2. Load | `curzon-listings-populate-db.sh` | Skips if `curzon-showtimes.db` was written in the last 30 minutes today (unless `FORCE=1`). Pulls the store out of `curzon_tokens.json` with jq, emits `startsAt\|title\|siteId;` per successful showtime, splits on `;` and pipes the lines into `import_showtimes.py`. Also writes `curzon_tokens_cleaned.json` (the store, pretty-printed). The node call to step 1 is commented out here, so cron runs step 1 separately. |
| 2b. | `import_showtimes.py` | Reads `time\|title\|location` lines on stdin into `curzon-showtimes.db` (`--db` to override): tables `film(title)`, `location(code)`, `film_showtime(film_title, location_code, starts_at)`. Clears all tables first unless `--keep-existing`. |
| 3. Publish | `curzon-listings-query-db.sh` | Queries the DB into `curzon_listings.txt` and **copies it to `/var/www/ianmiell.com/curzon-listings/`**. Sections: VENUE GUIDE (hard-coded notes), BY FILM / BY CINEMA TODAY, then TOMORROW on Saturdays or THIS WEEKEND Monday to Friday (nothing extra on Sundays), then ALL TIME. |
| Serve | `cat_listings.sh`, `README.md` | `cat_listings.sh` prints the file; `README.md` shows the `webhook` hook config. |
| Install | `Makefile` | `make install` (sudo) copies the scripts, `node_modules` and puppeteer's Chrome cache to `/var/www/ianmiell.com/curzon-listings` and chowns them to `www-data`. |

Venue codes: `ALD1` Aldgate, `BLO1` Bloomsbury, `CAM1` Camden, `HOX1` Hoxton,
`MAY1` Mayfair, `SOH1` Soho, `VIC1` Victoria.

## Traps

- **Running `curzon-listings-query-db.sh` publishes.** Its last lines copy the
  output over the live page. To test it, run a copy without that line:
  `sed '/\/var\/www/d' curzon-listings-query-db.sh > agent-query-check.sh && bash agent-query-check.sh; rm -f agent-query-check.sh`.
- **`curzon_tokens*.json` hold bearer tokens and cookies.** They and `capture/`
  are gitignored. Never commit them, print them, or paste values into issues or
  PRs; report key names, sizes and counts instead.
- **The venue list exists twice**: `SITE_ALLOWLIST` in
  `capture_curzon_headless.js` and the `location_names` CTE in
  `curzon-listings-query-db.sh`. Change both. A code missing from the CTE shows
  as the raw code in the listings.
- **Everything depends on curzon.com's Vista front end.** If the store key,
  `loadingState` / `payload` shapes or the `/venues/<slug>/` URLs change, the
  capture or the jq in step 2 silently yields nothing. Check the counts:
  `sqlite3 curzon-showtimes.db "SELECT location_code, count(*) FROM film_showtime GROUP BY 1;"`.
- **`curzon_listings.txt` is generated** but tracked; the owner's `latest`
  commits carry it. Don't hand-edit it or include it in code changes. Because
  cron rewrites it in the live checkout, `git pull` there needs it committed or
  checked out first.
- **Times**: `starts_at` is Vista's `schedule.startsAt` string as given; the
  queries compare it with `date('now', 'localtime')`, so check offsets and BST
  when touching the date logic. The weekend and tomorrow ranges use SQLite
  `weekday N` modifiers keyed off `date +%u`.
- **Linux only**: the scripts use GNU `stat -c` and `date -r`, the
  linuxbrew `sqlite3` fallback and an nvm node path under `/home/imiell`.
  They won't run unchanged on macOS.
- **The VENUE GUIDE and FILMS SEEN text is the owner's personal notes**,
  hard-coded in the query script. Leave it to them.

## Known quirks (not yet fixed)

- `curzon-listings-populate-db.sh` tests `[ ! $FORCE == 1 ]`, which errors
  when `FORCE` is unset, so the 30-minute skip never applies.
- `tr -d "'"` in step 2 strips apostrophes from film titles.
- The query script prints BY CINEMA ALL TIME twice, and its FILMS SEEN block
  is echoed after the output redirect, so it goes to stdout, not the file.
- `import_showtimes.py` prints debug lines and calls `parse_line` twice per line.
- `README.md` still refers to a `curzon-listings.sh`, which no longer exists.

## Checking a change

There is no test suite. From a clone (not the live checkout):

```sh
bash -n *.sh && python3 -m py_compile import_showtimes.py && node --check capture_curzon_headless.js
npm ci                                   # once; needs puppeteer's Chrome
node capture_curzon_headless.js          # hits curzon.com
FORCE=1 ./curzon-listings-populate-db.sh
sqlite3 curzon-showtimes.db "SELECT location_code, count(*) FROM film_showtime GROUP BY 1;"
# then the query script with the publish line stripped (see Traps), and read curzon_listings.txt
git checkout curzon_listings.txt
```

All seven venues should have showings, with titles (not film IDs) and times.

## Conventions

- Bash, 2-space indentation; `set -euo pipefail` in new scripts. Keep the
  scripts `cd`ing to their own directory first, as cron relies on it.
- Commit messages: the owner uses `latest` for regenerated listings; for code
  use `area: action` (`query: fix weekend range`), with `Fixes #N` or
  `Refs #N` in the body.
- Deploying is the owner's: `git pull` in `/home/imiell/git/curzon-listings`,
  plus `make install` for changes to the Makefile, `node_modules` or puppeteer.

## Agents

An agent team (monitor, triage, engineer, code-reviewer) maintains this repo
from `~/git/curzon-listings-agents`; see
[`ianmiell/software-agents` `teams/curzon`](https://github.com/ianmiell/software-agents/tree/main/teams/curzon).
Give it work with `gh issue create --label agent-task`.
