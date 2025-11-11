Script to get today's film times from the curzon website

Requires webhook package

sudo tee /opt/webhook/hooks.json >/dev/null <<'JSON'
[
  {
    "id": "run-job",
    "execute-command": "/opt/webhook/curzon-listings.sh",
    "command-working-directory": "/opt/webhook"
  }
]
JSON
