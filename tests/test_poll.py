"""poll_inbound: watermark change-detection, prime, echo-guard, self-chat."""
import pytest


def _stub_teams(bridge, monkeypatch, chats, messages):
    """messages: dict of display_num(str) -> list[msg]."""
    def fake(*args):
        if args[0] == "chats":
            return chats
        if args[0] == "chat":
            return messages.get(str(args[1]), [])
        return []
    monkeypatch.setattr(bridge, "teams", fake)
    monkeypatch.setattr(bridge, "deliver_message",
                        lambda m, tid: bridge._calls.setdefault("delivered", []).append(m["id"]))
    monkeypatch.setattr(bridge, "topic_for_chat", lambda cid, title: 1)


def test_prime_marks_seen_without_delivering(bridge, monkeypatch):
    chats = [{"id": "c1", "display_num": 1, "topic": "A", "last_message_time": "t1"}]
    _stub_teams(bridge, monkeypatch, chats, {"1": [{"id": "m1", "is_from_me": False}]})
    bridge.poll_inbound(post=False)
    # nothing delivered during prime
    assert bridge._calls.get("delivered", []) == []
    # but watermark recorded so next real poll can skip
    assert bridge.state["watermarks"]["c1"] == "t1"


def test_unchanged_chat_is_skipped(bridge, monkeypatch):
    chats = [{"id": "c1", "display_num": 1, "topic": "A", "last_message_time": "t1"}]
    opened = []
    def fake(*args):
        if args[0] == "chats":
            return chats
        if args[0] == "chat":
            opened.append(args[1]); return []
        return []
    monkeypatch.setattr(bridge, "teams", fake)
    monkeypatch.setattr(bridge, "topic_for_chat", lambda *a: 1)
    bridge.state["watermarks"] = {"c1": "t1"}   # already at latest
    bridge.poll_inbound(post=True)
    # c1 unchanged -> never opened (only the self-chat, which always opens)
    assert 1 not in opened


def test_changed_chat_is_read(bridge, monkeypatch):
    chats = [{"id": "c1", "display_num": 1, "topic": "A", "last_message_time": "t2"}]
    _stub_teams(bridge, monkeypatch, chats, {"1": [{"id": "m2", "is_from_me": False}]})
    bridge.state["watermarks"] = {"c1": "t1"}   # stale -> should re-read
    bridge.poll_inbound(post=True)
    assert "m2" in bridge._calls.get("delivered", [])
    assert bridge.state["watermarks"]["c1"] == "t2"


def test_own_message_echo_guarded(bridge, monkeypatch):
    chats = [{"id": "c1", "display_num": 1, "topic": "A", "last_message_time": "t2"}]
    _stub_teams(bridge, monkeypatch, chats,
                {"1": [{"id": "m1", "is_from_me": True, "text_content": "reply-from-tg"}]})
    bridge.mark_bridge_sent("c1", "reply-from-tg")   # bridge sent this outbound to c1
    bridge.poll_inbound(post=True)
    # must NOT be re-delivered to Telegram (would be an echo loop)
    assert "m1" not in bridge._calls.get("delivered", [])


def test_own_message_forwarded_when_not_bridge_sent(bridge, monkeypatch):
    # ECHO_SELF on by default: your own Teams-app messages DO mirror
    chats = [{"id": "c1", "display_num": 1, "topic": "A", "last_message_time": "t2"}]
    _stub_teams(bridge, monkeypatch, chats,
                {"1": [{"id": "m9", "is_from_me": True, "text_content": "typed in teams app"}]})
    bridge.poll_inbound(post=True)
    assert "m9" in bridge._calls.get("delivered", [])


def test_seen_message_not_redelivered(bridge, monkeypatch):
    chats = [{"id": "c1", "display_num": 1, "topic": "A", "last_message_time": "t2"}]
    _stub_teams(bridge, monkeypatch, chats, {"1": [{"id": "m1", "is_from_me": False}]})
    bridge.seen["m1"] = None
    bridge.poll_inbound(post=True)
    assert "m1" not in bridge._calls.get("delivered", [])


def test_one_bad_chat_does_not_abort_poll(bridge, monkeypatch):
    chats = [{"id": "bad", "display_num": 1, "topic": "A", "last_message_time": "t2"},
             {"id": "good", "display_num": 2, "topic": "B", "last_message_time": "t2"}]
    def fake(*args):
        if args[0] == "chats":
            return chats
        if args[0] == "chat":
            if args[1] == 1:
                raise RuntimeError("unreadable")
            return [{"id": "mok", "is_from_me": False}]
        return []
    monkeypatch.setattr(bridge, "teams", fake)
    monkeypatch.setattr(bridge, "deliver_message",
                        lambda m, tid: bridge._calls.setdefault("delivered", []).append(m["id"]))
    monkeypatch.setattr(bridge, "topic_for_chat", lambda *a: 1)
    bridge.poll_inbound(post=True)
    # the good chat still delivered despite the bad one throwing
    assert "mok" in bridge._calls.get("delivered", [])
