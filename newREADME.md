```
npm init -y
npm install puppeteer@latest
```


node capture_curzon_headless.js
out=$(cat curzon_tokens.json| jq -r '.bearerTokens[] | select(.key == "VistaOmnichannelComponents::browsing-domain-store") | .value' | jq -r '  . as $doc  | ($doc.filmsById      | to_entries      |
    map(select(.value.loadingState == "Success")             | {key: .key,
    value: .value.payload.title.text})      | from_entries) as $titleById
    | $doc.showtimesById  | to_entries  | map(select(.value.loadingState
    == "Success")        | .value.payload        | {location: .siteId,
    starts_at: .schedule.startsAt, film_id: .filmId})  |
    sort_by(.location, .starts_at)  | .[]  | . as $show  | ($show.starts_at
    | (.[0:-3] + .[-2:])      | strptime("%Y-%m-%dT%H:%M:%S%z")      |
    strftime("%H:%M")) as $time  | ($titleById[$show.film_id] // $show.film_id)
    as $title  | "\($time)|\($title)|\($show.location);"')
