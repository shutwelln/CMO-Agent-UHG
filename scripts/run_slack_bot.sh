#!/usr/bin/env bash
# Wrapper script for the CMO Agent Slack bot.
# Restarts automatically when the bot exits with code 42 (restart requested).
# Usage: ./scripts/run_slack_bot.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Activate virtualenv if present
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

while true; do
    echo "[$(date)] Starting CMO Agent Slack bot..."
    set +e
    cmo slack
    EXIT_CODE=$?
    set -e

    if [ "$EXIT_CODE" -eq 42 ]; then
        echo "[$(date)] Restart requested (exit 42). Restarting in 2 seconds..."
        sleep 2
    else
        echo "[$(date)] Bot exited with code $EXIT_CODE. Stopping."
        exit $EXIT_CODE
    fi
done
