"""refresh_loop must alert into Telegram when token minting keeps failing —
once, after a threshold — and send a recovery ping when it works again. This is
the fix for the silent multi-day auth death (see docs/RUNBOOK-token-recovery.md)."""
import pytest


class _Stop(Exception):
    pass


def _run_loop(bridge, mint_results):
    """Drive refresh_loop over a scripted sequence of refresh_token outcomes.
    Each item: None = success, an Exception instance = raise it. time.sleep is
    stubbed to raise _Stop once the script is exhausted, ending the loop."""
    seq = iter(mint_results)

    def fake_refresh():
        r = next(seq)
        if isinstance(r, Exception):
            raise r

    steps = {"n": 0}
    def fake_sleep(_):
        steps["n"] += 1
        if steps["n"] >= len(mint_results):
            raise _Stop

    bridge.refresh_token = fake_refresh
    bridge.time.sleep = fake_sleep
    try:
        bridge.refresh_loop()
    except (_Stop, StopIteration):
        pass


def _alerts(bridge):
    return [kw["text"] for m, kw in bridge._calls["tg"] if m == "sendMessage"]


def test_no_alert_below_threshold(bridge):
    # 2 failures (threshold is 3) -> no alert yet
    _run_loop(bridge, [Exception("mint failed"), Exception("mint failed")])
    assert _alerts(bridge) == []


def test_alerts_once_after_threshold(bridge):
    errs = [Exception("mint failed")] * 5
    _run_loop(bridge, errs)
    alerts = _alerts(bridge)
    # exactly one alert despite 5 failures — not one per retry
    assert len(alerts) == 1
    assert "failing" in alerts[0] and "RUNBOOK" in alerts[0]


def test_recovery_ping_after_alert(bridge):
    # 3 fails -> alert, then a success -> recovery ping
    _run_loop(bridge, [Exception("x"), Exception("x"), Exception("x"), None])
    alerts = _alerts(bridge)
    assert len(alerts) == 2
    assert "failing" in alerts[0]
    assert "recovered" in alerts[1]


def test_no_recovery_ping_without_prior_alert(bridge):
    # a single failure then success -> never alerted, so no recovery ping
    _run_loop(bridge, [Exception("x"), None])
    assert _alerts(bridge) == []
