#!/usr/bin/env python3
import sys
import re
import csv
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

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

def get_today_iso_london() -> str:
    tz = ZoneInfo("Europe/London")
    return datetime.now(tz).strftime("%Y-%m-%d")

def get_soup(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HDRS, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def add_or_replace_query(url: str, **params) -> str:
    """Return url with given query params added/replaced."""
    parts = list(urlparse(url))
    q = dict(parse_qsl(parts[4], keep_blank_values=True))
    q.update({k: v for k, v in params.items() if v is not None})
    parts[4] = urlencode(q, doseq=True)
    return urlunparse(parts)

def extract_venue_links(index_url: str) -> list[tuple[str, str]]:
    """
    Return list of (venue_name, venue_url) from the London venues index.
    We accept only links under /venues/<slug>/
    """
    soup = get_soup(index_url)
    links = []
    for a in soup.select("a[href]"):
        href = a.get("href")
        if not href:
            continue
        abs_url = urljoin(BASE, href)
        path = urlparse(abs_url).path.rstrip("/")
        # accept /venues/<slug>
        if re.fullmatch(r"/venues/[^/]+", path):
            name = a.get_text(strip=True) or path.split("/")[-1].replace("-", " ").title()
            links.append((name, abs_url + "/"))  # normalise trailing slash
    # de-duplicate while preserving order
    seen = set()
    out = []
    for name, url in links:
        if url not in seen:
            out.append((name, url))
            seen.add(url)
    return out

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
        films = harvest(get_soup(dated_url))
        if films:
            return films
    except Exception:
        pass  # fall back to plain page

    # Plain page (often defaults to today)
    try:
        return harvest(get_soup(venue_url))
    except Exception:
        return []

def main():
    today_iso = get_today_iso_london()
    venues = extract_venue_links(VENUES_INDEX)
    if not venues:
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

if __name__ == "__main__":
    main()
