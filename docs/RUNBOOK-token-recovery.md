# Runbook — bridge down, tokens won't mint (compliance lapse)

The most common way this bridge dies: it stops receiving/sending because
`token_mint.py` can no longer mint an `ic3` token silently. This runbook is the
exact diagnosis + fix, from a real incident.

## Symptoms

- Telegram stops mirroring; replies don't reach Teams.
- `/tmp/bridge-systemd.log` shows the poll falling back to interactive login:
  ```
  [in] teams ('chats', '-n', '40'): Opening Teams... Log in and wait for the app to fully load.
  [auth] FAILED: token mint failed: AOz_BQD...&mscrid=...
  localStorage keys sample: []
    url=https://login.microsoftonline.com/common/oauth2/v2 have=[]
  ```
- `teams auth-status --check` → `"valid": false`.
- `~/ic3.jwt` mtime is stale (hours/days old — tokens last ~24h).

## Root cause

**Device compliance lapsed** — not enrollment, not the broker.

The chain: `intune-container` broker still issues the PRT SSO cookie, and
`intune-container doctor` reports **all green** (this is the trap — doctor
checks enrollment/broker/keyring, NOT live Entra compliance). But Intune
re-evaluates device compliance periodically; when that lapses, Entra flags the
device non-compliant and **Conditional Access rejects the PRT SSO cookie**. So:

- `token_mint.py`'s headless silent login bounces to
  `login.microsoftonline.com` with empty `localStorage` — no token captured.
- A human signing into Teams in *any* browser hits the same gate:
  > You cannot access this right now. Your sign-in was successful but does not
  > meet the criteria to access this resource… restricted by your admin.

Both failures are the same CA compliant-device check. **`doctor` green + tokens
stale + CA "restricted" error = compliance lapse.**

## Fix — one command

```sh
tools/reenroll.sh
```

It does everything below: refuses if the device is actually compliant (so you
don't re-enroll for the wrong reason), brings up the VNC screencast bound to the
VPN address, runs `enroll`, waits at the sign-in, then starts SSO, mints, injects,
restarts the bridge, checks `state.json` is advancing, re-checks compliance and
tears the VNC down.

It stops and waits **once** — at the password + 2FA, which Entra requires and
nothing here can remove. Everything either side of that is automatic.

The manual steps are kept below because they're what the script does, and when
something breaks mid-way you'll want to run them one at a time.

## Fix — re-enroll, by hand (refreshes compliance + PRT)

There is no lightweight "refresh compliance" command in the container toolkit.
The durable fix is to re-run the interactive enrollment — the same flow used for
first-time setup. It re-registers the device, refreshes compliance, and mints a
fresh PRT that silent minting can use again for weeks.

Enrollment is interactive (needs the Microsoft sign-in + 2FA in a real window),
so on a headless server you screencast the container's display over VNC.

### 1. Screencast the headless display over VNC

The bridge already uses X display `:99` (an `Xvfb` virtual display) for headless
token minting. Expose it over noVNC so you can see + click the login window.
Bind it to a **trusted interface only** (here, the NetBird VPN IP), never public.

```sh
export DISPLAY=:99
# window manager on :99 (harmless if already running)
pgrep -f openbox   >/dev/null || openbox &
# VNC server on localhost; websockify bridges it to the VPN IP for the browser
pgrep -f x11vnc    >/dev/null || x11vnc -display :99 -rfbport 5900 -nopw -localhost -forever -bg
pgrep -f websockify>/dev/null || setsid websockify --web=/usr/share/novnc \
      <TRUSTED_IP>:6080 localhost:5900 >/tmp/novnc.log 2>&1 < /dev/null &
```

Then open **`http://<TRUSTED_IP>:6080/vnc.html`** in your browser → Connect
(no password). `<TRUSTED_IP>` is the VPN address of the server (e.g. the NetBird
IP `100.82.25.208`), reachable only over the VPN.

> Gotchas hit in the real incident: `x11vnc -bg` races a `pkill`, so start it
> once and confirm `pgrep x11vnc` before launching websockify; the IPv6
> "Address already in use" line from x11vnc is harmless (it still binds IPv4).

### 2. Re-enroll in the VNC window

```sh
DISPLAY=:99 ~/intune-container/target/release/intune-container enroll -v
# log: "Opening Intune Portal — the window can take up to ~30s the first time."
# then: "Sign in and enroll in the window, then close it to finish..."
```

In the VNC tab: wait for the **Intune Company Portal** window (this is the
CA-trusted enrollment app — a plain browser is NOT trusted and gets the
"restricted" error). Sign in, approve 2FA, let it report **Compliant**, then
**close the window** — the `enroll` process waits on `intune-portal` exiting and
finishes with:
```
✓ Done. Start background browser SSO with:  intune-container start
```

> The portal may itself show the "cannot access this resource" page after
> sign-in — that's a *different* CA policy on the portal resource and does NOT
> mean the fix failed. Trust the token mint (step 4), not the portal page.
> If the window won't close on its own: `pkill -x intune-portal`.

### 3. Start background SSO

```sh
~/intune-container/target/release/intune-container start
~/intune-container/target/release/intune-container doctor   # all ✓
```

### 4. Verify the fix — mint a fresh token

This is the real test (doctor isn't).

```sh
cd ~/teams-telegram-bridge && set -a && . ./.env && set +a
DISPLAY=:99 python3 token_mint.py
#   -> IC3_TOKEN_OK   len ... aud= https://ic3.teams.office.com
#   -> GRAPH_TOKEN_OK len ... aud= https://graph.microsoft.com
```

When compliance is fixed the trace no longer bounces to
`login.microsoftonline.com`; it stays on `teams.microsoft.com` /
`teams.cloud.microsoft/?loginHint=...` (silent SSO recognized the account) and
captures both tokens within ~30 poll cycles.

### 5. Inject + restart

```sh
cat ~/ic3.jwt | teams login --with-token --region "$TEAMS_REGION"
teams auth-status --check          # "valid": true
teams chats -n 3                   # real chats -> auth works end to end

systemctl --user restart teams-telegram-bridge
systemctl --user is-active teams-telegram-bridge   # active
tail -f /tmp/bridge-systemd.log                    # [in] primed, no auth fallback
```

Confirm `state.json` mtime advances each poll:
```sh
ls -l --time-style=+%H:%M:%S ~/.cache/teams-bridge/state.json
```

### 6. Tear down VNC

Once the bridge is healthy, kill the exposed display bridge:
```sh
pkill -f websockify; pkill -f x11vnc
```

## Confirm it in one second (do this first)

The checks below all lag the real cause. This one doesn't — it asks Entra
directly whether the device is still compliant:

```sh
tools/compliance_check.py
#   OK: device <name> is compliant                  -> compliance is NOT your problem
#   NOT COMPLIANT: device <name> is NOT compliant   -> this runbook, re-enroll
#   UNKNOWN: ...                                    -> probe couldn't tell, keep reading
```

It works because the broker still mints a device-bound **Graph** token silently
even when Teams scopes are refused; that token's `deviceid` claim identifies the
device, and Graph reports the device object's live `isCompliant`. Roughly a day
of warning, because compliance flips the moment it lapses while the token already
in hand stays valid for up to 24h.

`UNKNOWN` is not a diagnosis — HTTP 403 means the tenant won't tell us, 404 means
the device hasn't synced. Neither means non-compliant.

## Not compliance? Check the keyring

Same symptoms, completely different fix. The container's login keyring re-locks
on its own (~18h on the teams-lite author's host). The broker then drops off the
bus and every token call dies with
`org.freedesktop.DBus.Error.NoReply: Message recipient disconnected` — which
reads like a compliance lapse and sends you here by mistake.

```sh
leader=$(python3 -c "import json;print(json.load(open('$HOME/.local/share/intune-container/rootless.json'))['leader'])")
busctl --address="unix:path=/proc/$leader/root/run/user/0/bus" \
    get-property org.freedesktop.secrets \
    /org/freedesktop/secrets/collection/login \
    org.freedesktop.Secret.Collection Locked
#   b false  -> unlocked, not your problem
#   b true   -> LOCKED, fix below
```

The fix is **stop then start**, not a bare start:

```sh
intune-container stop && intune-container start
```

> A bare `start` on a running container short-circuits ("container already
> running") and never re-runs the session setup that unlocks the keyring. That is
> exactly why restarting it "did nothing" the first time someone tried.

The watchdog checks both of these every 5 minutes and names whichever it finds,
so in practice the Telegram alert should tell you which of the two you're in.

## Fast triage checklist

| Check | Healthy | This failure |
|-------|---------|--------------|
| `systemctl --user is-active teams-telegram-bridge` | active | active (misleading — process runs, just can't auth) |
| `/tmp/bridge-systemd.log` | `[in] primed` | `Opening Teams... Log in` + `token mint failed` |
| `teams auth-status --check` | `"valid": true` | `"valid": false` |
| `~/ic3.jwt` mtime | < ~24h | stale (days) |
| `intune-container doctor` | all ✓ | all ✓ (does NOT catch it) |
| interactive Teams login in a browser | works | "restricted by your admin" |

**The tell:** doctor green **and** tokens stale **and** CA "restricted" → compliance lapse → re-enroll.

## Prevention (implemented)

`doctor` stays green through this, so it's a poor liveness signal. What replaced
that idea, in `tools/watchdog.sh` on a 5-minute timer:

- `teams auth-status --check` returning `"valid": false`
- `~/.cache/teams-bridge/state.json` mtime not advancing
- the service not being active
- the container keyring being locked (above)
- **device compliance in Entra** (above) — the only one that fires *before*
  messages stop

It repeats itself: re-alerts every 6h while broken, and sends a daily "still up"
heartbeat with the token expiry. That last part matters more than it sounds — the
2026-08-03 outage was detected correctly on day one by two independent alerts,
both of which sent exactly one message and were missed. See
[docs/incidents/2026-08-03-bridge-outage.md](incidents/2026-08-03-bridge-outage.md).
