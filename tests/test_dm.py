"""`/dm <person> <message>` from the Telegram General topic starts a new 1:1
Teams chat via teams-cli `send` (which resolves the name/email and refuses an
uncertain match). Non-/dm text in General is ignored."""
import pytest


def _dm_calls(bridge):
    return [a for a in bridge._calls["teams_do"] if a and a[0] == "send"]


def _replies(bridge):
    return [kw["text"] for m, kw in bridge._calls["tg"] if m == "sendMessage"]


def test_non_dm_text_ignored(bridge):
    assert bridge.handle_dm_command("just chatting in general") is False
    assert _dm_calls(bridge) == [] and _replies(bridge) == []


def test_dm_sends_via_teams(bridge):
    handled = bridge.handle_dm_command("/dm bob@x.com hello there")
    assert handled is True
    calls = _dm_calls(bridge)
    assert len(calls) == 1
    # send <query> -y -- <message>  (message after -- so a leading '-' is safe)
    assert calls[0] == ("send", "bob@x.com", "-y", "--", "hello there")
    assert any("Sent to bob@x.com" in r for r in _replies(bridge))


def test_dm_message_keeps_spaces(bridge):
    bridge.handle_dm_command("/dm Alice can you review this by 5pm?")
    q, msg = _dm_calls(bridge)[0][1], _dm_calls(bridge)[0][4]
    assert q == "Alice"
    assert msg == "can you review this by 5pm?"


def test_to_alias_works(bridge):
    assert bridge.handle_dm_command("/to bob hi") is True
    assert _dm_calls(bridge)[0][1] == "bob"


def test_missing_message_shows_usage(bridge):
    assert bridge.handle_dm_command("/dm bob") is True
    assert _dm_calls(bridge) == []                       # nothing sent
    assert any("Usage:" in r for r in _replies(bridge))


def test_send_failure_relayed(bridge, monkeypatch):
    def boom(*a):
        raise RuntimeError("No exact match for 'bob'. Best match: Bobby (b@x)")
    monkeypatch.setattr(bridge, "teams_do", boom)
    bridge.handle_dm_command("/dm bob hi")
    assert any("Couldn't send" in r and "bob" in r for r in _replies(bridge))


def test_case_insensitive_prefix(bridge):
    assert bridge.handle_dm_command("/DM bob hi") is True
    assert _dm_calls(bridge)[0][1] == "bob"
