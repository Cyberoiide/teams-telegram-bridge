"""`/del` replying to your own mirrored message unsends it in Teams and removes
the Telegram copy. Only your own messages (Teams enforces server-side)."""
import pytest


def _tgcalls(bridge, method):
    return [kw for m, kw in bridge._calls["tg"] if m == method]


def _reply_msg(rt_id=999):
    return {"reply_to_message": {"message_id": rt_id}}


def test_del_deletes_teams_and_telegram(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "lookup_tg_message", lambda x: ("c1", "teams-7"))
    monkeypatch.setattr(bridge, "msg_num_for_id", lambda t, m: 42)
    bridge.handle_del_command(_reply_msg(999), target=1, cid="c1", tid=5)
    # deleted in teams
    assert ("delete", "42", "-y") in bridge._calls["teams_do"]
    # deleted the telegram copy (the replied-to msg)
    dels = _tgcalls(bridge, "deleteMessage")
    assert len(dels) == 1 and dels[0]["message_id"] == 999


def test_del_without_reply_prompts(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "lookup_tg_message", lambda x: None)
    bridge.handle_del_command({}, target=1, cid="c1", tid=5)   # no reply_to_message
    assert bridge._calls["teams_do"] == []
    sent = _tgcalls(bridge, "sendMessage")
    assert any("Reply to a message you sent" in kw["text"] for kw in sent)


def test_del_unmapped_reply_prompts(bridge, monkeypatch):
    # replying to something we never mirrored -> not deletable
    monkeypatch.setattr(bridge, "lookup_tg_message", lambda x: None)
    bridge.handle_del_command(_reply_msg(123), target=1, cid="c1", tid=5)
    assert bridge._calls["teams_do"] == []


def test_del_message_not_in_teams(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "lookup_tg_message", lambda x: ("c1", "teams-7"))
    monkeypatch.setattr(bridge, "msg_num_for_id", lambda t, m: None)   # too old
    bridge.handle_del_command(_reply_msg(999), target=1, cid="c1", tid=5)
    assert bridge._calls["teams_do"] == []
    assert any("Couldn't find" in kw["text"] for kw in _tgcalls(bridge, "sendMessage"))


def test_del_failure_relayed_no_tg_delete(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "lookup_tg_message", lambda x: ("c1", "teams-7"))
    monkeypatch.setattr(bridge, "msg_num_for_id", lambda t, m: 42)
    def boom(*a):
        raise RuntimeError("delete: 403 not your message")
    monkeypatch.setattr(bridge, "teams_do", boom)
    bridge.handle_del_command(_reply_msg(999), target=1, cid="c1", tid=5)
    # teams delete failed -> must NOT delete the telegram copy (stay consistent)
    assert _tgcalls(bridge, "deleteMessage") == []
    assert any("Delete failed" in kw["text"] for kw in _tgcalls(bridge, "sendMessage"))
