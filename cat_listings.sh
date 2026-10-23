#!/bin/bash
# Print this week's listings as text, for the curzon-listings webhook.
set -euo pipefail
curl -fsS "http://127.0.0.1:${CURZON_PORT:-6752}/listings.txt?when=${1:-week}&by=${2:-film}"
