#!/usr/bin/env bash
# External dead-man's-switch for the bridge. Runs on a systemd timer, INDEPENDENT
# of bridge.py — so it can alert when the bridge is dead (crashed, OOM, stopped,
# rebooted), which in-process alerting (refresh_loop) cannot: a dead process
# can't report its own death.
#
# Checks three health signals and reports to Telegram: alerts when something
# breaks, NAGS every BEAT_BAD_SEC until it's fixed, pings on recovery, and sends
# a "still up" heartbeat every BEAT_OK_SEC while healthy. It deliberately keeps
# repeating — a one-shot alert is how the 2026-08-03 outage went unnoticed for 10
# days (docs/incidents/2026-08-03-bridge-outage.md). With a heartbeat, silence
# means the watchdog itself died, which is information.
#
# Install: see systemd/watchdog.timer / systemd/watchdog.service.
# Needs TELEGRAM_BOT_TOKEN + TELEGRAM_GROUP_ID (read from the bridge's .env).
set -u

HERE="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$HERE/.env}"
STATE_JSON="${STATE_JSON:-$HOME/.cache/teams-bridge/state.json}"
# Where intune-container records the running container: {"leader": <pid>, ...}.
# The leader is the container's PID 1 on the host, and its
# /proc/<pid>/root/run/user/0/bus is the bus the broker activates on.
CONTAINER_STATE="${CONTAINER_STATE:-$HOME/.local/share/intune-container/rootless.json}"
COMPLIANCE="${COMPLIANCE:-$HERE/tools/compliance_check.py}"
LATCH="${LATCH:-$HOME/.cache/teams-bridge/watchdog.down}"   # exists => already alerted
BEAT="${BEAT:-$HOME/.cache/teams-bridge/watchdog.beat}"    # mtime = last status ping
SERVICE="${SERVICE:-teams-telegram-bridge}"
# state.json must have been written within this many seconds (POLL_SEC is ~5s;
# allow generous slack for a slow poll / one skipped cycle).
STALE_AFTER="${STALE_AFTER:-300}"
# How often to re-send status. A single alert is how the 2026-08-03 outage went
# unnoticed for 10 days: both alert paths fired correctly on day 1, into the
# General topic, and were missed. Repeating makes silence itself the signal.
BEAT_OK_SEC="${BEAT_OK_SEC:-86400}"     # healthy -> "still up" once a day
BEAT_BAD_SEC="${BEAT_BAD_SEC:-21600}"   # unhealthy -> nag every 6h until fixed

# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
: "${TELEGRAM_BOT_TOKEN:?set TELEGRAM_BOT_TOKEN (or ENV_FILE)}"
: "${TELEGRAM_GROUP_ID:?set TELEGRAM_GROUP_ID (or ENV_FILE)}"

# $1 = message text -> Telegram General topic. Returns non-zero unless Telegram
# confirmed the send: the old version discarded curl's output, so a failed alert
# still latched and went silent forever.
notify() {
    resp=$(curl -sS --max-time 20 \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_GROUP_ID}" \
        --data-urlencode "text=$1" 2>&1)
    case "$resp" in
        *'"ok":true'*) return 0 ;;
    esac
    printf 'watchdog: telegram send failed: %s\n' "$resp" >&2
    return 1
}

# seconds since $1 was last touched (a huge number if it never was, so the
# first run always pings)
age_of() {
    [ -f "$1" ] || { echo 999999999; return; }
    echo $(( $(date +%s) - $(stat -c %Y "$1" 2>/dev/null || echo 0) ))
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
    # tolerate JSON spacing variants ("valid": true / "valid":true) so a
    # formatting change in teams-cli can't cause a false "auth invalid" alarm.
    if ! teams auth-status --check 2>/dev/null | grep -Eq '"valid" *: *true'; then
        problems="${problems}• Teams auth invalid (token expired / compliance lapse)"$'\n'
    fi
fi

# 4) container keyring locked? This names a cause the checks above can only
# guess at. The keyring re-locks on its own (~18h on the teams-lite author's
# host); the broker then drops off the bus and every token call dies with
# `NoReply: Message recipient disconnected`, which looks exactly like a
# compliance lapse and sends you to the wrong runbook. Repair is stop THEN
# start — a bare `start` short-circuits on a running container and never redoes
# the session setup that unlocks the keyring.
# Only a definite "true" counts: never alarm on ignorance.
leader=$(sed -n 's/.*"leader"[^0-9]*\([0-9]\{1,\}\).*/\1/p' "$CONTAINER_STATE" 2>/dev/null | head -1)
CBUS=""
if [ -n "${leader:-}" ] && command -v busctl >/dev/null 2>&1; then
    CBUS="unix:path=/proc/${leader}/root/run/user/0/bus"
fi

if [ -n "$CBUS" ]; then
    if busctl --address="$CBUS" \
        get-property org.freedesktop.secrets \
        /org/freedesktop/secrets/collection/login \
        org.freedesktop.Secret.Collection Locked 2>/dev/null | grep -q true; then
        problems="${problems}• container keyring LOCKED — broker can't mint. Fix: intune-container stop && intune-container start (a bare start won't do it)"$'\n'
    fi
fi

# 4b) is the in-container compliance agent's last run OK? It reports this device
# as compliant to Intune every hour; when it can no longer authenticate it fails
# every run and compliance drifts to non-compliant days later. This fails FIRST —
# before Entra flips isCompliant, and before the held token expires.
#
# `intune-container doctor` cannot see it: it checks only that the timer is
# scheduled, deliberately not whether the run passed (doctor.rs:141-143), which is
# why it stayed all green through the whole 10-day outage.
if [ -n "$CBUS" ]; then
    agent_result=$(busctl --address="$CBUS" get-property org.freedesktop.systemd1 \
        /org/freedesktop/systemd1/unit/intune_2dagent_2eservice \
        org.freedesktop.systemd1.Service Result 2>/dev/null)
    # Match the shape too, not just the value: only `s "..."` is systemd actually
    # answering this property. Anything else means we asked wrong or got noise,
    # and that must not alarm.
    case "$agent_result" in
        's "success"'*) ;;                      # healthy
        's "'*) problems="${problems}• Intune compliance agent last run FAILED (${agent_result#s }) — device will drift to non-compliant. If the container just restarted this may be transient; otherwise re-enroll"$'\n' ;;
        *) ;;                                   # no answer / not this property -> no opinion
    esac
fi

# 5) device still compliant in Entra? The ONLY check here that fires before
# messages stop: compliance lapses up to ~24h before the token already in hand
# expires, and nothing else notices in that window (see tools/compliance_check.py).
# Exit 2 is "cannot tell" and is deliberately ignored.
if [ -x "$COMPLIANCE" ]; then
    compliance_reason=$("$COMPLIANCE" 2>&1) && compliance_rc=0 || compliance_rc=$?
    if [ "$compliance_rc" -eq 1 ]; then
        problems="${problems}• ${compliance_reason}"$'\n'
    fi
fi

mkdir -p "$(dirname "$LATCH")"

if [ -n "$problems" ]; then
    # First bad run alerts immediately; after that, nag every BEAT_BAD_SEC until
    # it's fixed. Only mark it sent when Telegram confirmed — otherwise retry
    # next run instead of latching into silence.
    if [ ! -f "$LATCH" ] || [ "$(age_of "$BEAT")" -ge "$BEAT_BAD_SEC" ]; then
        if notify "🔴 Teams bridge DOWN:"$'\n'"${problems}"$'\n'"Fix: docs/RUNBOOK-token-recovery.md"; then
            touch "$LATCH" "$BEAT"
        fi
    fi
    exit 1
fi

# healthy — if we'd alerted, say it's back, then clear the latch
if [ -f "$LATCH" ]; then
    if notify "🟢 Teams bridge recovered — healthy again."; then
        rm -f "$LATCH"; touch "$BEAT"
    fi
    exit 0
fi

# still healthy — periodic "yes it's up" so silence is never ambiguous
if [ "$(age_of "$BEAT")" -ge "$BEAT_OK_SEC" ]; then
    exp=$(teams auth-status --check 2>/dev/null \
          | grep -o '"expires_in_human"[^,]*' | cut -d'"' -f4)
    notify "🟢 Teams bridge up — last poll ${age:-?}s ago, token expires in ${exp:-?}." \
        && touch "$BEAT"
fi
exit 0
