#!/usr/bin/env python3
"""Is this device still COMPLIANT in Entra? The one signal that predicts the
bridge's #1 outage instead of reporting it late.

    tools/compliance_check.py            # 0 = compliant, 1 = NOT, 2 = cannot tell
    tools/compliance_check.py --quiet    # exit code only

WHY THIS EXISTS. When Intune compliance lapses, Conditional Access starts
rejecting the PRT SSO cookie, so `token_mint.py` can no longer mint silently.
But the bridge keeps working off the token it already holds — for up to 24h.
Everything visible stays green in that window:

  * `systemctl is-active`        -> active
  * `intune-container doctor`    -> all ✓ (it never asks Entra about compliance)
  * `teams auth-status --check`  -> "valid": true, until the token expires

So the first honest symptom is messages silently stopping a day later, which is
exactly how the 2026-08-03 outage started (compliance lapsed ~22:00, mirroring
stopped ~22:05 the next day, and nobody knew for 10 days). `isCompliant` flips
the moment compliance lapses, giving roughly a day of warning.

HOW. The broker mints a device-bound Graph token silently (~1s, no browser); its
`deviceid` claim identifies this device to Entra; Graph then reports the device
object's live compliance. Approach borrowed from the intune-container doctor's
"Device status" block and theophile-wallez/teams-lite.

Never alarms on ignorance: anything we could not determine exits 2, not 1. A
watchdog must not report a device non-compliant because a probe broke.
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import token_mint  # noqa: E402  (path set above so this works from anywhere)

GRAPH_DEVICE = ("https://graph.microsoft.com/v1.0/devices(deviceId='{{{did}}}')"
                "?$select=isCompliant,displayName")

COMPLIANT, NOT_COMPLIANT, UNKNOWN = 0, 1, 2


def check():
    """Return (exit_code, human-readable reason)."""
    try:
        tok = token_mint.broker_graph_token()
    except Exception as e:
        # Includes the broker's own refusal text when it gave one — a refusal
        # here is itself a strong hint (see token_mint.refusal).
        return UNKNOWN, f"could not get a Graph token from the broker: {e}"

    did = token_mint.jwt_claims(tok).get("deviceid")
    if not did:
        # Enrolled in Intune but not Entra-registered (Workplace Join): the token
        # isn't device-bound, so device-based CA (Teams error 53003) fails too.
        return NOT_COMPLIANT, ("Graph token has no deviceid claim — device is NOT "
                               "Entra-registered (Workplace Join). Re-enroll.")

    req = urllib.request.Request(
        GRAPH_DEVICE.format(did=did),
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            dev = json.load(r)
    except urllib.error.HTTPError as e:
        # 403 = the tenant won't tell us (permission), 404 = not synced yet.
        # Neither means non-compliant, so neither may alarm.
        return UNKNOWN, f"Graph would not answer (HTTP {e.code}) — cannot tell"
    except Exception as e:
        return UNKNOWN, f"Graph unreachable: {e}"

    if dev.get("isCompliant") is True:
        return COMPLIANT, f"device {dev.get('displayName', did)} is compliant"
    if dev.get("isCompliant") is False:
        return NOT_COMPLIANT, (f"device {dev.get('displayName', did)} is NOT compliant "
                               "— token minting will fail once the current token "
                               "expires (~24h). Re-enroll: "
                               "docs/RUNBOOK-token-recovery.md")
    return UNKNOWN, f"Graph returned no isCompliant field: {json.dumps(dev)[:120]}"


def main():
    code, reason = check()
    if "--quiet" not in sys.argv:
        label = {COMPLIANT: "OK", NOT_COMPLIANT: "NOT COMPLIANT", UNKNOWN: "UNKNOWN"}[code]
        print(f"{label}: {reason}")
    return code


if __name__ == "__main__":
    sys.exit(main())
