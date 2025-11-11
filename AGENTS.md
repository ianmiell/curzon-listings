# Repository Guidelines

## Project Structure & Module Organization
- `curzon-listings.sh` holds the curl + jq pipeline that fetches and formats showtimes; treat it as the single source of logic.
- `Makefile` currently exposes the `install` target, copying the script into `/opt/webhook` with proper permissions.
- `README.md` documents the webhook hook JSON snippet; update it whenever deployment details change.
- No nested modules or assets exist yet—create new directories (e.g., `scripts/` or `docs/`) when functionality grows to keep the root tidy.

## Build, Test, and Development Commands
- `bash curzon-listings.sh` runs the fetcher locally; expect a pipe-separated list like `SOH1|10:30|Film Title`.
- `make install` installs the script into `/opt/webhook`; requires sudo and is the preferred deployment path.
- `jq` is mandatory; verify it is installed via `jq --version` before hacking on the pipeline.

## Coding Style & Naming Conventions
- Shell scripts use Bash, 2-space indentation, and `set -euo pipefail` when adding new scripts.
- Prefer descriptive variable names (`site_id`, `titleById`) and keep curl headers alphabetized to simplify diffs.
- When adding helper functions, prefix them with the script name (e.g., `curzon_format_time`) to avoid clashes.

## Testing Guidelines
- There is no automated suite; validate changes by running `bash curzon-listings.sh` for at least one real date and ensure output stays stable.
- When modifying the JSON parsing, capture the raw response (`curl … > tmp/showtimes.json`) and test `jq -r -f parser.jq tmp/showtimes.json`.
- For production sanity checks, compare the deployed output against `https://www.curzon.com` listings after every change.

## Commit & Pull Request Guidelines
- Existing history favors short, imperative messages (`latest`, `add debug`); follow the pattern `area: action`, e.g., `script: add date flag`.
- Reference related issues in the body using `Refs #ID` or `Fixes #ID`.
- Pull requests should list: summary, manual test evidence (sample command output), and deployment considerations (e.g., need to rerun `make install`).

## Security & Configuration Notes
- Never commit live bearer tokens; source them from environment variables and inject via `Authorization: Bearer "$CURZON_TOKEN"`.
- `/opt/webhook` ownership can block installs; coordinate with ops before changing permissions or running `sudo chown`.
