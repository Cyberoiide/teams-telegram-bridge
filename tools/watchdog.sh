#!/usr/bin/env bash
# External dead-man's-switch for the bridge. Runs on a systemd timer, INDEPENDENT
# of bridge.py — so it can alert when the bridge is dead (crashed, OOM, stopped,
# rebooted), which in-process alerting (refresh_loop) cannot: a dead process
# can't report its own death.
#
# Checks three health signals, pings Telegram if any is bad, and pings once more
# when everything recovers. Alerts ONCE per outage (a latch file), not every run.
#
# Install: see tools/watchdog.timer / tools/watchdog.service.
# Needs TELEGRAM_BOT_TOKEN + TELEGRAM_GROUP_ID (read from the bridge's .env).
set -u

HERE="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$HERE/.env}"
STATE_JSON="${STATE_JSON:-$HOME/.cache/teams-bridge/state.json}"
LATCH="${LATCH:-$HOME/.cache/teams-bridge/watchdog.down}"   # exists => already alerted
SERVICE="${SERVICE:-teams-telegram-bridge}"
# state.json must have been written within this many seconds (POLL_SEC is ~5s;
# allow generous slack for a slow poll / one skipped cycle).
STALE_AFTER="${STALE_AFTER:-300}"

# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
: "${TELEGRAM_BOT_TOKEN:?set TELEGRAM_BOT_TOKEN (or ENV_FILE)}"
: "${TELEGRAM_GROUP_ID:?set TELEGRAM_GROUP_ID (or ENV_FILE)}"

notify() {   # $1 = message text -> Telegram General topic
    curl -sS --max-time 20 \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_GROUP_ID}" \
        --data-urlencode "text=$1" >/dev/null 2>&1
}

problems=""

# 1) process alive?
if ! systemctl --user is-active --quiet "$SERVICE"; then
    problems="${problems}• service not active (crashed/stopped/rebooted)"$'\n'
fi

# 2) poll advancing? (alive but wedged looks active but state.json goes stale)
if [ -f "$STATE_JSON" ]; then
    now=$(date +%s); mtime=$(stat -c %Y "$STATE_JSON" 2>/dev/null || echo 0)
    age=$(( now - mtime ))
    if [ "$age" -gt "$STALE_AFTER" ]; then
        problems="${problems}• poll stalled (state.json ${age}s old, > ${STALE_AFTER}s)"$'\n'
    fi
else
    problems="${problems}• state.json missing (never primed?)"$'\n'
fi

# 3) auth still valid? (the compliance-lapse case — token silently dead)
if command -v teams >/dev/null 2>&1; then
    if ! teams auth-status --check 2>/dev/null | grep -q '"valid": true'; then
        problems="${problems}• Teams auth invalid (token expired / compliance lapse)"$'\n'
    fi
fi

if [ -n "$problems" ]; then
    if [ ! -f "$LATCH" ]; then      # first bad run this outage -> alert once
        notify "🔴 Teams bridge unhealthy:"$'\n'"${problems}"$'\n'"Fix: docs/RUNBOOK-token-recovery.md"
        mkdir -p "$(dirname "$LATCH")"; touch "$LATCH"
    fi
    exit 1
fi

# healthy — if we'd alerted, say it's back, then clear the latch
if [ -f "$LATCH" ]; then
    notify "🟢 Teams bridge recovered — healthy again."
    rm -f "$LATCH"
fi
exit 0
