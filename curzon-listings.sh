#!/bin/bash

all=$(
  for site_id in ALD1 BLO1 CAM1 HOX1 MAY1 SOH1 VIC1
  do
      output=$(curl -s "https://vwc.curzon.com/WSVistaWebClient/ocapi/v1/showtimes/by-business-date/2025-11-12?siteIds=${site_id}" -H 'accept: application/json' -H 'accept-language: en-GB,en-US;q=0.9,en;q=0.8' -H 'authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IjRBQUQ3MUYwRDI3OURBM0Y2NkMzNjJBM0JGMDRBMDFDNDBBNzU4RjciLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiIxbWpyZm13anJ3ODB4ZjM5cXgwNzcwcTUwd2M4aDdkNTYiLCJnaXZlbl9uYW1lIjoiQ3Vyem9uIiwiZmFtaWx5X25hbWUiOiJXZWIgSG9zdCIsInZpc3RhX29yZ2FuaXNhdGlvbl9jb2RlIjoiYTFiOXNqMG05ZTRtNzluN2RhdHd0MHMzdmcwIiwidG9rZW5fdXNhZ2UiOiJhY2Nlc3NfdG9rZW4iLCJqdGkiOiI1ZjFhYjYzZC01Y2I5LTQ3Y2QtOTdmYS1iMjVhOTY0ZWFjOGUiLCJhdWQiOiJhbGwiLCJhenAiOiJDdXJ6b24gQ2luZW1hcyAtIERpZ2l0YWwgV2ViIERldiAtIFBST0QiLCJuYmYiOjE3NjI4NTIzMjAsImV4cCI6MTc2Mjg5NTUyMCwiaWF0IjoxNzYyODUyMzIwLCJpc3MiOiJodHRwczovL2F1dGgubW92aWV4Y2hhbmdlLmNvbS8ifQ.T7Ziah3NIJT4z1aXrnly8bb2ChKZb_ljLqO_kI-07dd3LyHtlyBBqkyJExLYUmymkEsQ5uHE8HW9jqH4xWyhEU7J99BBQqlnvbmlmXY4ouYSd8ZlZWWy7jGd7xiLh0sQ1WvCBbwaxprOpAko7Bt-lOfVIAZgObPtUoJEfzTVZIRn8xmb5Vf8E9bVolVpBJiQDiAhFxTSK72oEr1-e0jT17ywOQPTJ_OjHhYZ-y-vpW7cWhuv3ZdigfUuh_nwMjzhi6TNJMAuwaFcGAiri6ylucU-oiDcFTBuSLuW5rc005JfpYeml4os7Wu7Dj9QgDErNluUw9T1scBRiDUonPqU5eVwMRO1-Vn3-SkXUCIEEEubUk3hYqaNDnc2tv18jRM1lyBHs0MITmLV1IGFOWQO6T5xBzOEvPdta9Wa45fH78Xc8VjI_Ve73fkeAuA8kIXKt9q4Sm-TkfNhdfOhYzwoksL8XgU0Z-6GdZELDyfoZcVCGpLDkhrardppSTdEd971SgXPuWgQiqaXsTco2cVZkSBtKZrukd3vpan6RK6zlSmwhcz6LVJLRQ1fXJiADpvQRRMSX3jkufhO5omch-vRXJ_04-t1t2M1szWVodT_SNTe4fZxKXZRuLLbtG75mI64HBto84evCH2cGsfEMpYJQBx_szeaS5sSOzoN11a4ujc' -H 'cache-control: no-cache' -H 'correlationid: OCC-1mjrfmwjrw80xf39qx0770q50wc8h7d56-kAL6T1i-uec5NWE' -H 'origin: https://www.curzon.com' -H 'pragma: no-cache' -H 'priority: u=1, i' -H 'referer: https://www.curzon.com/' -H 'sec-ch-ua: "Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"' -H 'sec-ch-ua-mobile: ?0' -H 'sec-ch-ua-platform: "macOS"' -H 'sec-fetch-dest: empty' -H 'sec-fetch-mode: cors' -H 'sec-fetch-site: same-site' -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36' | jq -r '
    . as $doc
    | ($doc.relatedData.films
       | map({key: .id, value: .title.text})
       | from_entries) as $titleById
    | $doc.showtimes
    | map({
        title: ($titleById[.filmId] // .filmId),
        time: (
          (.schedule.filmStartsAt // .schedule.startsAt) as $t
  | ($t[:-3] + $t[-2:])              # remove the ':' in the timezone
  | strptime("%Y-%m-%dT%H:%M:%S%z")
  | strftime("%H:%M")
        )
      })
    | sort_by(.title)
    | .[]
    | "\(.time)|\(.title)|XXX;"
    ')
    echo $output | sed "s/XXX/${site_id}/g"
  done
)

IFS=';'
(for a in $all
do
    echo $a | xargs
done) > curzon-showtimes

cat curzon-showtimes | python3 scripts/import_showtimes.py

