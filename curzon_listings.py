#!/usr/bin/env python3
import argparse
import csv
import json
import logging
import re
import sys
from collections.abc import Iterator
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

BASE = "https://www.curzon.com"
VENUES_INDEX = "https://www.curzon.com/venues/all-london-cinemas/"

HDRS = {
    # A polite, explicit UA helps avoid being blocked by generic bot rules.
    "User-Agent": "Mozilla/5.0 (compatible; CurzonScraper/1.0; +https://example.org)",
    "Accept-Language": "en-GB,en;q=0.7",
}

NAME_KEYS = {"name", "title", "label", "text"}
VENUE_PATH_RE = re.compile(r"^/venues/[^/]+$")


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # urllib3 is chatty when DEBUG; keep it quieter.
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_today_iso_london() -> str:
    tz = ZoneInfo("Europe/London")
    today = datetime.now(tz).strftime("%Y-%m-%d")
    logging.debug("Resolved London date: %s", today)
    return today

def get_soup(url: str) -> BeautifulSoup:
    logging.debug("Fetching %s", url)
    r = requests.get(url, headers=HDRS, timeout=20)
    r.raise_for_status()
    logging.debug("Fetched %s (%d bytes)", url, len(r.text))
    return BeautifulSoup(r.text, "html.parser")


def _slice_window_json_blob(script_text: str, var_name: str) -> str | None:
    marker = f"window.{var_name}"
    idx = script_text.find(marker)
    if idx == -1:
        return None
    idx = script_text.find("=", idx)
    if idx == -1:
        return None
    idx += 1
    length = len(script_text)
    while idx < length and script_text[idx].isspace():
        idx += 1
    if idx >= length:
        return None
    bracket = script_text[idx]
    pairs = {"{": "}", "[": "]"}
    closing = pairs.get(bracket)
    if not closing:
        return None
    stack = [closing]
    in_string = False
    escaped = False
    for pos in range(idx + 1, length):
        ch = script_text[pos]
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch in pairs:
            stack.append(pairs[ch])
            continue
        if ch in ("]", "}"):
            if not stack or ch != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return script_text[idx:pos + 1]
    return None


def load_page_data(soup: BeautifulSoup) -> dict | None:
    var_name = "pageData"
    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        if not text or f"window.{var_name}" not in text:
            continue
        blob = _slice_window_json_blob(text, var_name)
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError as exc:
            logging.debug("Failed to parse window.%s JSON: %s", var_name, exc)
            continue
        logging.debug("Parsed window.%s payload (%d chars)", var_name, len(blob))
        return data
    logging.debug("window.%s payload not found in page scripts", var_name)
    return None


def looks_like_venue_url(url: str) -> bool:
    if not isinstance(url, str) or not url:
        return False
    try:
        full = urljoin(BASE, url)
    except Exception:
        return False
    path = urlparse(full).path.rstrip("/")
    if not path:
        path = "/"
    return bool(VENUE_PATH_RE.fullmatch(path))


def normalise_venue_url(url: str) -> str:
    full = urljoin(BASE, url)
    parsed = urlparse(full)
    clean = parsed._replace(query="", fragment="")
    final = urlunparse(clean)
    if not final.endswith("/"):
        final += "/"
    return final


def derive_venue_name(url: str, provided: str | None) -> str:
    if provided:
        return provided.strip()
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    if not slug:
        return url
    return slug.replace("-", " ").title()


def iter_page_data_venues(node) -> Iterator[tuple[str | None, str]]:
    if isinstance(node, dict):
        url_value = None
        name_value = None
        for key, value in node.items():
            if isinstance(value, str):
                if looks_like_venue_url(value):
                    url_value = value
                elif key.lower() in NAME_KEYS:
                    stripped = value.strip()
                    if stripped:
                        name_value = stripped
            else:
                yield from iter_page_data_venues(value)
        if url_value:
            yield (name_value, url_value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_page_data_venues(item)

def add_or_replace_query(url: str, **params) -> str:
    """Return url with given query params added/replaced."""
    parts = list(urlparse(url))
    q = dict(parse_qsl(parts[4], keep_blank_values=True))
    q.update({k: v for k, v in params.items() if v is not None})
    parts[4] = urlencode(q, doseq=True)
    return urlunparse(parts)

def extract_venue_links_from_dom(soup: BeautifulSoup) -> list[tuple[str, str]]:
    links = []
    for a in soup.select("a[href]"):
        href = a.get("href")
        if not href:
            continue
        if not looks_like_venue_url(href):
            continue
        url = normalise_venue_url(href)
        name = a.get_text(strip=True) or derive_venue_name(url, None)
        links.append((name, url))
    seen = set()
    out = []
    for name, url in links:
        if url not in seen:
            out.append((name, url))
            seen.add(url)
    logging.info("DOM fallback found %d unique venues", len(out))
    return out


def extract_venue_links(index_url: str) -> list[tuple[str, str]]:
    """
    Return list of (venue_name, venue_url) from the London venues index using
    the structured window.pageData payload before falling back to DOM parsing.
    """
    soup = get_soup(index_url)
    page_data = load_page_data(soup)
    if page_data:
        seen = set()
        venues = []
        raw_hits = 0
        for candidate_name, candidate_url in iter_page_data_venues(page_data):
            raw_hits += 1
            if not candidate_url or not looks_like_venue_url(candidate_url):
                continue
            url = normalise_venue_url(candidate_url)
            if url in seen:
                continue
            seen.add(url)
            venues.append((derive_venue_name(url, candidate_name), url))
        if venues:
            logging.info(
                "Found %d unique venues via window.pageData (raw matches: %d)",
                len(venues),
                raw_hits,
            )
            return venues
        logging.warning(
            "window.pageData parsed but yielded no /venues/ links; falling back to DOM"
        )
    else:
        logging.warning("window.pageData not found; falling back to DOM parsing")
    return extract_venue_links_from_dom(soup)

def clean_title(text: str) -> str:
    # Remove common runtime / certification fragments if they’re in the link text
    text = re.sub(r"\s*\|\s*.*$", "", text.strip())  # split on pipes if present
    text = re.sub(r"\s*·\s*.*$", "", text)          # split on bullets like "· 2h 10m"
    # Trim excessive whitespace
    return re.sub(r"\s+", " ", text).strip()

def extract_films_from_venue(venue_url: str, today_iso: str) -> list[str]:
    """
    Try with ?date=today first (many sites support it). If that fails or returns empty,
    fall back to the raw page (which often defaults to today's listings).
    """
    candidates = []

    def harvest(soup: BeautifulSoup):
        titles = set()

        # Strategy 1: any <a> pointing to /films/<slug>
        for a in soup.select('a[href*="/films/"]'):
            t = clean_title(a.get_text(strip=True))
            if len(t) >= 2 and not t.lower().startswith(("book", "trailer", "more")):
                titles.add(t)

        # Strategy 2: headings near showtime blocks (fallback)
        if not titles:
            for h in soup.find_all(["h2", "h3", "h4"]):
                t = clean_title(h.get_text(strip=True))
                if 2 <= len(t) <= 120 and not re.search(r"what'?s on|today|tomorrow|showtimes", t, re.I):
                    # Look ahead for time-like patterns near this heading
                    sib_text = " ".join(s.get_text(" ", strip=True) for s in h.find_all_next(limit=3))
                    if re.search(r"\b([01]?\d|2[0-3]):[0-5]\d\b", sib_text):
                        titles.add(t)

        return sorted(titles)

    # Attempt with ?date=today
    dated_url = add_or_replace_query(venue_url, date=today_iso)
    try:
        logging.debug("Harvesting %s with ?date=%s", venue_url, today_iso)
        films = harvest(get_soup(dated_url))
        if films:
            return films
        logging.debug("No films via dated URL for %s, trying plain page", venue_url)
    except Exception as exc:
        logging.warning("Dated fetch failed for %s: %s", venue_url, exc, exc_info=logging.getLogger().isEnabledFor(logging.DEBUG))

    # Plain page (often defaults to today)
    try:
        logging.debug("Harvesting %s without date parameter", venue_url)
        films = harvest(get_soup(venue_url))
        logging.debug("Found %d films at %s", len(films), venue_url)
        return films
    except Exception as exc:
        logging.error("Failed to harvest films for %s: %s", venue_url, exc, exc_info=logging.getLogger().isEnabledFor(logging.DEBUG))
        return []

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Curzon venue listings for today.")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose logging to stderr.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    configure_logging(args.debug)
    logging.info("Starting Curzon listings scrape (debug=%s)", args.debug)

    today_iso = get_today_iso_london()
    venues = extract_venue_links(VENUES_INDEX)
    if not venues:
        logging.error("No venues parsed from %s", VENUES_INDEX)
        print("No venues found on index page.", file=sys.stderr)
        sys.exit(2)

    results = []
    for venue_name, venue_url in venues:
        films = extract_films_from_venue(venue_url, today_iso)
        results.append({
            "venue": venue_name,
            "url": venue_url,
            "date": today_iso,
            "films": films,
        })
        logging.info("Processed %s (%d films)", venue_name, len(films))

    # Print a concise, readable summary
    for r in results:
        print(f"\n=== {r['venue']} — {r['date']} ===")
        if r["films"]:
            for f in r["films"]:
                print(f" - {f}")
        else:
            print(" (no films found / venue may be closed today)")

    # Also write CSV with one row per (venue, film)
    with open("curzon_today.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "venue", "film", "venue_url"])
        for r in results:
            if r["films"]:
                for film in r["films"]:
                    w.writerow([r["date"], r["venue"], film, r["url"]])
            else:
                w.writerow([r["date"], r["venue"], "", r["url"]])

    print("\nWrote curzon_today.csv")
    logging.info("CSV written with %d venue rows", len(results))

if __name__ == "__main__":
    main()
