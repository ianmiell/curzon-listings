
DBFILE=curzon-showtimes.db
node capture_curzon_headless.js
out=$(cat curzon_tokens.json| jq -r '.bearerTokens[] | select(.key == "VistaOmnichannelComponents::browsing-domain-store") | .value' | jq -r '  . as $doc  | ($doc.filmsById      | to_entries      |                                                                       map(select(.value.loadingState == "Success")             | {key: .key,                                                              value: .value.payload.title.text})      | from_entries) as $titleById
    | $doc.showtimesById  | to_entries  | map(select(.value.loadingState
        == "Success")        | .value.payload        | {location: .siteId,
            starts_at: .schedule.startsAt, film_id: .filmId})  |
                  sort_by(.location, .starts_at)  | .[]  | . as $show  | ($show.starts_at
                | (.[0:-3] + .[-2:])      | strptime("%Y-%m-%dT%H:%M:%S%z")      |
                      strftime("%H:%M")) as $time  | ($titleById[$show.film_id] // $show.film_id)
                    as $title  | "\($time)|\($title)|\($show.location);"')

IFS=';'
(
  for l in $out
  do
    echo $l | xargs
  done
) | python3 scripts/import_showtimes.py

echo "BY FILM"
/home/linuxbrew/.linuxbrew/bin/sqlite3 "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
   f.title || char(10) ||
      group_concat('  ' ||                                                                                                                              strftime('%H:%M', substr(fs.starts_at,1,19)) ||
                     ' | ' || l.code, char(10)) AS out
   FROM film_showtime fs
   JOIN film f ON f.title = fs.film_title
   JOIN location l ON l.code = fs.location_code
   GROUP BY f.title
   ORDER BY f.title, fs.starts_at;" | column -t -s '|'

echo "BY CINEMA"
/home/linuxbrew/.linuxbrew/bin/sqlite3 "${DBFILE}" -cmd ".headers off" -cmd ".mode list" "$LOCATION_CTE
SELECT
   l.code || char(10) ||
       group_concat('  ' || f.title || ' | ' ||
                      strftime('%H:%M', substr(fs.starts_at,1,19)),                                                                                       char(10)                                                                                                                           ) AS out                                                                                                              FROM film_showtime fs
   JOIN film     f ON f.title = fs.film_title
   JOIN location l ON l.code  = fs.location_code
   GROUP BY l.code
   ORDER BY l.code, min(fs.starts_at);" | column -t -s '|'
