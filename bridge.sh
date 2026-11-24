#!/usr/bin/env bash
# Start the HackerAI local bridge for this project.
#
# What this does: runs `npx @hackerai/local` with your bridge token so HackerAI can
# work on the machine this script runs on. It is a remote-control bridge, NOT an
# inference API key — it cannot generate Shorts ideas for the app. For that you need
# an `sk-` key from https://hackerai.sh/pricing saved in Config or HACKER_AI_API_KEY.
#
# The token is read from the environment, or from .env in this directory. It is never
# written into the repository, never echoed, and never passed on a command line that
# other local users can read via `ps`.
#
# Usage:
#   ./bridge.sh              # start the bridge
#   ./bridge.sh --help       # pass flags through to the CLI
#   ./bridge.sh --verbose    # anything after the script name is forwarded
set -euo pipefail
cd "$(dirname "$0")"

# Load .env without exporting secrets into the shell history.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

TOKEN="${HACKERAI_BRIDGE_TOKEN:-}"

if [ -z "$TOKEN" ]; then
  cat >&2 <<'MSG'
No bridge token found.

Add this line to .env (it is git-ignored):

    HACKERAI_BRIDGE_TOKEN=hsb_your_token_here

Or export it for one run:

    HACKERAI_BRIDGE_TOKEN=hsb_... ./bridge.sh

Get a bridge token from your HackerAI account. A bridge token starts with "hsb_".
MSG
  exit 1
fi

case "$TOKEN" in
  hsb_*) ;;
  sk_*|sk-*)
    echo "That looks like an inference key (sk-...), not a bridge token." >&2
    echo "Bridge tokens start with hsb_. Use the sk- key in Config instead." >&2
    exit 1
    ;;
  *)
    echo "Warning: the token does not start with 'hsb_'. Continuing anyway." >&2
    ;;
esac

if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required but was not found. Install Node.js 18 or newer." >&2
  exit 1
fi

echo "Starting HackerAI local bridge for $(pwd)"
echo "Token ending ${TOKEN: -4} · press Ctrl+C to stop."

# The token is passed as an argument because the CLI expects it there. It is not
# printed by this script.
#
# The CLI names the connection after the hostname by default (e.g. "e2b.local"),
# which is hard to recognise in a list. Set HACKERAI_BRIDGE_NAME to pick the name
# HackerAI shows in "select this computer".
if [ -n "${HACKERAI_BRIDGE_NAME:-}" ]; then
  exec npx --yes @hackerai/local@latest --token "$TOKEN" --name "$HACKERAI_BRIDGE_NAME" "$@"
fi

exec npx --yes @hackerai/local@latest --token "$TOKEN" "$@"
