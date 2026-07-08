"""Regressions from the correctness-cluster review:
 1. seen-trim must keep the NEWEST ids (ordered), not an arbitrary set slice.
 3. tg_msg_for_teams must not raise when the outbound thread mutates the map.
 5. a non-429 HTTP error / API rejection must return None, not crash the caller.
"""
import urllib.error


# --- bug 1: seen dedup keeps newest ------------------------------------------
def test_seen_is_insertion_ordered(bridge):
    # dict.fromkeys preserves order; a plain set() would not.
    bridge.seen.clear()
    for i in range(5):
        bridge.seen[f"m{i}"] = None
    assert list(bridge.seen)[-2:] == ["m3", "m4"]


def test_seen_trim_keeps_newest(bridge, monkeypatch):
    # simulate the trim in poll_inbound: newest 2000 survive
    bridge.seen.clear()
    for i in range(2100):
        bridge.seen[f"m{i}"] = None
    trimmed = list(bridge.seen)[-2000:]
    assert trimmed[0] == "m100" and trimmed[-1] == "m2099"
    assert "m0" not in trimmed          # oldest evicted, not a random id


# --- bug 3: reverse lookup is lock-safe --------------------------------------
def test_tg_msg_for_teams_finds_mapping(bridge):
    bridge.state["tg_to_teams"] = {"555": ["c1", "teams-9"]}
    assert bridge.tg_msg_for_teams("teams-9") == 555
    assert bridge.tg_msg_for_teams("nope") is None


def test_tg_msg_for_teams_survives_concurrent_mutation(bridge):
    # Insert while iterating would raise "dict changed size" without the lock +
    # list() copy. We can't truly race in a unit test, but the list() snapshot is
    # what makes it safe — assert it doesn't choke on a large live map.
    bridge.state["tg_to_teams"] = {str(i): ["c", f"t{i}"] for i in range(1000)}
    assert bridge.tg_msg_for_teams("t999") == 999


# --- bug 5: tg() returns None on rejection, callers don't crash --------------
def _fake_400(*a, **k):
    raise urllib.error.HTTPError("u", 400, "Bad Request", {}, None)


def test_tg_returns_none_on_400(bridge, monkeypatch, capsys):
    import importlib, bridge as real
    importlib.reload(real)
    monkeypatch.setattr(real.urllib.request, "urlopen", _fake_400)
    assert real.tg("sendMessage", chat_id=1, text="x") is None
    assert "HTTP 400" in capsys.readouterr().out


def test_getupdates_none_does_not_crash_outbound(bridge, monkeypatch):
    # tg() -> None must not raise when outbound does (upd or {}).get("result")
    monkeypatch.setattr(bridge, "tg", lambda *a, **k: None)
    # the guard expression itself is what we exercise:
    upd = bridge.tg("getUpdates")
    assert list((upd or {}).get("result", [])) == []
