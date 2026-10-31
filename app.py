"""
Web app showing upcoming Curzon cinema listings, scraped from curzon.com.
"""
from __future__ import annotations

import configparser
import hmac
import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta
from itertools import groupby
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from curzon import CurzonClient, fetch_listings

HERE = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("CURZON_CONFIG", HERE / "curzon_config.ini"))
CACHE_PATH = Path(os.environ.get("CURZON_CACHE", HERE / "cache" / "listings.json"))
# Venue notes edited on the /notes page. Not committed; once it exists it
# replaces the [venue_notes] section of the config.
NOTES_PATH = Path(os.environ.get("CURZON_NOTES", HERE / "data" / "venue_notes.json"))
NOTE_MAX_CHARS = 500
LONDON = ZoneInfo("Europe/London")
DEFAULT_SITES = ["ALD1", "BLO1", "CAM1", "HOX1", "MAY1", "SOH1", "VIC1"]
# After a failed scrape, try again sooner than the normal refresh.
RETRY_MINUTES = 10
RANGES = {
    "today": "Today",
    "tomorrow": "Tomorrow",
    "weekend": "Weekend",
    "week": "Next 7 days",
    "all": "Everything",
}
VIEWS = {"film": "By film", "cinema": "By cinema"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("curzon-listings")

app = Flask(__name__)
# nginx serves the app under a path prefix and passes it in X-Forwarded-Prefix.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

listings: dict = {}
status = {"last_attempt": None, "last_error": None}
notes_lock = threading.Lock()


def read_config() -> configparser.ConfigParser:
    """Read the config file, re-read on every use so edits apply without a restart."""
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config


def configured_sites(config: configparser.ConfigParser) -> list[str]:
    """Return the Curzon site IDs to scrape, from ``[curzon] sites``."""
    raw = config.get("curzon", "sites", fallback="")
    return [s.strip().upper() for s in raw.split(",") if s.strip()] or DEFAULT_SITES


def refresh_minutes(config: configparser.ConfigParser) -> int:
    """Return minutes between scrapes, from ``[curzon] refresh_minutes``."""
    return max(10, config.getint("curzon", "refresh_minutes", fallback=60))


def load_cache() -> None:
    """Load the last scrape from disk so a restart shows listings straight away."""
    global listings
    try:
        listings = json.loads(CACHE_PATH.read_text())
        log.info("loaded %d showtimes from %s", len(listings.get("showtimes", [])), CACHE_PATH)
    except (OSError, ValueError) as exc:
        log.info("no usable cache at %s: %s", CACHE_PATH, exc)


def save_cache(data: dict) -> None:
    """Write the scrape to disk atomically."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(CACHE_PATH)


def venue_notes(config: configparser.ConfigParser) -> dict[str, str]:
    """Return {site ID: note}: from the notes file if it exists, else ``[venue_notes]``."""
    try:
        return {k.upper(): v for k, v in json.loads(NOTES_PATH.read_text()).items() if v}
    except FileNotFoundError:
        pass
    except (OSError, ValueError, AttributeError) as exc:
        log.warning("unreadable notes file %s: %s", NOTES_PATH, exc)
    if not config.has_section("venue_notes"):
        return {}
    return {k.upper(): v for k, v in config.items("venue_notes")}


def save_venue_notes(notes: dict[str, str]) -> None:
    """Write the venue notes file atomically."""
    NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = NOTES_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(notes, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(NOTES_PATH)


def notes_password() -> str:
    """Return the password for editing notes; empty means editing is off."""
    return os.environ.get("CURZON_NOTES_PASSWORD", "")


def authorised(password: str) -> bool:
    """True if the request carries the notes password in HTTP basic auth (any user name)."""
    auth = request.authorization
    given = (auth.password or "") if auth and auth.type == "basic" else ""
    return hmac.compare_digest(given.encode(), password.encode())


def same_origin() -> bool:
    """False if the browser says the request came from another site (a CSRF guard)."""
    if request.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
        return False
    origin = request.headers.get("Origin")
    return origin is None or origin == f"{request.scheme}://{request.host}"


def update_listings() -> None:
    """Background loop: scrape curzon.com, then sleep until the next refresh."""
    global listings
    client = CurzonClient()
    while True:
        config = read_config()
        delay = refresh_minutes(config)
        status["last_attempt"] = datetime.now(LONDON).isoformat(timespec="seconds")
        try:
            data = fetch_listings(client, configured_sites(config))
            listings = data
            save_cache(data)
            status["last_error"] = None
            log.info("%d films, %d showtimes", len(data["films"]), len(data["showtimes"]))
        except Exception as exc:  # keep the old listings on any failure
            status["last_error"] = f"{type(exc).__name__}: {exc}"
            log.exception("Error during update_listings")
            delay = min(delay, RETRY_MINUTES)
        time.sleep(delay * 60)


def date_range(when: str, today: date) -> tuple[date, date] | None:
    """Return the inclusive (first, last) dates for a range name, None for all."""
    if when == "today":
        return today, today
    if when == "tomorrow":
        return today + timedelta(days=1), today + timedelta(days=1)
    if when == "weekend":
        # Saturday and Sunday; on a weekend, what's left of this one.
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        if today.weekday() == 6:
            saturday = today - timedelta(days=1)
        return max(saturday, today), saturday + timedelta(days=1)
    if when == "week":
        return today, today + timedelta(days=6)
    return None


def upcoming_showtimes(when: str, sites: list[str]) -> list[dict]:
    """Return showtimes in the range that haven't started, with ``start`` as a London datetime."""
    now = datetime.now(LONDON)
    span = date_range(when, now.date())
    shows = []
    for show in listings.get("showtimes", []):
        start = datetime.fromisoformat(show["starts_at"]).astimezone(LONDON)
        if start < now or (sites and show["site_id"] not in sites):
            continue
        if span and not span[0] <= start.date() <= span[1]:
            continue
        shows.append({**show, "start": start})
    return shows


def by_film(shows: list[dict]) -> list[dict]:
    """Group showtimes by film (alphabetical), then by day."""
    films = listings.get("films", {})
    groups = []
    for film_id, film_shows in groupby(sorted(shows, key=lambda s: s["film_id"]), key=lambda s: s["film_id"]):
        film_shows = sorted(film_shows, key=lambda s: (s["start"], s["site_id"]))
        groups.append({
            "film": films.get(film_id, {"id": film_id, "title": film_id}),
            "days": [(day, list(day_shows)) for day, day_shows in groupby(film_shows, key=lambda s: s["start"].date())],
        })
    return sorted(groups, key=lambda g: g["film"]["title"].lower().removeprefix("the "))


def by_cinema(shows: list[dict]) -> list[dict]:
    """Group showtimes by cinema, then day, then film (in order of first showing)."""
    films = listings.get("films", {})
    sites = listings.get("sites", {})
    groups = []
    for site_id in sorted({s["site_id"] for s in shows}, key=lambda s: sites.get(s, s)):
        site_shows = sorted((s for s in shows if s["site_id"] == site_id), key=lambda s: s["start"])
        days = []
        for day, day_shows in groupby(site_shows, key=lambda s: s["start"].date()):
            day_shows = list(day_shows)
            order = list(dict.fromkeys(s["film_id"] for s in day_shows))
            days.append((day, [
                (films.get(f, {"id": f, "title": f}), [s for s in day_shows if s["film_id"] == f])
                for f in order
            ]))
        groups.append({"site_id": site_id, "name": sites.get(site_id, site_id), "days": days})
    return groups


def selection() -> tuple[str, str, list[str]]:
    """Read the range, view and cinema filter from the query string."""
    when = request.args.get("when", "today")
    view = request.args.get("by", "film")
    sites = [s for s in request.args.getlist("site") if s in listings.get("sites", {})]
    return (when if when in RANGES else "today"), (view if view in VIEWS else "film"), sites


@app.url_defaults
def add_static_version(endpoint: str, values: dict) -> None:
    """Add ?v=<mtime> to static URLs so browsers fetch changed CSS instead of a cached copy."""
    if endpoint != "static" or "filename" not in values or "v" in values:
        return
    try:
        values["v"] = int(os.stat(os.path.join(app.static_folder, values["filename"])).st_mtime)
    except OSError:
        pass


@app.template_filter("day")
def format_day(value: date) -> str:
    """Format a date as 'Today', 'Tomorrow' or 'Sat 25 Oct'."""
    today = datetime.now(LONDON).date()
    if value == today:
        return "Today"
    if value == today + timedelta(days=1):
        return "Tomorrow"
    label = value.strftime("%a %-d %b")
    return label if value.year == today.year else f"{label} {value.year}"


@app.template_filter("hhmm")
def format_time(value: datetime) -> str:
    """Format a datetime as 24-hour 'HH:MM'."""
    return value.strftime("%H:%M")


@app.context_processor
def inject_globals() -> dict:
    """Make the update status and config notes available to all templates."""
    config = read_config()
    fetched = listings.get("fetched_at")
    return {
        "fetched_at": datetime.fromisoformat(fetched).astimezone(LONDON) if fetched else None,
        "last_error": status["last_error"],
        "all_sites": listings.get("sites", {}),
        "venue_notes": venue_notes(config),
        "notes_editable": bool(notes_password()),
        "seen": [line.strip() for line in config.get("seen", "films", fallback="").splitlines() if line.strip()],
    }


@app.route("/")
def index():
    """Listings for a date range, grouped by film or by cinema."""
    when, view, sites = selection()
    shows = upcoming_showtimes(when, sites)
    if not shows and "when" not in request.args:
        # Late in the evening there's nothing left today; show tomorrow instead.
        when = "tomorrow"
        shows = upcoming_showtimes(when, sites)
    groups = by_film(shows) if view == "film" else by_cinema(shows)
    return render_template(
        "index.html", when=when, view=view, sites=sites, groups=groups,
        ranges=RANGES, views=VIEWS, count=len(shows),
    )


@app.route("/film/<film_id>")
def film(film_id: str):
    """One film: details and every upcoming showing."""
    info = listings.get("films", {}).get(film_id)
    if not info:
        abort(404)
    _, _, sites = selection()
    shows = [s for s in upcoming_showtimes("all", sites) if s["film_id"] == film_id]
    groups = by_film(shows)
    return render_template("film.html", film=info, days=groups[0]["days"] if groups else [], sites=sites)


@app.route("/listings.json")
def listings_json():
    """The raw scraped data."""
    return jsonify(listings)


@app.route("/listings.txt")
def listings_txt():
    """Plain-text listings, taking the same query parameters as the page."""
    when, view, sites = selection()
    shows = upcoming_showtimes(when, sites)
    groups = by_film(shows) if view == "film" else by_cinema(shows)
    body = render_template("listings.txt", when=when, view=view, groups=groups, ranges=RANGES)
    return Response(body, mimetype="text/plain")


@app.route("/health")
def health():
    """Update status as JSON; 503 if there are no listings or they are stale."""
    fetched = listings.get("fetched_at")
    age = (datetime.now(LONDON) - datetime.fromisoformat(fetched)).total_seconds() if fetched else None
    stale_after = 3 * refresh_minutes(read_config()) * 60
    healthy = age is not None and age < stale_after
    return jsonify(
        healthy=healthy,
        fetched_at=fetched,
        age_seconds=int(age) if age is not None else None,
        films=len(listings.get("films", {})),
        showtimes=len(listings.get("showtimes", [])),
        sites=listings.get("sites", {}),
        **status,
    ), 200 if healthy else 503


@app.route("/notes", methods=["GET", "POST"])
def edit_notes():
    """Edit the venue notes. Needs CURZON_NOTES_PASSWORD set, and given via basic auth."""
    password = notes_password()
    if not password:
        abort(404)
    if not authorised(password):
        return Response("Password needed to edit venue notes.\n", 401,
                        {"WWW-Authenticate": 'Basic realm="Curzon venue notes", charset="UTF-8"'},
                        mimetype="text/plain")
    config = read_config()
    site_ids = list(dict.fromkeys([*configured_sites(config), *listings.get("sites", {})]))
    if request.method == "POST":
        if not same_origin():
            abort(403)
        with notes_lock:
            notes = venue_notes(config)
            for site_id in site_ids + list(notes):
                field = f"note-{site_id}"
                if field not in request.form:
                    continue
                text = " ".join(request.form[field].split())[:NOTE_MAX_CHARS]
                if text:
                    notes[site_id] = text
                else:
                    notes.pop(site_id, None)
            save_venue_notes(notes)
        log.info("venue notes saved: %d cinemas have notes", len(notes))
        return redirect(url_for("edit_notes", saved=1), code=303)
    notes = venue_notes(config)
    site_ids += [s for s in notes if s not in site_ids]
    return render_template("notes.html", site_ids=site_ids, notes=notes,
                           saved="saved" in request.args, max_chars=NOTE_MAX_CHARS)


@app.errorhandler(404)
def not_found(_error):
    """Plain not-found page in the site style."""
    return render_template("404.html"), 404


load_cache()
threading.Thread(target=update_listings, name="update_listings", daemon=True).start()
