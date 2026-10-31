# AGENTS.md

A Flask web app listing upcoming London Curzon cinema showtimes, scraped from
curzon.com. It runs as the systemd unit `curzon_listings` (gunicorn,
127.0.0.1:6752) out of `/home/imiell/git/curzon-listings`, behind nginx at
`https://ianmiell.com/curzon-listings/`. README.md covers how the scrape works
and how to run and deploy it.

## Layout

| File | |
|---|---|
| `curzon.py` | Scraper. `CurzonClient` gets a bearer token by loading curzon.com in headless Chrome, then calls OCAPI with `requests`; `fetch_listings` returns `{fetched_at, sites, films, showtimes}`. `python curzon.py [SITE ...]` scrapes once and prints JSON. |
| `app.py` | Flask routes, the background `update_listings` thread, date ranges and grouping. |
| `curzon_config.ini` | Sites, refresh interval, venue notes, films seen. Committed and public. |
| `templates/`, `static/` | Jinja templates (no JS), one stylesheet. |
| `deploy/` | systemd unit and nginx location block. |
| `cat_listings.sh` | Prints `/listings.txt` for the `curzon-listings` webhook. |

## Traps

- **Cloudflare.** curzon.com answers plain HTTP and Chrome's default headless
  user agent with a challenge. `dump_page` sets a normal user agent and a
  virtual time budget so the challenge runs. If the scrape fails with "no
  authToken", Cloudflare has probably tightened up; check `/health` and
  `make scrape`.
- **OCAPI quirks.** `siteIds` must be repeated (`?siteIds=A&siteIds=B`); a
  comma-joined list is a 400. Strings are `{"text": ..., "translations": []}`;
  use `text()`. Times are ISO with an offset; the app shows Europe/London.
- **The token is a secret of sorts.** Never log, print or commit it; report its
  length or expiry instead. `cache/listings.json` holds no token.
- **Keep one gunicorn worker.** Listings and the scraper thread are in process
  memory; more workers means more scrapes and Chrome runs.
- **Templates are cached by gunicorn**; restart after template changes. Static
  URLs carry `?v=<mtime>`.
- **Links must use `url_for`**: the app is served under `/curzon-listings`,
  which nginx passes as `X-Forwarded-Prefix` (`ProxyFix`).
- **Venue notes and films seen are the owner's**; leave their text alone.
  Notes edited on `/notes` live in `data/venue_notes.json` (not committed),
  which overrides `[venue_notes]` once it exists. `CURZON_NOTES_PASSWORD`
  (from `.env`) turns the editor on; never log, print or commit it.

## Checking a change

```sh
make check                    # prints four 200s
make scrape                   # live scrape, ~1 minute; logs film/showtime counts
```

All seven London sites should have showtimes, with titles and times. For UI
changes, run `make run` and look at film and cinema views on a phone-width
window too.

## Conventions

- Plain Flask, type hints and docstrings on helpers, no JS, no build step.
- Commit messages `area: action` (`scrape: handle new token location`), with
  `Fixes #N` / `Refs #N` in the body.
- Deploying is the owner's (`git pull`, `make restart`; `make install` and
  nginx changes need sudo).
