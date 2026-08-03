# Incident 2026-08-03 — bridge silently down for 10 days (compliance lapse)

Running log of the outage: what was observed, what was ruled out, what was done.
Times are UTC. Written live during recovery.

Related: [RUNBOOK-token-recovery.md](../RUNBOOK-token-recovery.md) (the procedure
this incident follows), and the prior incident of the same class (2026-07-15).

---

## Timeline

| When (UTC) | Event |
|---|---|
| 2026-07-22 22:05 | Last successful token mint (`~/ic3.jwt`, `~/graph.jwt` mtime). |
| 2026-07-23 22:00:22 | Last write to `~/.cache/teams-bridge/state.json` — **bridge stops mirroring here**. |
| 2026-07-23 22:05:26 | `ic3` token expiry. |
| 2026-07-23 22:10:01 | `~/.cache/teams-bridge/watchdog.down` marker created. Nothing acted on it. |
| 2026-07-24 10:11:21 | systemd service (re)started — ran for 10d 8h "active" but unable to auth. |
| 2026-07-28 09:58:54 | `/tmp/x11vnc.log` shows a prior VNC session ended (earlier recovery attempt; did not hold). |
| 2026-08-03 11:56 | Reported as "disconnected". Investigation starts. |
| 2026-08-03 12:30 | VNC screencast up, bridge service stopped, re-enrollment started. |
| 2026-08-03 12:35:41 | Portal reports device **Compliant** after human sign-in + 2FA. |
| 2026-08-03 12:38:15 | `enroll` finishes `✓ Done` (exit 0). |
| 2026-08-03 12:41:07 | Fresh `ic3` + `graph` minted silently — **fix confirmed**. |
| 2026-08-03 12:41:37 | Bridge restarted; `[in] primed`, `state.json` advancing. |

## Symptoms observed

Everything matched the runbook's "Fast triage" row-for-row:

```
$ systemctl --user is-active teams-telegram-bridge
active                        # misleading — process alive, cannot auth

$ teams auth-status --check
"ic3": { "expires_at": "2026-07-23T22:05:26+00:00",
         "expires_in_human": "253h 51m 26s ago",
         "valid": false }

$ ls -l ~/ic3.jwt
-rw------- ... 2026-07-22 22:05  ~/ic3.jwt        # 12 days stale

$ intune-container doctor
✓ Registration  ✓ Container  ✓ Network  ✓ Identity broker  ✓ Keyring  ✓ Compliance agent
                              # all green — the documented trap
```

Log (`/tmp/bridge-systemd.log`, 2.6 MB):

```
[in] teams ('chats', '-n', '40'): Opening Teams... Log in and wait for the app to fully load.
[auth] FAILED (#4637): token mint failed: AOz_BQD...&mscrid=019fc778-13fe-75e5-afa2-036943788cd5
localStorage keys sample: []
  url=https://login.microsoftonline.com/common/oauth2/v2 have=[]
```

**4637** consecutive failed mint attempts. Each one launches a headless
Chromium. Process was at **1.0 GB RSS (peak 1.4 GB), 1d 16h CPU** after 10 days
of this.

## Ruled out

Deliberately re-verified the layer below, because the 2026-07-15 incident *was* a
broker-level PRT expiry (`invalid_grant` / `token_expired`) and looks identical
from the log.

1. **Broker is healthy; the PRT SSO cookie still issues.** Driving
   `native-host`'s `acquirePrtSsoCookie` by hand (same call `token_mint.py`
   makes) returns a real cookie:

   ```
   ACCOUNT   clement.bosle@sia-partners.com / realm af1bbf3d-...
   cookieItems len=1
   cookieName = 'x-ms-RefreshTokenCredential'
   cookieContent len=2653   header: {"alg":"HS256","ctx":"...","kid":"session"}
   ```
   → **not** the Jul-15 failure mode. No `token_expired`, no `invalid_grant`.

2. **Header injection name is correct.** The broker's item keys are
   `['cookieContent', 'cookieName']` — note `cookieName`, not `name`.
   `token_mint.py:37` reads `c.get("name", "x-ms-RefreshTokenCredential")`, so it
   falls through to the hardcoded default, which happens to equal the value the
   broker actually returns. Wrong key, right result — see "Follow-ups".

3. **The mint gets further than the log implies.** Ran `_probe2.py` (injects the
   cookie, dumps URL + localStorage key count every 10s):

   ```
   [0] url=https://teams.microsoft.com/v2/  lskeys=9
   [3] url=https://teams.microsoft.com/v2/  lskeys=16
   [4..7] url=https://teams.microsoft.com/v2/  lskeys=19
   [8] <navigating>
   [9]  url=https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_  lskeys=0
   [10] url=https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_  lskeys=0
   [11] url=https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_  lskeys=0
   ```

   Teams web loads and builds 19 localStorage keys, then at ~85s bounces to
   `/authorize` and **stalls there, blank body, zero localStorage**, until the
   30-cycle timeout.

## Diagnosis

Valid PRT cookie + correct injection + Entra refusing to complete silent sign-in
= **device compliance lapsed**, Conditional Access rejecting the compliant-device
check. Exactly the runbook's root cause. `doctor` cannot see it because it checks
enrollment/broker/keyring, never live Entra compliance.

## Actions taken

1. **VNC screencast of display `:99`** (Xvfb already running as PID 828,
   `1280x800x24`):

   ```sh
   openbox &                                            # PID 3065611
   x11vnc -display :99 -rfbport 5900 -nopw -localhost -forever -bg -o /tmp/x11vnc.log
   websockify --web=/usr/share/novnc 100.82.25.208:6080 localhost:5900
   ```
   - `5900` bound to **localhost only**; `6080` bound to **100.82.25.208** (the
     NetBird VPN address on `wt0`) — never a public interface. Verified:
     `LISTEN 127.0.0.1:5900`, `LISTEN 100.82.25.208:6080`,
     `GET /vnc.html → 200`.
   - Gotcha hit again, as the runbook warns: the first `x11vnc -bg` silently did
     not come up (`pgrep` empty); a second invocation took (`PORT=5900`). Always
     confirm `pgrep x11vnc` before starting websockify.
   - Second gotcha, new: `setsid websockify ... &` from a tool-run shell gets
     SIGTERM when that shell exits (`WebSockifyServer.Terminate` in
     `/tmp/novnc.log`). Must be launched genuinely detached.
   - Access URL: `http://100.82.25.208:6080/vnc.html` → Connect, no password.

2. **Stopped the bridge service** for the duration — 4637 failing mints/10 days
   meant a Chromium launch every poll, competing for CPU and hammering Entra
   during the re-enroll. `systemctl --user stop teams-telegram-bridge` →
   `inactive`. The runbook restarts it in step 5 regardless.

3. **Re-enrollment** — see below.

## Re-enrollment

```sh
DISPLAY=:99 ~/intune-container/target/release/intune-container enroll -v
```

- `12:32:53` — container restarted with the host display attached; Xauthority
  generated at `/run/user/1002/intune-container-xauth` (none existed).
- `12:33:04` — `Sign in and enroll in the window, then close it to finish...`,
  `intune-portal` PID 750856 painting on `:99`.
- Window landed at x≈616,y≈147 on a 1280x800 display, so its lower edge sat
  off-screen. openbox was running, so it could be dragged. Verified the window
  was actually painted with `DISPLAY=:99 scrot` rather than trusting `pgrep` —
  worth doing before handing the VNC URL over.
- Human signed in + 2FA. Portal then showed the device page: **`✓ Compliant` —
  "This device meets your organization's device and security requirements"**,
  `Last checked: 08/03/26 12:35:41`. (No "restricted by your admin" page this
  time.)
- `enroll` blocks on `intune-portal` exiting and the window doesn't self-close;
  `pkill -x intune-portal` finished it. `12:38:15` →
  `✓ Done. Start background browser SSO with: intune-container start`, exit 0.

```sh
~/intune-container/target/release/intune-container start   # ok
intune-container doctor                                    # all ✓ (proves nothing)
```

## Verification

**1. Token mint — the only check that means anything.**

```
$ DISPLAY=:99 python3.14 token_mint.py
[13..27] url=https://teams.cloud.microsoft/?loginHint=clement.b have=[]
[28] captured graph aud=https://graph.microsoft.com
[28] captured ic3   aud=https://ic3.teams.office.com
IC3_TOKEN_OK   len 2186 aud= https://ic3.teams.office.com
GRAPH_TOKEN_OK len 3502 aud= https://graph.microsoft.com
```

Fix confirmed by the URL, not just the tokens: the trace **never bounces to
`login.microsoftonline.com`** — it settles on
`teams.cloud.microsoft/?loginHint=…`, i.e. silent SSO recognized the account.
Exactly the healthy shape the runbook describes.

**2. Inject + verify.**

```
$ cat ~/ic3.jwt | teams login --with-token --region emea
Logged in successfully. Tokens cached.   Region: emea   Tokens: ic3 + 0/4 optional

$ teams auth-status --check
"ic3": { "expires_at": "2026-08-04T12:41:07+00:00",
         "expires_in_human": "23h 59m 46s", "valid": true }

$ teams chats -n 3 --json
{ "ok": true, ... "topic": "📣 Alerting 📣", "last_message_time": "2026-08-03T12:36:58..." }
```

`auth-status` reporting `"graph": false` right after this is **expected, not a
regression** — `teams login --with-token` only takes ic3. The bridge injects
graph itself, reading `~/graph.jwt` into the bundle at `bridge.py:353-355`.

**3. Restart + liveness.**

```
$ rm -f ~/.cache/teams-bridge/watchdog.down
$ systemctl --user restart teams-telegram-bridge     # ActiveEnterTimestamp 12:41:37
$ tail /tmp/bridge-systemd.log
[in] primed

state.json  12:41:50 → 12:42:11 → 12:42:32 → 12:43:03     # advancing each ~21s poll
auth] FAILED count frozen at 4645                          # zero new failures since restart
```

**4. VNC torn down.** `websockify` and `x11vnc` killed; `ss -ltn` confirms
`5900/6080 closed`. (`pkill -f x11vnc` exited 144 — the pattern matched the
tool's own shell. Kill it by PID.)

**Status: bridge healthy, mirroring again.** ic3 valid until
**2026-08-04 12:41 UTC**; `refresh_loop` re-mints from here on its own, which is
what the re-enroll restored.

### Not verified

Inbound polling is proven (state advancing, `primed`, real chats read). The
**Telegram → Teams** direction was not exercised — it can only be triggered by a
human sending from Telegram. No test message was sent to any Teams chat.

## Why nobody noticed for 10 days

This is the part worth keeping. **Both alert paths worked correctly.** Neither
was broken, and neither helped.

1. **In-process** — `bridge.py:367` `_auth_alert()`, fires after
   `AUTH_ALERT_AFTER = 3` consecutive mint failures. `fails` reached **4637**, so
   it fired; the log has **zero** `[auth] alert send failed` lines, so Telegram
   accepted it.
2. **External** — `tools/watchdog.sh` on `watchdog.timer`. `journalctl` shows it
   exiting `1` every 5 min for the whole outage and `0` since recovery. Detection
   was correct on run one; that's what created `watchdog.down` at 22:10.

Delivery was fine too — re-tested the exact notify path afterwards:
`sendMessage → {"ok":true}`, msg id 2600, chat `-1003924499345`.

So: two correct alerts were sent around Jul 23–24, both **one-shot**, both into
the **General** topic, and both missed. Then, by design, permanent silence:

```sh
if [ ! -f "$LATCH" ]; then      # first bad run this outage -> alert once
    notify "🔴 ..."
    touch "$LATCH"              # every later run: latch exists -> say nothing
fi
```

**Lesson: a one-shot alert is a single point of failure with a human in it.** The
health checks were never the weak link — the notification policy was. Worse, the
old `notify()` discarded curl's output entirely and latched *unconditionally*, so
a send that failed for any reason produced the same permanent silence with no
trace.

### Fix applied — `tools/watchdog.sh`

Kept all three health checks (they were right); changed only when it speaks.

- **Nags while down.** Alerts immediately, then repeats every `BEAT_BAD_SEC`
  (default 6h) until fixed. Missing one message no longer costs 10 days.
- **Heartbeat while up.** Every `BEAT_OK_SEC` (default 24h), sends
  `🟢 Teams bridge up — last poll Ns ago, token expires in 23h 5m`. Silence now
  means *the watchdog itself is dead*, which is information; before, silence was
  ambiguous. The token-expiry figure is the number that predicts the next outage.
- **`notify()` verifies delivery** — checks for `"ok":true`, returns non-zero
  otherwise, logs the response to stderr.
- **Latch only on confirmed send.** A failed alert retries next run instead of
  latching into silence.

Tuning is env-only, in `watchdog.service`: `BEAT_OK_SEC` / `BEAT_BAD_SEC`.

Covered by `tests/test_watchdog.py` — 7 tests, `curl`/`teams`/`systemctl` stubbed
on `PATH`, no network. Notably `test_failed_send_does_not_latch` (the silent-death
bug) and `test_down_alerts_then_nags_until_fixed`. Full suite: 192 passed.

Live-verified against the real bridge and real Telegram: `BEAT_OK_SEC=0` →
delivered the 🟢 ping and touched `watchdog.beat` (only touched on confirmed
send); immediate re-run inside the window stayed quiet.

## Borrowed from teams-lite

[theophile-wallez/teams-lite](https://github.com/theophile-wallez/teams-lite) is
another unofficial Linux Teams client built on the same `intune-container`
broker, shared by its author. Its ops documentation is unusually good and covers
failure modes this project hadn't characterized. Adopted with permission; ideas
and protocol facts, no code copied.

### Taken

1. **Ask Entra for device compliance directly** → `tools/compliance_check.py`.
   The broker mints a device-bound **Graph** token silently even when Teams
   scopes are refused; its `deviceid` claim identifies the device; Graph reports
   the device object's live `isCompliant`. Verified here: `HTTP 200`,
   `isCompliant: true`, `displayName: localhost.localdomain`.

   This is the single most valuable thing in the whole incident. Compliance
   flips the moment it lapses, while the token already in hand stays valid for up
   to 24h — so this check would have fired around 2026-07-22 22:00, a full day
   *before* mirroring stopped, instead of us finding out 10 days later. Approach
   is also visible in `intune-container`'s own doctor ("Device status" block,
   `native_host.rs:333-420`), which computes it but doesn't alert on it.

2. **The container keyring re-locks on its own** (~18h on their host). The broker
   then drops off the bus and every token call dies with
   `NoReply: Message recipient disconnected` — indistinguishable from a
   compliance lapse, and it sends you to the wrong runbook. Now a distinct
   watchdog check via a one-shot `busctl get-property` on the login collection's
   `Locked` property (verified readable here: `b false`).

   With the crucial gotcha: the fix is `stop` **then** `start`. A bare `start` on
   a running container short-circuits and never re-runs the session setup that
   unlocks the keyring.

3. **Name the broker's refusal instead of dumping the envelope** →
   `token_mint.refusal()`. Their `classify_refusal` treats exactly four codes as
   "a human must sign in" — `interaction_required`, `interactive_required`,
   `token_expired`, `invalid_grant` — and leaves everything else unnamed rather
   than claiming a remedy it doesn't have. Adopted verbatim as a policy. A mint
   that says *why* it failed is the difference between today's dozen probes and
   one line of log.

4. **"Never alarm on ignorance."** Their repair unit skips on an unknown keyring
   state rather than restarting a container on a guess. Applied to both new
   checks: the compliance probe's exit 2 (Graph 403/404, no broker, no network)
   is deliberately ignored by the watchdog.

Also fixed in passing, because the refactor touched it: `prt_cookie()` now reads
the broker's actual key, `cookieName` (follow-up 3 below).

### Deliberately not taken

- **Broker-minted Graph as the bridge's Graph token.** It works, but its scopes
  are *narrower* than the token Teams web caches — missing `People.Read`,
  `Files.ReadWrite.All`, `Sites.ReadWrite.All`. Swapping would silently break
  user search and uploads. It's used only for the compliance probe, which needs
  nothing but `deviceid`.
- **The `.path` unit watching `rootless.json`** for a new container leader. Their
  backend is long-lived and caches a `/proc/<pid>/root/...` bus address that goes
  stale when the container restarts. We're immune by construction: `token_mint`
  spawns `intune-container native-host` fresh on every refresh, so the bus is
  re-resolved each time. Worth knowing we're immune, and why.
- **An automatic keyring repair unit** (their `stop`/`start` oneshot with
  `ExecCondition`, 3/hour rate limit). We have never observed the lock on this
  host. Detection plus a named fix in the alert is enough; the unit is ~20 lines
  away if it ever fires. Their notes on it are worth re-reading first: `StartLimit*`
  belongs in `[Unit]` — a copy under `[Service]` is silently ignored — and
  `ExecCondition` reads exit 0 as "run" and 1-254 as "skip".
- **Realtime socket, SQLite cache, TUI/web UI, mail and calendar.** A different
  product. Our polling loop works and is a fraction of the surface.

### Negative result: the broker still won't mint ic3

Worth recording so nobody re-runs this spike. teams-lite's `src/auth.rs`
acquires Teams tokens straight from the broker with
`authorizationType: 1` (CACHED_REFRESH_TOKEN), which would let us delete the
entire Playwright path — no Chromium, no 150s mint, no 28-of-30-cycle margin.

It does not work on this tenant. Swept 2026-08-03 via
`intune-container`'s own `INTUNE_CLIENT_ID` override:

| client + scope | result |
|---|---|
| Office `d3590ed6…` + `ic3.teams.office.com/Teams.AccessAsUser.All` | AAD `invalid_request` / `IncorrectConfiguration` |
| Office + `ic3.teams.office.com/.default` | same |
| Teams `1fec8e78…` + `ic3…/Teams.AccessAsUser.All` | same |
| Office + `api.spaces.skype.com/.default` | same |
| Edge `d7b530a4…` (default) + ic3 | same |
| **Graph `/.default`** (control) | **works**, ~1s, `deviceid` present |

`auth_flow: PRT` on every failure, so the PRT was used and AAD rejected the
request configuration. The mechanism is fine; these scopes are refused. So
`token_mint.py`'s "won't mint ic3 directly" holds — it is not a
wrong-parameters artifact.

**How to reopen it:** AAD hides the reason behind `description: '(pii)'`. A
tenant admin can read the real error in the Entra sign-in logs by correlation id
`8d04308d-ff08-45f4-939a-fbce924caf32`. If it turns out to be missing admin
consent for the client on the ic3 scope, that's a tenant-side grant and the
Playwright path can go.

## Follow-ups worth doing (not part of this recovery)

1. **No backoff on mint failure.** 4637 attempts over 10 days, one Chromium each,
   1.0 GB RSS. Should back off exponentially instead of spinning silently. The
   *alerting* half of this is now covered by the watchdog nag above; the wasted
   CPU/memory is not.
2. ~~The watchdog alerted once and then went quiet for 10 days.~~ **Fixed** — see
   "Fix applied" above.
3. ~~`token_mint.py:37` reads the wrong key (`name` vs the broker's
   `cookieName`).~~ **Fixed** — covered by
   `tests/test_broker.py::test_prt_cookie_reads_the_brokers_key_name`.
4. **The mint barely fits its own timeout.** Even on a *healthy* device the
   tokens appeared at cycle **28 of 30** (~145s of a ~150s budget) — two cycles
   of margin. A slow poll or a slightly slower Teams load turns a working setup
   into a "mint failed" that looks identical to a compliance lapse. Raise the
   loop bound.
5. **Compliance lapse is recurring** (2026-07-15, ~2026-07-28 attempt,
   2026-08-03). Whatever interval Intune re-evaluates on, it outlives the PRT.
   Worth measuring how long a fresh enroll actually holds, and scheduling a
   re-enroll reminder inside that window.
