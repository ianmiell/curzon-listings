#!/bin/bash
# Print this week's listings as text, for the curzon-listings webhook.
# If the site has a password (CURZON_SITE_USER/PASSWORD in .env), send it.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
user=${CURZON_SITE_USER:-}
password=${CURZON_SITE_PASSWORD:-}
if [[ -z $password && -r $here/.env ]]; then
    user=$(sed -n 's/^CURZON_SITE_USER=//p' "$here/.env" | tail -1)
    password=$(sed -n 's/^CURZON_SITE_PASSWORD=//p' "$here/.env" | tail -1)
fi
url="http://127.0.0.1:${CURZON_PORT:-6752}/listings.txt?when=${1:-week}&by=${2:-film}"
if [[ -n $password ]]; then
    # Credentials go to curl on stdin, not the command line, so ps can't see them.
    printf 'user = "%s:%s"\n' "$user" "$password" | curl -fsS -K - "$url"
else
    curl -fsS "$url"
fi
