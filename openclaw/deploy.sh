#!/bin/bash
# Deploy CMO Service Layer (companion to existing OpenClaw container)
# Usage: ./deploy.sh [start|stop|restart|status|logs|test]
#
# Prerequisites:
#   - OpenClaw container already running (openclaw-xmzf-openclaw-1)
#   - .env file in project root with API keys
#   - Docker network: openclaw-xmzf_default

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

ACTION="${1:-start}"

# Verify OpenClaw network exists
check_network() {
    if ! docker network inspect openclaw-xmzf_default &>/dev/null; then
        echo "ERROR: OpenClaw Docker network 'openclaw-xmzf_default' not found."
        echo "Is the OpenClaw container running? Check with: docker ps | grep openclaw"
        exit 1
    fi
}

case "$ACTION" in
    start)
        check_network
        echo "Starting CMO Service Layer..."
        docker compose up -d --build
        echo "Waiting for health check..."
        sleep 5
        curl -s http://localhost:8100/health | python3 -m json.tool
        echo ""
        echo "Service layer running at http://localhost:8100"
        echo "OpenClaw skills can reach it at http://cmo-service:8100"
        ;;
    stop)
        echo "Stopping CMO Service Layer..."
        docker compose down
        ;;
    restart)
        check_network
        echo "Restarting CMO Service Layer..."
        docker compose down
        docker compose up -d --build
        sleep 5
        curl -s http://localhost:8100/health | python3 -m json.tool
        ;;
    status)
        echo "=== CMO Service Layer ==="
        docker compose ps 2>/dev/null || echo "Not running"
        echo ""
        echo "=== OpenClaw Container ==="
        docker ps --filter "name=openclaw" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "Not found"
        echo ""
        echo "=== Health Check ==="
        curl -s http://localhost:8100/health | python3 -m json.tool 2>/dev/null || echo "Service not responding"
        ;;
    logs)
        docker compose logs -f --tail=50
        ;;
    test)
        echo "Testing CMO Service Layer endpoints..."
        echo ""

        echo "1. Health check:"
        curl -s http://localhost:8100/health | python3 -m json.tool
        echo ""

        echo "2. Brand voices:"
        curl -s http://localhost:8100/api/brand-voice | python3 -m json.tool
        echo ""

        echo "3. Proofread test:"
        curl -s -X POST http://localhost:8100/api/proofread \
            -H "Content-Type: application/json" \
            -d '{"text": "This is a tset of the proofreading endpont.", "context": "test"}' \
            | python3 -m json.tool
        echo ""

        echo "4. n8n workflows:"
        curl -s http://localhost:8100/api/n8n/workflows | python3 -m json.tool
        echo ""

        echo "All tests complete."
        ;;
    install-skills)
        echo "Copying skills to OpenClaw workspace..."
        OPENCLAW_DIR="/docker/openclaw-xmzf/data/.openclaw"

        # Copy workspace files
        for f in AGENTS.md SOUL.md IDENTITY.md HEARTBEAT.md USER.md TOOLS.md; do
            if [ -f "$f" ]; then
                cp "$f" "$OPENCLAW_DIR/workspace/$f"
                echo "  Copied $f"
            fi
        done

        # Copy skills
        if [ -d "skills" ]; then
            cp -r skills/* "$OPENCLAW_DIR/workspace/skills/" 2>/dev/null || \
            mkdir -p "$OPENCLAW_DIR/workspace/skills" && cp -r skills/* "$OPENCLAW_DIR/workspace/skills/"
            echo "  Copied skills/"
        fi

        # Copy cron jobs
        if [ -f "cron-jobs.json" ]; then
            cp "cron-jobs.json" "$OPENCLAW_DIR/cron/jobs.json"
            echo "  Copied cron jobs"
        fi

        echo ""
        echo "Skills installed. Restart OpenClaw to pick up changes:"
        echo "  docker restart openclaw-xmzf-openclaw-1"
        ;;
    *)
        echo "Usage: $0 [start|stop|restart|status|logs|test|install-skills]"
        exit 1
        ;;
esac
