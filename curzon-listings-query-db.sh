#!/bin/bash

cd $(dirname ${BASH_SOURCE[0]})

DBFILE=curzon-showtimes.db
OUTFILE=curzon_listings.txt
LOCATION_CTE=$(cat <<'SQL'
WITH location_names(code, name) AS (
  VALUES
    ('ALD1', 'Aldgate'),
    ('BLO1', 'Bloomsbury'),
    ('CAM1', 'Camden'),
    ('HOX1', 'Hoxton'),
    ('MAY1', 'Mayfair'),
    ('SOH1', 'Soho'),
    ('VIC1', 'Victoria')
)
SQL
)

(
echo "================================="
echo "BY FILM TODAY"
echo "================================="
/home/linuxbrew/.linuxbrew/bin/sqlite3 "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
   f.title || char(10) || group_concat('  ' || strftime('%H:%M', fs.starts_at) || ' | ' || COALESCE(n.name, l.code), char(10)) AS out
   FROM film_showtime fs
   JOIN film f ON f.title = fs.film_title
   JOIN location l ON l.code = fs.location_code
   LEFT JOIN location_names n ON n.code = l.code
   WHERE date(fs.starts_at) = date('now', 'localtime')
     AND datetime(fs.starts_at) >= datetime('now', 'localtime')
   GROUP BY f.title
   ORDER BY f.title, fs.starts_at;" | column -t -s '|'

echo
echo
echo
echo "================================="
echo "BY CINEMA TODAY"
echo "================================="
/home/linuxbrew/.linuxbrew/bin/sqlite3 "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
  COALESCE(n.name, l.code) || char(10) || group_concat('  ' || f.title || ' | ' || strftime('%H:%M', fs.starts_at), char(10)) AS out
  FROM film_showtime fs
  JOIN film     f ON f.title = fs.film_title
  JOIN location l ON l.code  = fs.location_code
  LEFT JOIN location_names n ON n.code = l.code
  WHERE date(fs.starts_at) = date('now', 'localtime')
  AND datetime(fs.starts_at) >= datetime('now', 'localtime')
  GROUP BY COALESCE(n.name, l.code)
  ORDER BY COALESCE(n.name, l.code), min(fs.starts_at);" | column -t -s '|'

echo
echo
echo
echo "================================="
echo "BY CINEMA THIS WEEKEND TODO"
echo "================================="
/home/linuxbrew/.linuxbrew/bin/sqlite3 "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
   COALESCE(n.name, l.code) || char(10) || group_concat('  ' || f.title || ' | ' || strftime('%d/%m %H:%M', fs.starts_at), char(10)) AS out
   FROM film_showtime fs
   JOIN film     f ON f.title = fs.film_title
   JOIN location l ON l.code  = fs.location_code
   LEFT JOIN location_names n ON n.code = l.code
   WHERE
       datetime(fs.starts_at) >= datetime('now', 'localtime')       -- Only future showings
   AND datetime(fs.starts_at) > date('now','localtime','weekday 5') -- after next friday
   AND datetime(fs.starts_at) < date('now','localtime','weekday 1') -- before next monday
   GROUP BY COALESCE(n.name, l.code)
   ORDER BY COALESCE(n.name, l.code), min(fs.starts_at);" | column -t -s '|'

echo
echo
echo
echo "================================="
echo "BY FILM THIS WEEKEND"
echo "================================="
/home/linuxbrew/.linuxbrew/bin/sqlite3 "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
   f.title || char(10) || group_concat('  ' || strftime('%d/%m %H:%M', fs.starts_at) || ' | ' || COALESCE(n.name, l.code), char(10)) AS out
   FROM film_showtime fs
   JOIN film f ON f.title = fs.film_title
   JOIN location l ON l.code = fs.location_code
   LEFT JOIN location_names n ON n.code = l.code
   WHERE
       datetime(fs.starts_at) >= datetime('now', 'localtime')       -- Only future showings
   AND datetime(fs.starts_at) > date('now','localtime','weekday 5') -- after next friday
   AND datetime(fs.starts_at) < date('now','localtime','weekday 1') -- before next monday
   GROUP BY f.title
   ORDER BY f.title, fs.starts_at;" | column -t -s '|'

echo
echo
echo
echo "================================="
echo "BY CINEMA ALL TIME"
echo "================================="
/home/linuxbrew/.linuxbrew/bin/sqlite3 "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
   COALESCE(n.name, l.code) || char(10) || group_concat('  ' || f.title || ' | ' || strftime('%d/%m %H:%M', fs.starts_at), char(10)) AS out
   FROM film_showtime fs
   JOIN film     f ON f.title = fs.film_title
   JOIN location l ON l.code  = fs.location_code
   LEFT JOIN location_names n ON n.code = l.code
   WHERE date(fs.starts_at) > date('now', 'localtime')
   GROUP BY COALESCE(n.name, l.code)
   ORDER BY COALESCE(n.name, l.code), min(fs.starts_at);" | column -t -s '|'



echo
echo
echo
echo "================================="
echo "BY FILM ALL TIME"
echo "================================="
/home/linuxbrew/.linuxbrew/bin/sqlite3 "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
   f.title || char(10) || group_concat('  ' || strftime('%d/%m %H:%M', fs.starts_at) || ' | ' || COALESCE(n.name, l.code), char(10)) AS out
   FROM film_showtime fs
   JOIN film f ON f.title = fs.film_title
   JOIN location l ON l.code = fs.location_code
   LEFT JOIN location_names n ON n.code = l.code
   WHERE date(fs.starts_at) > date('now', 'localtime')
   GROUP BY f.title
   ORDER BY f.title, fs.starts_at;" | column -t -s '|'

echo
echo
echo
echo "================================="
echo "BY CINEMA ALL TIME"
echo "================================="
/home/linuxbrew/.linuxbrew/bin/sqlite3 "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
   COALESCE(n.name, l.code) || char(10) || group_concat('  ' || f.title || ' | ' || strftime('%d/%m %H:%M', fs.starts_at), char(10)) AS out
   FROM film_showtime fs
   JOIN film     f ON f.title = fs.film_title
   JOIN location l ON l.code  = fs.location_code
   LEFT JOIN location_names n ON n.code = l.code
   WHERE date(fs.starts_at) > date('now', 'localtime')
   GROUP BY COALESCE(n.name, l.code)
   ORDER BY COALESCE(n.name, l.code), min(fs.starts_at);" | column -t -s '|'
) > "${OUTFILE}"

# Folder needs write to be able to copy in imiell cron
#sudo chmod a+w /var/www/ianmiell.com/curzon-listings

echo "$OUTFILE written"
cp curzon_listings.txt /var/www/ianmiell.com/curzon-listings
echo "$OUTFILE copied"


