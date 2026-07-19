"""/mute stops a chat mirroring into Telegram; /unmute resumes. Muted messages
are still marked seen so unmuting doesn't flood the backlog."""
import pytest
from test_poll import _stub_teams


def test_set_and_is_muted(bridge):
    assert bridge.is_muted("c1") is False
    bridge.set_muted("c1", True)
    assert bridge.is_muted("c1") is True
    assert "c1" in bridge.state["muted"]
    bridge.set_muted("c1", False)
    assert bridge.is_muted("c1") is False


def test_muted_chat_not_delivered(bridge, monkeypatch):
    chats = [{"id": "c1", "display_num": 1, "topic": "A", "last_message_time": "t2"}]
    _stub_teams(bridge, monkeypatch, chats, {"1": [{"id": "m1", "is_from_me": False}]})
    bridge.set_muted("c1", True)
    bridge.poll_inbound(post=True)
    assert bridge._calls.get("delivered", []) == []      # nothing mirrored
    assert "m1" in bridge.seen                            # but marked seen


def test_unmute_resumes_without_flood(bridge, monkeypatch):
    chats = [{"id": "c1", "display_num": 1, "topic": "A", "last_message_time": "t2"}]
    _stub_teams(bridge, monkeypatch, chats, {"1": [{"id": "m1", "is_from_me": False}]})
    # muted: m1 seen, not delivered
    bridge.set_muted("c1", True)
    bridge.poll_inbound(post=True)
    assert bridge._calls.get("delivered", []) == []
    # unmute + a NEW message m2 arrives (bump watermark) -> only m2 delivers, not m1
    bridge.set_muted("c1", False)
    chats[0]["last_message_time"] = "t3"
    _stub_teams(bridge, monkeypatch, chats,
                {"1": [{"id": "m1", "is_from_me": False}, {"id": "m2", "is_from_me": False}]})
    bridge.poll_inbound(post=True)
    assert bridge._calls.get("delivered", []) == ["m2"]   # m1 stayed seen, no flood


def test_unmuted_chat_delivers_normally(bridge, monkeypatch):
    chats = [{"id": "c1", "display_num": 1, "topic": "A", "last_message_time": "t2"}]
    _stub_teams(bridge, monkeypatch, chats, {"1": [{"id": "m1", "is_from_me": False}]})
    bridge.poll_inbound(post=True)
    assert bridge._calls.get("delivered", []) == ["m1"]
