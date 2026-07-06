"""File uploads can't be content-matched, so the bridge marks the chat after an
outbound file send and skips re-mirroring its own attachment messages."""


def test_file_marker_recognized(bridge):
    bridge.mark_bridge_file("c1", "photo.jpg")
    assert bridge.was_bridge_file("c1", ["photo.jpg"]) is True


def test_wrong_filename_not_flagged(bridge):
    bridge.mark_bridge_file("c1", "photo.jpg")
    assert bridge.was_bridge_file("c1", ["other.png"]) is False


def test_wrong_chat_not_flagged(bridge):
    bridge.mark_bridge_file("c1", "photo.jpg")
    assert bridge.was_bridge_file("c2", ["photo.jpg"]) is False


def test_file_marker_expires(bridge, monkeypatch):
    bridge.mark_bridge_file("c1", "photo.jpg")
    monkeypatch.setattr(bridge.time, "time", lambda: 10**12)
    assert bridge.was_bridge_file("c1", ["photo.jpg"]) is False


def test_att_filenames(bridge):
    m = {"attachments": [{"name": "a.jpg"}, {"name": "b.pdf"}, {"id": "no-name"}]}
    assert bridge.att_filenames(m) == ["a.jpg", "b.pdf"]


def test_own_file_echo_skipped_in_poll(bridge, monkeypatch):
    # bridge uploaded photo.jpg to c1; the poll then sees our own attachment
    # message with that name -> must NOT re-deliver.
    chats = [{"id": "c1", "display_num": 1, "topic": "A", "last_message_time": "t2"}]
    own_file_msg = {"id": "mf", "is_from_me": True, "content": "",
                    "attachments": [{"id": "a1", "name": "photo.jpg"}], "text_content": ""}
    def fake(*args):
        if args[0] == "chats": return chats
        if args[0] == "chat": return [own_file_msg]
        return []
    monkeypatch.setattr(bridge, "teams", fake)
    monkeypatch.setattr(bridge, "deliver_message",
                        lambda m, tid: bridge._calls.setdefault("delivered", []).append(m["id"]))
    monkeypatch.setattr(bridge, "topic_for_chat", lambda *a: 1)
    bridge.mark_bridge_file("c1", "photo.jpg")   # we just uploaded it
    bridge.poll_inbound(post=True)
    assert "mf" not in bridge._calls.get("delivered", [])


def test_others_file_still_delivered(bridge, monkeypatch):
    # a file from someone ELSE (not from_me) must still be delivered
    chats = [{"id": "c1", "display_num": 1, "topic": "A", "last_message_time": "t2"}]
    other = {"id": "mo", "is_from_me": False, "content": "",
             "attachments": [{"id": "a1", "name": "theirs.jpg"}], "text_content": ""}
    def fake(*args):
        if args[0] == "chats": return chats
        if args[0] == "chat": return [other]
        return []
    monkeypatch.setattr(bridge, "teams", fake)
    monkeypatch.setattr(bridge, "deliver_message",
                        lambda m, tid: bridge._calls.setdefault("delivered", []).append(m["id"]))
    monkeypatch.setattr(bridge, "topic_for_chat", lambda *a: 1)
    bridge.mark_bridge_file("c1", "photo.jpg")
    bridge.poll_inbound(post=True)
    assert "mo" in bridge._calls.get("delivered", [])
