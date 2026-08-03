#!/usr/bin/env bash
# One command for the whole compliance-lapse recovery: VNC up, re-enroll, mint,
# inject, restart, verify, VNC down.
#
#   tools/reenroll.sh           # refuses if the device is already compliant
#   tools/reenroll.sh --force   # do it anyway
#
# You still have to type the password and approve 2FA in the browser — Entra
# requires an interactive sign-in and nothing here can remove that. What this
# removes is the other ~10 steps around it, which is where the time actually went
# (see docs/incidents/2026-08-03-bridge-outage.md).
#
# The script stops and waits exactly once, at the sign-in. Everything before and
# after is automatic.
set -uo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$HERE/.env}"
INTUNE="${INTUNE:-$HOME/intune-container/target/release/intune-container}"
DISPLAY_NUM="${DISPLAY_NUM:-:99}"
VNC_PORT="${VNC_PORT:-5900}"
WEB_PORT="${WEB_PORT:-6080}"
NOVNC_DIR="${NOVNC_DIR:-/usr/share/novnc}"
SERVICE="${SERVICE:-teams-telegram-bridge}"
# The interpreter that has playwright — the same one the bridge's ExecStart uses,
# because refresh_loop spawns token_mint.py with sys.executable.
MINT_PYTHON="${MINT_PYTHON:-/home/linuxbrew/.linuxbrew/opt/python@3.14/bin/python3.14}"
# VPN-only. Never bind the VNC bridge to a public interface.
TRUSTED_IP="${TRUSTED_IP:-$(ip -4 -o addr show wt0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)}"

say() { printf '\n=== %s\n' "$*"; }
die() { printf 'reenroll: %s\n' "$*" >&2; exit 1; }

[ -x "$INTUNE" ] || die "no intune-container binary at $INTUNE"
[ -n "$TRUSTED_IP" ] || die "no VPN address on wt0 — set TRUSTED_IP=… explicitly (never a public IP)"

# ---------------------------------------------------------------- 0. is it needed
if [ "${1:-}" != "--force" ]; then
    say "Checking whether this is even necessary"
    if "$HERE/tools/compliance_check.py"; then
        echo "Device is already compliant — a re-enroll won't fix whatever is wrong."
        echo "Check the other causes first: docs/RUNBOOK-token-recovery.md"
        echo "Override with: $0 --force"
        exit 0
    fi
fi

# ------------------------------------------------------------------- 1. VNC up
# systemd-run, not `setsid … &`: a backgrounded job started from a tool shell gets
# SIGTERM when that shell exits, which is how websockify silently died the first
# time. Transient units also make teardown a one-liner.
say "Exposing display $DISPLAY_NUM over VNC on the VPN address only"
export DISPLAY="$DISPLAY_NUM"
pgrep -f "Xvfb $DISPLAY_NUM" >/dev/null || die "no Xvfb on $DISPLAY_NUM (xvfb.service?)"
pgrep -f openbox >/dev/null || systemd-run --user --unit=ttb-openbox --quiet openbox || true

if ! pgrep -x x11vnc >/dev/null; then
    # x11vnc -bg has been seen to silently not come up; start it and verify.
    x11vnc -display "$DISPLAY_NUM" -rfbport "$VNC_PORT" -nopw -localhost \
           -forever -bg -o /tmp/x11vnc.log
    sleep 2
    pgrep -x x11vnc >/dev/null || die "x11vnc did not start — see /tmp/x11vnc.log"
fi
systemctl --user is-active --quiet ttb-novnc 2>/dev/null || \
    systemd-run --user --unit=ttb-novnc --quiet \
        websockify --web="$NOVNC_DIR" "$TRUSTED_IP:$WEB_PORT" "localhost:$VNC_PORT"
sleep 2

cleanup_vnc() {
    say "Tearing down the VNC exposure"
    systemctl --user stop ttb-novnc ttb-openbox 2>/dev/null || true
    pkill -x x11vnc 2>/dev/null || true
    sleep 1
    ss -ltn 2>/dev/null | grep -qE ":$VNC_PORT|:$WEB_PORT" \
        && echo "WARNING: $VNC_PORT/$WEB_PORT still listening — check by hand" \
        || echo "$VNC_PORT/$WEB_PORT closed."
}
trap cleanup_vnc EXIT

# --------------------------------------------------------------- 2. the one wait
cat <<EOF

  ┌──────────────────────────────────────────────────────────────────┐
     Open:  http://$TRUSTED_IP:$WEB_PORT/vnc.html   -> Connect (no password)

     Wait for the "Intune Agent" window (up to ~30s), click Sign in,
     enter the password, approve 2FA, wait for "Compliant",
     then CLOSE the window. This script continues by itself.

     The window may land partly off-screen — drag its titlebar up.
     If the portal itself shows "cannot access this resource" AFTER
     sign-in, ignore it: that's a different CA policy on the portal,
     not a failure. The token mint below is the real verdict.
  └──────────────────────────────────────────────────────────────────┘
EOF

say "Running enrollment (blocks until you close the portal window)"
DISPLAY="$DISPLAY_NUM" "$INTUNE" enroll -v || die "enroll failed"

say "Starting background browser SSO"
"$INTUNE" start >/dev/null || die "intune-container start failed"

# ------------------------------------------------------------------ 3. the verdict
say "Minting tokens — this is the real test, not doctor (takes ~2.5 min)"
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
cd "$HERE" || die "cannot cd $HERE"
if ! DISPLAY="$DISPLAY_NUM" "$MINT_PYTHON" token_mint.py 2>&1 | tail -20; then
    die "token mint failed — the enrollment did not restore compliance"
fi
[ -s "$HOME/ic3.jwt" ] || die "no ~/ic3.jwt after minting"

say "Injecting the token into teams-cli"
teams login --with-token --region "${TEAMS_REGION:?set TEAMS_REGION in .env}" \
    < "$HOME/ic3.jwt" || die "teams login failed"
teams auth-status --check | grep -Eq '"valid" *: *true' \
    || die "auth-status still reports invalid"
echo "auth-status: valid"

# --------------------------------------------------------------- 4. back in service
say "Restarting the bridge"
rm -f "$HOME/.cache/teams-bridge/watchdog.down"   # let the watchdog re-alert if still broken
systemctl --user restart "$SERVICE"
sleep 10
[ "$(systemctl --user is-active "$SERVICE")" = active ] || die "$SERVICE did not come back"

before=$(stat -c %Y "$HOME/.cache/teams-bridge/state.json" 2>/dev/null || echo 0)
sleep 30
after=$(stat -c %Y "$HOME/.cache/teams-bridge/state.json" 2>/dev/null || echo 0)
[ "$after" -gt "$before" ] || die "state.json is not advancing — the poll is wedged"
echo "state.json is advancing: the poll is alive."

say "Confirming compliance from Entra's side"
"$HERE/tools/compliance_check.py" || true

cat <<'EOF'

Done. The bridge is mirroring again.

Note: the 10-day-old backlog is NOT mirrored — the bridge primes on start
(post=False) so it doesn't flood Telegram. Those messages are still in Teams.
EOF
