"""Scrape Curzon cinema listings from curzon.com.

curzon.com sits behind a Cloudflare JavaScript challenge, so a plain HTTP
client can't load it. A headless Chrome loads one page, which passes the
challenge and contains the site config, including a bearer token (``authToken``,
valid for about 12 hours) for Vista's OCAPI at ``digital-api.curzon.com``.
That API is not behind the challenge, so everything else is plain JSON over
``requests``.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests

log = logging.getLogger(__name__)

SITE_URL = "https://www.curzon.com"
API_URL = "https://digital-api.curzon.com/ocapi/v1"
# Headless Chrome announces itself as "HeadlessChrome", which Cloudflare blocks.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
TOKEN_RE = re.compile(r'"authToken"\s*:\s*"([A-Za-z0-9._-]+)"')
API_URL_RE = re.compile(r'"apiUrl"\s*:\s*"(https://[^"]+)"')
CHROME_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
# Fetch a new token when the current one has less than this many seconds left.
TOKEN_MARGIN = 30 * 60


class ScrapeError(RuntimeError):
    """curzon.com or its API didn't give us what we expected."""


def find_chrome() -> str:
    """Return the Chrome binary: ``$CURZON_CHROME``, else the first on ``PATH``."""
    configured = os.environ.get("CURZON_CHROME")
    if configured:
        return configured
    for name in CHROME_NAMES:
        path = shutil.which(name)
        if path:
            return path
    raise ScrapeError("no Chrome found; install google-chrome or set CURZON_CHROME")


def dump_page(url: str, timeout: int = 120) -> str:
    """Load ``url`` in headless Chrome and return the rendered DOM.

    ``--virtual-time-budget`` gives the Cloudflare challenge time to run and
    reload the page before Chrome dumps it.
    """
    with tempfile.TemporaryDirectory(prefix="curzon-chrome-", ignore_cleanup_errors=True) as profile:
        cmd = [
            find_chrome(),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            f"--user-data-dir={profile}",
            f"--user-agent={USER_AGENT}",
            "--virtual-time-budget=20000",
            "--dump-dom",
            url,
        ]
        if os.environ.get("CURZON_CHROME_NO_SANDBOX") == "1":
            cmd.insert(1, "--no-sandbox")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise ScrapeError(f"Chrome timed out after {timeout}s loading {url}") from exc
    if result.returncode != 0 and not result.stdout:
        raise ScrapeError(f"Chrome exited {result.returncode}: {result.stderr[-500:]}")
    return result.stdout


def jwt_expiry(token: str) -> float:
    """Return the ``exp`` claim of a JWT as a Unix time (0 if unreadable)."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return float(claims["exp"])
    except (IndexError, KeyError, ValueError):
        return 0.0


class CurzonClient:
    """OCAPI client that fetches and renews its own bearer token."""

    def __init__(self) -> None:
        self.api_url = API_URL
        self._token: str | None = None
        self._token_expires = 0.0
        self._lock = threading.Lock()
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": USER_AGENT, "Origin": SITE_URL, "Accept": "application/json"}
        )

    def token(self, force: bool = False) -> str:
        """Return a usable bearer token, scraping a new one if needed."""
        with self._lock:
            if force or not self._token or time.time() > self._token_expires - TOKEN_MARGIN:
                started = time.monotonic()
                html = dump_page(SITE_URL + "/")
                match = TOKEN_RE.search(html)
                if not match:
                    title = re.search(r"<title>([^<]*)", html)
                    raise ScrapeError(
                        "no authToken in curzon.com page (title: "
                        f"{title.group(1) if title else 'none'!r}); "
                        "Cloudflare may be blocking headless Chrome"
                    )
                self._token = match.group(1)
                self._token_expires = jwt_expiry(self._token) or time.time() + 3600
                api = API_URL_RE.search(html)
                if api:
                    self.api_url = api.group(1).rstrip("/") + "/ocapi/v1"
                log.info(
                    "new Curzon token in %.0fs, expires %s",
                    time.monotonic() - started,
                    datetime.fromtimestamp(self._token_expires).isoformat(timespec="minutes"),
                )
            return self._token

    def get(self, path: str, params: Any = None) -> dict:
        """GET an OCAPI path, renewing the token once on a 401."""
        for attempt in (1, 2):
            response = self.session.get(
                f"{self.api_url}/{path}",
                params=params,
                headers={"Authorization": f"Bearer {self.token(force=attempt == 2)}"},
                timeout=30,
            )
            if response.status_code != 401:
                break
        if not response.ok:
            raise ScrapeError(f"{path}: HTTP {response.status_code} {response.text[:200]}")
        return response.json()


def text(value: Any) -> str:
    """Unwrap OCAPI's ``{"text": ..., "translations": [...]}`` strings."""
    if isinstance(value, dict):
        return value.get("text") or ""
    return value or ""


def slugify(title: str) -> str:
    """Make the slug curzon.com uses in film URLs."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower().replace("&", "and")).strip("-")


def fetch_sites(client: CurzonClient) -> dict[str, str]:
    """Return every Curzon site as ``{site_id: name}``."""
    return {s["id"]: text(s["name"]) for s in client.get("sites")["sites"]}


def fetch_listings(client: CurzonClient, site_ids: list[str]) -> dict:
    """Fetch every upcoming showtime at ``site_ids``.

    Returns a JSON-serialisable dict with ``sites``, ``films`` (keyed by film
    ID), ``showtimes`` (sorted by start) and ``fetched_at``.
    """
    all_sites = fetch_sites(client)
    unknown = [s for s in site_ids if s not in all_sites]
    if unknown:
        log.warning("unknown Curzon site IDs ignored: %s", ", ".join(unknown))
    site_ids = [s for s in site_ids if s in all_sites]
    if not site_ids:
        raise ScrapeError("none of the configured site IDs exist")
    # OCAPI wants siteIds repeated, not comma-joined.
    params = [("siteIds", s) for s in site_ids]

    dates = sorted(
        d["businessDate"]
        for d in client.get("film-screening-dates", params)["filmScreeningDates"]
    )
    films: dict[str, dict] = {}
    showtimes: dict[str, dict] = {}
    for business_date in dates:
        data = client.get(f"showtimes/by-business-date/{business_date}", params)
        related = data.get("relatedData", {})
        people = {
            p["id"]: " ".join(
                n.strip()
                for n in (p["name"].get("givenName"), p["name"].get("familyName"))
                if n and n.strip()
            )
            for p in related.get("castAndCrew", [])
        }
        genres = {g["id"]: text(g["name"]) for g in related.get("genres", [])}
        ratings = {r["id"]: text(r["classification"]) for r in related.get("censorRatings", [])}
        screens = {s["id"]: text(s["name"]) for s in related.get("screens", [])}
        attributes = {a["id"]: text(a.get("shortName") or a["name"]) for a in related.get("attributes", [])}
        events = {e["id"]: text(e.get("name")) for e in related.get("events", [])}

        for film in related.get("films", []):
            if film["id"] in films:
                continue
            title = text(film["title"])
            films[film["id"]] = {
                "id": film["id"],
                "title": title,
                "synopsis": text(film.get("synopsis")),
                "short_synopsis": text(film.get("shortSynopsis")),
                "runtime": film.get("runtimeInMinutes"),
                "release_date": film.get("releaseDate"),
                "rating": ratings.get(film.get("censorRatingId"), ""),
                "rating_note": text(film.get("censorRatingNote")),
                "genres": [genres[g] for g in film.get("genreIds", []) if g in genres],
                "directors": [
                    people[d["castAndCrewMemberId"]]
                    for d in film.get("directors", [])
                    if d["castAndCrewMemberId"] in people
                ],
                "cast": [
                    people[a["castAndCrewMemberId"]]
                    for a in film.get("actors", [])
                    if a["castAndCrewMemberId"] in people
                ],
                "trailer": film.get("trailerUrl"),
                "url": f"{SITE_URL}/films/{slugify(title)}/{film['id']}/",
            }

        for show in data.get("showtimes", []):
            if show["siteId"] not in site_ids:
                continue
            showtimes[show["id"]] = {
                "id": show["id"],
                "film_id": show["filmId"],
                "site_id": show["siteId"],
                "starts_at": show["schedule"]["startsAt"],
                "film_starts_at": show["schedule"].get("filmStartsAt"),
                "ends_at": show["schedule"].get("endsAt"),
                "screen": screens.get(show.get("screenId"), ""),
                "sold_out": bool(show.get("isSoldOut")),
                "tags": [attributes[a] for a in show.get("attributeIds", []) if a in attributes]
                + ([events[show["eventId"]]] if show.get("eventId") in events else []),
                "booking_url": f"{SITE_URL}/ticketing/seats/{show['id']}/",
            }

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sites": {s: all_sites[s] for s in site_ids},
        "films": films,
        "showtimes": sorted(showtimes.values(), key=lambda s: (s["starts_at"], s["site_id"])),
    }


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sites = sys.argv[1:] or ["ALD1", "BLO1", "CAM1", "HOX1", "MAY1", "SOH1", "VIC1"]
    listings = fetch_listings(CurzonClient(), sites)
    print(
        f"{len(listings['films'])} films, {len(listings['showtimes'])} showtimes "
        f"at {', '.join(listings['sites'].values())}",
        file=sys.stderr,
    )
    json.dump(listings, sys.stdout, indent=1)
