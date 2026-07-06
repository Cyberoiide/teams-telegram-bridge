"""Outbound: a Telegram reply to a mirrored message becomes a Teams reply."""


def test_map_and_lookup(bridge):
    bridge.map_tg_message(555, "c1", "teams-123")
    assert bridge.tg_to_teams[555] == ("c1", "teams-123")


def test_map_ignores_none(bridge):
    bridge.map_tg_message(None, "c1", "t1")
    bridge.map_tg_message(9, "c1", None)
    assert 9 not in bridge.tg_to_teams and None not in bridge.tg_to_teams


def test_map_bounded(bridge):
    for i in range(bridge._TG_MAP_MAX + 50):
        bridge.map_tg_message(i, "c", f"t{i}")
    assert len(bridge.tg_to_teams) <= bridge._TG_MAP_MAX


def test_msg_num_for_id_found(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "teams",
        lambda *a: [{"id": "t1", "display_num": 10}, {"id": "t2", "display_num": 11}])
    assert bridge.msg_num_for_id(3, "t2") == 11


def test_msg_num_for_id_missing(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "teams", lambda *a: [{"id": "t1", "display_num": 10}])
    assert bridge.msg_num_for_id(3, "nope") is None


def test_deliver_records_mapping(bridge, monkeypatch):
    # tg() returns a message_id; deliver_message should map it to the teams msg
    monkeypatch.setattr(bridge, "tg",
        lambda method, **kw: {"result": {"message_id": 777}})
    m = {"sender": "A", "content": "<p>hi</p>", "text_content": "hi",
         "id": "teams-9", "_chat_id": "c1"}
    bridge.deliver_message(m, tid=1)
    assert bridge.tg_to_teams.get(777) == ("c1", "teams-9")
