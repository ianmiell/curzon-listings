#!/bin/bash

cd $(dirname ${BASH_SOURCE[0]})

DBFILE=curzon-showtimes.db
JSONFILE=curzon_tokens.json
TODAY="$(date +%Y-%m-%d)"
NODE="/home/imiell/.nvm/versions/node/v22.17.1/bin/node"

if [ -f "${DBFILE}" ] && [ "$(date -r "${DBFILE}" +%Y-%m-%d)" = ${TODAY} ] && [ $(($(date +%s) - $(stat -c %Y "${DBFILE}"))) -lt 1800 ]
then
  :
else
  #$NODE capture_curzon_headless.js
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
      echo $l | tr -d "'"
    done
  ) | python3 ./import_showtimes.py
  IFS="${IFS_BACKUP}"
fi

