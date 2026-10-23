# curzon-listings

A small Flask web app listing upcoming films at London Curzon cinemas,
scraped from [curzon.com](https://www.curzon.com/). Browse by film or by
cinema for today, tomorrow, the weekend, the next 7 days or everything on
sale; filter by cinema; each time links straight to Curzon's seat picker.

## How the scrape works

curzon.com is behind a Cloudflare JavaScript challenge, so a plain HTTP client
gets a 403. Every `refresh_minutes` (default 60) the app:

1. loads `https://www.curzon.com/` in headless Chrome (`google-chrome
   --headless --dump-dom`, with a normal user agent: Cloudflare blocks
   `HeadlessChrome`) and reads the `authToken` from the page config. The token
   is valid for about 12 hours, so Chrome only runs when it is near expiry;
2. calls Vista's OCAPI at `https://digital-api.curzon.com/ocapi/v1` with that
   bearer token: `sites`, `film-screening-dates`, then
   `showtimes/by-business-date/<date>` for each date (which also returns the
   films, cast, genres, ratings and screens);
3. keeps the result in memory and in `cache/listings.json`, so a restart shows
   listings at once. A failed scrape keeps the old listings and retries in 10
   minutes.

## Running

Needs Python 3.10+ and Google Chrome or Chromium (`CURZON_CHROME` to point at
a specific binary).

```sh
make venv
make run        # flask dev server, http://127.0.0.1:5000
make scrape     # one scrape from the command line, to check it still works
make check      # compile + render the main routes
```

The first scrape takes about a minute after start-up.

## Pages

| URL | |
|---|---|
| `/?when=today\|tomorrow\|weekend\|week\|all&by=film\|cinema&site=SOH1&site=...` | listings |
| `/film/<film id>` | film details and all showings |
| `/listings.txt` | the same as text, same parameters |
| `/listings.json` | the raw scraped data |
| `/health` | last scrape status; 503 if no data or stale |

## Config

`curzon_config.ini` (or `$CURZON_CONFIG`): which cinemas to scrape, refresh
interval, venue notes and a films-seen list. It is re-read on every request,
so edits apply without a restart. `$CURZON_CACHE` moves the cache file.

## Deployment

On the server, in `/home/imiell/git/curzon-listings`:

```sh
git pull
make install          # venv + systemd unit curzon_listings (gunicorn, 127.0.0.1:6752)
make status           # systemd state + /health
```

Then add `deploy/nginx-location.conf` to the ianmiell.com nginx site in place
of the old static `/curzon-listings` directory, `sudo nginx -t && sudo
systemctl reload nginx`, and delete `/etc/cron.d/curzon-listings`: the old
populate and query scripts are gone. `cat_listings.sh` (used by the
`curzon-listings` webhook) now prints `/listings.txt` from the running app.
