#!/bin/bash

cd $(dirname ${BASH_SOURCE[0]})

DBFILE=curzon-showtimes.db

(
echo "BY FILM"
/home/linuxbrew/.linuxbrew/bin/sqlite3 "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
   f.title || char(10) || group_concat('  ' || starts_at || ' | ' || l.code, char(10)) AS out
   FROM film_showtime fs
   JOIN film f ON f.title = fs.film_title
   JOIN location l ON l.code = fs.location_code
   GROUP BY f.title
   ORDER BY f.title, fs.starts_at;" | column -t -s '|'

echo "BY CINEMA"
/home/linuxbrew/.linuxbrew/bin/sqlite3 "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
   l.code || char(10) || group_concat('  ' || f.title || ' | ' || fs.starts_at, char(10)) AS out
   FROM film_showtime fs
   JOIN film     f ON f.title = fs.film_title
   JOIN location l ON l.code  = fs.location_code
   GROUP BY l.code
   ORDER BY l.code, min(fs.starts_at);" | column -t -s '|'
) > curzon_listings.txt
