"""tools/watchdog.sh must keep talking: nag while down, ping when recovered,
and say "still up" periodically. A single one-shot alert is exactly how the
2026-08-03 outage stayed unnoticed for 10 days (see
docs/incidents/2026-08-03-bridge-outage.md), so the repeat behaviour is the
point of the script, not a nicety.

Network is never touched — curl/teams/systemctl are stubbed on PATH.
"""
import os
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHDOG = os.path.join(ROOT, "tools", "watchdog.sh")

# curl stub: append the outgoing --data-urlencode text to $SENT, then print
# whatever Telegram is supposed to have replied ($CURL_REPLY). Alert bodies are
# multi-line, so newlines are flattened to " | " — one line in $SENT == one send.
CURL = """#!/usr/bin/env bash
for a in "$@"; do case "$a" in
    text=*) t="${a#text=}"; printf '%s\\n' "${t//$'\\n'/ | }" >> "$SENT";;
esac; done
printf '%s' "${CURL_REPLY:-{\\"ok\\":true,\\"result\\":{}}}"
"""

TEAMS = """#!/usr/bin/env bash
printf '%s' "${TEAMS_REPLY:-\\"valid\\": true, \\"expires_in_human\\": \\"23h 5m\\"}"
"""

SYSTEMCTL = """#!/usr/bin/env bash
exit ${SYSTEMCTL_RC:-0}
"""

# Stands in for tools/compliance_check.py so no test ever reaches the broker or
# Graph. 0 = compliant, 1 = not, 2 = cannot tell.
COMPLIANCE = """#!/usr/bin/env bash
printf '%s' "${COMPLIANCE_TEXT:-OK: device is compliant}"
exit ${COMPLIANCE_RC:-0}
"""


@pytest.fixture
def wd(tmp_path):
    """Run watchdog.sh against temp state, with the network stubbed out.

    Returns run(**env) -> (returncode, [messages sent]).
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("curl", CURL), ("teams", TEAMS), ("systemctl", SYSTEMCTL)):
        p = bin_dir / name
        p.write_text(body)
        p.chmod(0o755)

    compliance = bin_dir / "compliance_check.sh"
    compliance.write_text(COMPLIANCE)
    compliance.chmod(0o755)

    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=test:token\nTELEGRAM_GROUP_ID=-100999\n")

    state = tmp_path / "state.json"
    state.write_text("{}")                      # fresh mtime => poll looks alive
    sent = tmp_path / "sent.txt"
    latch = tmp_path / "watchdog.down"
    beat = tmp_path / "watchdog.beat"

    def run(**overrides):
        env = {
            "PATH": f"{bin_dir}:{os.environ.get('PATH','')}",
            "HOME": str(tmp_path),
            "ENV_FILE": str(env_file),
            "STATE_JSON": str(state),
            "LATCH": str(latch),
            "BEAT": str(beat),
            "SENT": str(sent),
            "COMPLIANCE": str(compliance),
            # no container state file => the keyring probe skips, as it must when
            # it cannot tell
            "CONTAINER_STATE": str(tmp_path / "no-such-rootless.json"),
        }
        env.update({k: str(v) for k, v in overrides.items()})
        r = subprocess.run(["bash", WATCHDOG], env=env, capture_output=True, text=True)
        msgs = sent.read_text().splitlines() if sent.exists() else []
        sent.write_text("")                     # only report this run's sends
        return r.returncode, msgs

    run.paths = {"latch": latch, "beat": beat, "state": state}
    return run


def test_healthy_is_quiet_then_beats_daily(wd):
    """A healthy bridge must not chatter every 5 min, but must confirm it's up
    once per BEAT_OK_SEC — otherwise silence can't be told from death."""
    rc, msgs = wd(BEAT_OK_SEC=86400)
    assert rc == 0
    assert len(msgs) == 1 and "up" in msgs[0]      # first run has no beat file yet

    rc, msgs = wd(BEAT_OK_SEC=86400)              # immediately after -> quiet
    assert rc == 0 and msgs == []

    rc, msgs = wd(BEAT_OK_SEC=0)                  # beat is due again
    assert rc == 0
    assert len(msgs) == 1 and "up" in msgs[0]


def test_beat_reports_token_expiry(wd):
    """The 'up' ping carries the token expiry — the number that actually
    predicts the next outage."""
    rc, msgs = wd(BEAT_OK_SEC=0)
    assert rc == 0
    assert "23h 5m" in msgs[0]


def test_down_alerts_then_nags_until_fixed(wd):
    """Down must alert at once, stay quiet for BEAT_BAD_SEC, then nag again.
    One-shot alerting is the bug this replaces."""
    rc, msgs = wd(SYSTEMCTL_RC=3, BEAT_BAD_SEC=21600)
    assert rc == 1
    assert len(msgs) == 1 and "DOWN" in msgs[0] and "service not active" in msgs[0]

    rc, msgs = wd(SYSTEMCTL_RC=3, BEAT_BAD_SEC=21600)   # too soon -> no repeat
    assert rc == 1 and msgs == []

    rc, msgs = wd(SYSTEMCTL_RC=3, BEAT_BAD_SEC=0)       # nag window elapsed
    assert rc == 1
    assert len(msgs) == 1 and "DOWN" in msgs[0]


def test_failed_send_does_not_latch(wd):
    """If Telegram rejects the alert, the next run must retry. The old version
    discarded curl output and latched regardless, so a single failed send meant
    permanent silence."""
    rc, msgs = wd(SYSTEMCTL_RC=3, CURL_REPLY='{"ok":false,"description":"nope"}')
    assert rc == 1
    assert not wd.paths["latch"].exists()          # not latched -> will retry

    rc, msgs = wd(SYSTEMCTL_RC=3)                 # send works now
    assert rc == 1
    assert len(msgs) == 1 and "DOWN" in msgs[0]
    assert wd.paths["latch"].exists()


def test_recovery_ping_after_outage(wd):
    """Down -> up must announce the recovery exactly once."""
    rc, _ = wd(SYSTEMCTL_RC=3)
    assert rc == 1 and wd.paths["latch"].exists()

    rc, msgs = wd()                               # healthy again
    assert rc == 0
    assert len(msgs) == 1 and "recovered" in msgs[0]
    assert not wd.paths["latch"].exists()

    rc, msgs = wd(BEAT_OK_SEC=86400)              # and then goes quiet
    assert rc == 0 and msgs == []


def test_stalled_poll_detected(wd):
    """The wedged-but-active case: service up, state.json frozen. This is what
    'active' hides."""
    old = time.time() - 4000
    os.utime(wd.paths["state"], (old, old))
    rc, msgs = wd(STALE_AFTER=300)
    assert rc == 1
    assert "poll stalled" in msgs[0]


def test_invalid_auth_detected(wd):
    """The compliance-lapse case: everything running, token silently dead."""
    rc, msgs = wd(TEAMS_REPLY='"valid": false')
    assert rc == 1
    assert "auth invalid" in msgs[0]


def test_non_compliant_device_alerts_before_anything_else_breaks(wd):
    """The early-warning check. Service active, poll advancing, token still
    valid — and yet we must alert, because compliance has lapsed and minting
    will fail once this token expires (~24h). Nothing else sees this window."""
    rc, msgs = wd(COMPLIANCE_RC=1,
                  COMPLIANCE_TEXT="NOT COMPLIANT: device foo is NOT compliant")
    assert rc == 1
    assert "NOT COMPLIANT" in msgs[0]
    # the other three checks were all healthy
    assert "service not active" not in msgs[0]
    assert "poll stalled" not in msgs[0]
    assert "auth invalid" not in msgs[0]


def test_compliance_unknown_never_alarms(wd):
    """Exit 2 means the probe could not tell (no broker, Graph 403, no network).
    That must stay silent — a watchdog that cries wolf on its own breakage
    trains you to ignore it."""
    rc, msgs = wd(COMPLIANCE_RC=2, COMPLIANCE_TEXT="UNKNOWN: Graph unreachable")
    assert rc == 0
    assert "DOWN" not in "".join(msgs)      # healthy verdict, no alert
    assert not wd.paths["latch"].exists()


def test_locked_keyring_names_itself(wd, tmp_path):
    """A locked container keyring must be reported as such, with its own fix.
    It otherwise presents as a generic auth failure and sends you to the
    re-enroll runbook, which does not fix it."""
    state = tmp_path / "rootless.json"
    state.write_text('{"leader": 4242, "scope": "intune-4241.scope"}')

    busctl = tmp_path / "bin" / "busctl"
    busctl.write_text("#!/usr/bin/env bash\nprintf 'b true'\n")
    busctl.chmod(0o755)

    rc, msgs = wd(CONTAINER_STATE=str(state))
    assert rc == 1
    assert "keyring LOCKED" in msgs[0]
    assert "stop && intune-container start" in msgs[0]


def test_unlocked_keyring_is_not_a_problem(wd, tmp_path):
    """The healthy keyring case, and the guard against a false positive from
    matching the wrong thing in busctl's output."""
    state = tmp_path / "rootless.json"
    state.write_text('{"leader": 4242}')

    busctl = tmp_path / "bin" / "busctl"
    busctl.write_text("#!/usr/bin/env bash\nprintf 'b false'\n")
    busctl.chmod(0o755)

    rc, msgs = wd(CONTAINER_STATE=str(state))
    assert rc == 0
    assert "keyring" not in "".join(msgs)
    assert not wd.paths["latch"].exists()
