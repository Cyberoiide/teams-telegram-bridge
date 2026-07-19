"""`/group <a>, <b> | <msg>` creates a Teams group chat via teams-cli group-chat.
Comma-separated users (names may have spaces), optional first message after `|`."""


def _grp(bridge):
    return [a for a in bridge._calls["teams_do"] if a and a[0] == "group-chat"]


def _sends(bridge):
    return [kw["text"] for m, kw in bridge._calls["tg"] if m == "sendMessage"]


def test_group_dispatched(bridge):
    assert bridge.handle_dm_command("/group a@x.com, b@y.com | hi team") is True


def test_group_two_users_with_message(bridge):
    bridge.handle_group("a@x.com, Bob Smith | let's sync")
    call = _grp(bridge)[0]
    # flags first, users after -- ; message via -m
    assert call[0] == "group-chat" and call[1] == "-y"
    assert "-m" in call and "let's sync" in call
    assert "--" in call
    after = call[call.index("--") + 1:]
    assert list(after) == ["a@x.com", "Bob Smith"]     # names with spaces preserved


def test_group_no_message(bridge):
    bridge.handle_group("a@x.com, b@y.com")
    call = _grp(bridge)[0]
    assert "-m" not in call
    assert call[call.index("--") + 1:] == ("a@x.com", "b@y.com")


def test_group_needs_two_users(bridge):
    bridge.handle_group("onlyone@x.com | hi")
    assert _grp(bridge) == []
    assert any("Usage:" in s for s in _sends(bridge))


def test_group_leading_dash_user_rejected(bridge):
    bridge.handle_group("--help, b@y.com | hi")
    assert _grp(bridge) == []
    assert any("can't start with" in s for s in _sends(bridge))


def test_group_failure_relayed(bridge, monkeypatch):
    def boom(*a):
        raise RuntimeError("No user found matching 'ghost'")
    monkeypatch.setattr(bridge, "teams_do", boom)
    bridge.handle_group("ghost, b@y.com | hi")
    assert any("Couldn't create group" in s for s in _sends(bridge))


def test_group_success_message_lists_users(bridge):
    bridge.handle_group("a@x.com, b@y.com | hi")
    assert any("a@x.com" in s and "b@y.com" in s for s in _sends(bridge))


def test_group_extra_whitespace_and_trailing_commas(bridge):
    bridge.handle_group("  a@x.com ,  b@y.com ,  | hey")
    after = _grp(bridge)[0]
    users = after[after.index("--") + 1:]
    assert list(users) == ["a@x.com", "b@y.com"]       # trimmed, empties dropped
