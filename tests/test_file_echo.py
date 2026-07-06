"""File uploads can't be content-matched, so the bridge marks the chat after an
outbound file send and skips re-mirroring its own attachment messages."""


def test_file_marker_recognized(bridge):
    bridge.mark_bridge_file("c1")
    assert bridge.was_bridge_file("c1") is True


def test_unmarked_chat_not_flagged(bridge):
    assert bridge.was_bridge_file("other") is False


def test_file_marker_expires(bridge, monkeypatch):
    bridge.mark_bridge_file("c1")
    monkeypatch.setattr(bridge.time, "time", lambda: 10**12)
    assert bridge.was_bridge_file("c1") is False


def test_msg_has_media_attachment(bridge):
    assert bridge.msg_has_media({"attachments": [{"id": "x"}]}) is True


def test_msg_has_media_hosted_image(bridge):
    m = {"content": '<img src="https://fr-prod.asyncgw.teams.microsoft.com/o">'}
    assert bridge.msg_has_media(m) is True


def test_msg_has_media_ignores_emoji(bridge):
    m = {"content": '<span itemtype="http://schema.skype.com/Emoji"><img src="https://x/e.png"></span>'}
    assert bridge.msg_has_media(m) is False


def test_msg_has_media_plain_text(bridge):
    assert bridge.msg_has_media({"content": "<p>hello</p>", "text_content": "hello"}) is False


def test_own_file_echo_skipped_in_poll(bridge, monkeypatch):
    # simulate: bridge uploaded a file to c1, then the poll sees our own
    # attachment message come back -> must NOT re-deliver.
    chats = [{"id": "c1", "display_num": 1, "topic": "A", "last_message_time": "t2"}]
    own_file_msg = {"id": "mf", "is_from_me": True, "content": "",
                    "attachments": [{"id": "a1"}], "text_content": ""}
    def fake(*args):
        if args[0] == "chats": return chats
        if args[0] == "chat": return [own_file_msg]
        return []
    monkeypatch.setattr(bridge, "teams", fake)
    monkeypatch.setattr(bridge, "deliver_message",
                        lambda m, tid: bridge._calls.setdefault("delivered", []).append(m["id"]))
    monkeypatch.setattr(bridge, "topic_for_chat", lambda *a: 1)
    bridge.mark_bridge_file("c1")            # we just uploaded to c1
    bridge.poll_inbound(post=True)
    assert "mf" not in bridge._calls.get("delivered", [])
