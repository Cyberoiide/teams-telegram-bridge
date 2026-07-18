"""/help lists the bridge commands — works in the General topic (via
handle_dm_command) and inside a chat topic (via send_help(tid))."""


def _sends(bridge):
    return [kw for m, kw in bridge._calls["tg"] if m == "sendMessage"]


def test_help_in_general_consumed(bridge):
    assert bridge.handle_dm_command("/help") is True
    sends = _sends(bridge)
    assert len(sends) == 1
    assert "/dm" in sends[0]["text"] and "/del" in sends[0]["text"]
    assert sends[0].get("message_thread_id") is None       # General, no topic


def test_help_case_insensitive(bridge):
    assert bridge.handle_dm_command("/HELP") is True
    assert len(_sends(bridge)) == 1


def test_send_help_into_topic(bridge):
    bridge.send_help(tid=7)
    s = _sends(bridge)[0]
    assert s["message_thread_id"] == 7
    assert "/dm" in s["text"]


def test_help_text_lists_all_commands(bridge):
    # guard against a command shipping without a help entry
    for cmd in ("/dm", "/to", "/del", "/unsend", "/help"):
        assert cmd in bridge.HELP_TEXT


def test_non_help_general_text_still_ignored(bridge):
    assert bridge.handle_dm_command("hello world") is False
    assert _sends(bridge) == []


def test_register_commands_sets_menu(bridge):
    bridge.register_commands()
    calls = [kw for m, kw in bridge._calls["tg"] if m == "setMyCommands"]
    assert len(calls) == 1
    import json
    cmds = [c["command"] for c in json.loads(calls[0]["commands"])]
    assert "dm" in cmds and "help" in cmds
