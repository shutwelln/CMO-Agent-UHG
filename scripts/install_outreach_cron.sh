#!/usr/bin/env bash
# Install / uninstall / check status of the DSDN outreach cron launchd job.
#
# Usage:
#   bash scripts/install_outreach_cron.sh              # install (default)
#   bash scripts/install_outreach_cron.sh --install
#   bash scripts/install_outreach_cron.sh --uninstall
#   bash scripts/install_outreach_cron.sh --status

set -euo pipefail

LABEL="com.cmoagent.outreach-cron"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="${SCRIPT_DIR}/com.cmoagent.outreach-cron.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

action="${1:---install}"

case "$action" in
    --install)
        if [ ! -f "$PLIST_SRC" ]; then
            echo "ERROR: Plist not found at ${PLIST_SRC}"
            exit 1
        fi

        # Ensure logs directory exists
        mkdir -p "$(dirname "$SCRIPT_DIR")/data/logs"

        # Unload first if already loaded (idempotent)
        launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true

        cp "$PLIST_SRC" "$PLIST_DST"
        launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"

        echo "Installed and loaded: ${LABEL}"
        echo "  Plist: ${PLIST_DST}"
        echo "  Runs every 4 hours while machine is awake."
        echo ""
        echo "To run immediately:  launchctl kickstart gui/$(id -u)/${LABEL}"
        echo "To check status:     bash $0 --status"
        ;;

    --uninstall)
        launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
        rm -f "$PLIST_DST"
        echo "Unloaded and removed: ${LABEL}"
        ;;

    --status)
        if launchctl print "gui/$(id -u)/${LABEL}" &>/dev/null; then
            echo "LOADED: ${LABEL}"
            launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null | head -20
        else
            echo "NOT LOADED: ${LABEL}"
            if [ -f "$PLIST_DST" ]; then
                echo "  (plist exists at ${PLIST_DST} but is not loaded)"
            fi
        fi
        ;;

    *)
        echo "Usage: $0 [--install | --uninstall | --status]"
        exit 1
        ;;
esac
