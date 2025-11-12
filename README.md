Script to get today's film times from the curzon website

Requires webhook package

sudo tee /opt/webhook/hooks.json >/dev/null <<'JSON'
[
  {
    "id": "curzon-listings",
    "execute-command": "curzon-listings.sh",
    "command-working-directory": "/home/imiell/git/curzon-listings"
  }
]
JSON

## Importing showtimes into SQLite

Use `scripts/import_showtimes.py` to persist the pipe-separated output produced by `curzon-listings.sh`:

```sh
python3 scripts/import_showtimes.py --db /tmp/curzon-showtimes.db
```

- When stdin is a pipe, the script reads from it. Otherwise it executes `curzon-listings.sh` itself.
- The database schema contains `film` (title primary key), `location` (code primary key) and `film_showtime` (film/title/location triple) tables. Rows are replaced on every run unless `--keep-existing` is supplied.
- The default database path is `curzon-showtimes.db` in the repository root; override it with `--db`.


## Setup
```
npm init -y
npm install puppeteer@latest
```
