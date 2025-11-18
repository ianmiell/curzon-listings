#!/usr/bin/env python3
"""
Import the pipe-separated output from curzon-listings.sh into a SQLite database.
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import os
from pathlib import Path
from typing import Iterable, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = "curzon-showtimes.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load curzon showtimes into a SQLite database."
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help=f"Path to the SQLite database (default: {DEFAULT_DB}).",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not clear previously stored records before inserting new rows.",
    )
    return parser.parse_args()


def read_showtimes() -> List[str]:
    return [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]



def parse_line(line: str) -> Tuple[str, str, str]:
    parts = line.split("|")
    if len(parts) != 3:
        print(f"Unrecognized line format: {line!r}")
        return None
    start_time, title, location = (part.strip() for part in parts)
    if not (start_time and title and location):
        raise ValueError(f"Incomplete entry: {line!r}")
    return start_time, title, location


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS film (
            title TEXT PRIMARY KEY
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS location (
            code TEXT PRIMARY KEY
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS film_showtime (
            film_title TEXT NOT NULL,
            location_code TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            PRIMARY KEY (film_title, location_code, starts_at),
            FOREIGN KEY (film_title) REFERENCES film(title) ON DELETE CASCADE,
            FOREIGN KEY (location_code) REFERENCES location(code) ON DELETE CASCADE
        );
        """
    )


def clear_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM film_showtime;")
    conn.execute("DELETE FROM film;")
    conn.execute("DELETE FROM location;")


def insert_rows(
    conn: sqlite3.Connection, rows: Iterable[Tuple[str, str, str]]
) -> None:
    for start_time, title, location in rows:
        conn.execute("INSERT OR IGNORE INTO film(title) VALUES (?);", (title,))
        conn.execute("INSERT OR IGNORE INTO location(code) VALUES (?);", (location,))
        conn.execute(
            """
            INSERT OR REPLACE INTO film_showtime (film_title, location_code, starts_at)
            VALUES (?, ?, ?);
            """,
            (title, location, start_time),
        )


def main() -> None:
    args = parse_args()
    print("args.db =", repr(args.db))
    print("cwd    =", os.getcwd())
    print("db abs path =", Path(args.db).resolve())
    lines = read_showtimes()
    rows = [parse_line(line) for line in lines if (r := parse_line(line)) is not None]
    conn = sqlite3.connect(args.db)
    try:
        with conn:
            ensure_schema(conn)
            if not args.keep_existing:
                clear_tables(conn)
            insert_rows(conn, rows)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
