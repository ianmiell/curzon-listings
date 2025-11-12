```
npm init -y
npm install puppeteer@latest
node capture_curzon_headless.js
cat capture_curzon_headless.json| jq -r '.bearerTokens[] | select(.key == "VistaOmnichannelComponents::browsing-domain-store") | .value' | jq -r '
    (.localStorage["VistaOmnichannelComponents::browsing-domain-store"] |
  fromjson) as $store
    | ($store.filmsById | with_entries(.value = .value.payload.title.text))
  as $titles
    | $store.showtimesById
    | to_entries
    | map(.value.payload)
    | sort_by(.siteId, .schedule.startsAt)
    | .[]
    | "\(.siteId)|\(.schedule.startsAt | split("T")[1][0:5])|
  \($titles[.filmId])"
  '
```
