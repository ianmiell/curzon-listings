#!/bin/bash

cd $(dirname ${BASH_SOURCE[0]})

SQLITE_BIN="$(which sqlite3 || echo "/home/linuxbrew/.linuxbrew/bin/sqlite3")"

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
echo -e "=================================\nVENUE GUIDE\n================================="
echo -e "Soho:\n\tscreen 2 back is good"
echo -e "Victoria:\n\tscreen 2 back a bit cramped, front looked ok"

echo -e "=================================\nBY FILM TODAY\n================================="
$SQLITE_BIN "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
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

echo -e "=================================\nBY CINEMA TODAY\n================================="
${SQLITE_BIN} "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
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

# If it is Saturday, then just do tomorrow for the weekend
if [ "$(date +%u)" -eq 6 ]
then
   echo -e "\n\n\n=================================\nBY FILM TOMORROW\n================================="
   ${SQLITE_BIN} "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
   SELECT
      f.title || char(10) || group_concat('  ' || strftime('%d/%m %H:%M', fs.starts_at) || ' | ' || COALESCE(n.name, l.code), char(10)) AS out
      FROM film_showtime fs
      JOIN film f ON f.title = fs.film_title
      JOIN location l ON l.code = fs.location_code
      LEFT JOIN location_names n ON n.code = l.code
      WHERE
      datetime(fs.starts_at) >= datetime('now', 'localtime') -- Only future showings
      AND date(fs.starts_at) < date('now', 'localtime', 'weekday 0') -- before monday
      GROUP BY f.title
      ORDER BY f.title, fs.starts_at;" | column -t -s '|'

   echo -e "\n\n\n=================================\nBY CINEMA TOMORROW\n================================="
   ${SQLITE_BIN} "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
   SELECT
      COALESCE(n.name, l.code) || char(10) || group_concat('  ' || f.title || ' | ' || strftime('%H:%M', fs.starts_at), char(10)) AS out
      FROM film_showtime fs
      JOIN film     f ON f.title = fs.film_title
      JOIN location l ON l.code  = fs.location_code
      LEFT JOIN location_names n ON n.code = l.code
      WHERE
          datetime(fs.starts_at) >= datetime('now', 'localtime') -- Only future showings
      AND date(fs.starts_at) < date('now', 'localtime', 'weekday 0') -- before monday
      GROUP BY COALESCE(n.name, l.code)
      ORDER BY COALESCE(n.name, l.code), fs.starts_at;" | column -t -s '|'

# If it's not Saturday, ask for the weekend
elif [ "$(date +%u)" -lt 6 ]
then
   echo -e "\n\n\n=================================\nBY FILM THIS WEEKEND\n================================="
   ${SQLITE_BIN} "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
   SELECT
      f.title || char(10) || group_concat('  ' || strftime('%d/%m %H:%M', fs.starts_at) || ' | ' || COALESCE(n.name, l.code), char(10)) AS out
      FROM film_showtime fs
      JOIN film f ON f.title = fs.film_title
      JOIN location l ON l.code = fs.location_code
      LEFT JOIN location_names n ON n.code = l.code
      WHERE
         datetime(fs.starts_at) >= datetime('now', 'localtime')       -- Only future showings
      AND datetime(fs.starts_at) > date('now','localtime','weekday 5') -- after next friday
      AND datetime(fs.starts_at) < date('now','localtime','weekday 0') -- before next monday
      GROUP BY f.title
      ORDER BY f.title, fs.starts_at;" | column -t -s '|'

   echo -e "\n\n\n=================================\nBY CINEMA THIS WEEKEND\n================================="
   ${SQLITE_BIN} "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
   SELECT
      COALESCE(n.name, l.code) || char(10) || group_concat('  ' || f.title || ' | ' || strftime('%d/%m %H:%M', fs.starts_at), char(10)) AS out
      FROM film_showtime fs
      JOIN film     f ON f.title = fs.film_title
      JOIN location l ON l.code  = fs.location_code
      LEFT JOIN location_names n ON n.code = l.code
      WHERE
          datetime(fs.starts_at) >= datetime('now', 'localtime')       -- Only future showings
      AND datetime(fs.starts_at) > date('now','localtime','weekday 5') -- after next friday
      AND datetime(fs.starts_at) < date('now','localtime','weekday 0') -- before next monday
      GROUP BY COALESCE(n.name, l.code)
      ORDER BY COALESCE(n.name, l.code), min(fs.starts_at);" | column -t -s '|'
fi

echo -e "\n\n\n=================================\nBY CINEMA ALL TIME\n================================="
${SQLITE_BIN} "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
   COALESCE(n.name, l.code) || char(10) || group_concat('  ' || f.title || ' | ' || strftime('%d/%m %H:%M', fs.starts_at), char(10)) AS out
   FROM film_showtime fs
   JOIN film     f ON f.title = fs.film_title
   JOIN location l ON l.code  = fs.location_code
   LEFT JOIN location_names n ON n.code = l.code
   WHERE date(fs.starts_at) > date('now', 'localtime')
   GROUP BY COALESCE(n.name, l.code)
   ORDER BY COALESCE(n.name, l.code), min(fs.starts_at);" | column -t -s '|'

echo -e "\n\n\n=================================\nBY FILM ALL TIME\n================================="
${SQLITE_BIN} "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
   f.title || char(10) || group_concat('  ' || strftime('%d/%m %H:%M', fs.starts_at) || ' | ' || COALESCE(n.name, l.code), char(10)) AS out
   FROM film_showtime fs
   JOIN film f ON f.title = fs.film_title
   JOIN location l ON l.code = fs.location_code
   LEFT JOIN location_names n ON n.code = l.code
   WHERE date(fs.starts_at) > date('now', 'localtime')
   GROUP BY f.title
   ORDER BY f.title, fs.starts_at;" | column -t -s '|'

echo -e "\n\n\n=================================\nBY CINEMA ALL TIME\n================================="
${SQLITE_BIN} "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
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
