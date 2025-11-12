#!/bin/bash

cd $(dirname ${BASH_SOURCE[0]})

DBFILE=curzon-showtimes.db
JSONFILE=curzon_tokens.json
TODAY="$(date +%Y-%m-%d)"

if [ -f "${DBFILE}" ] && [ "$(date -r "${DBFILE}" +%Y-%m-%d)" = ${TODAY} ] && [ $(($(date +%s) - $(stat -c %Y "${DBFILE}"))) -lt $((6*3600)) ]
then
  :
else
  node capture_curzon_headless.js
  out=$(
    cat "${JSONFILE}" | jq -r '.bearerTokens[] | select(.key == "VistaOmnichannelComponents::browsing-domain-store") | .value' | jq -r '
      . as $doc |
      (
        $doc.filmsById |
        to_entries |
        map(
          select(.value.loadingState == "Success") |
          {key: .key, value: .value.payload.title.text}
        ) |
        from_entries
      ) as $titleById |
      $doc.showtimesById |
      to_entries |
      map(
        select(.value.loadingState == "Success") |
        .value.payload |
        {location: .siteId, starts_at: .schedule.startsAt, film_id: .filmId}
      ) |
      sort_by(.location, .starts_at) |
      .[] |
      . as $show |
      (
        $show.starts_at
      ) as $time |
      ($titleById[$show.film_id] // $show.film_id) as $title |
      "\($time)|\($title)|\($show.location);"
    '
  )
  IFS_BACKUP="${IFS}"
  IFS=';'
  (
    for l in $out
    do
      echo $l | xargs
    done
  ) | python3 ./scripts/import_showtimes.py
  IFS="${IFS_BACKUP}"
fi

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
