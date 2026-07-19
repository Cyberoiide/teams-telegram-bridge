"""`/chats` lists recent Teams chats (name · date, 🔕 if muted) to General."""


def _sends(bridge):
    return [kw["text"] for m, kw in bridge._calls["tg"] if m == "sendMessage"]


def _stub_chats(bridge, monkeypatch, chats):
    monkeypatch.setattr(bridge, "teams",
                        lambda *a: chats if a and a[0] == "chats" else [])


def test_chats_dispatched(bridge, monkeypatch):
    _stub_chats(bridge, monkeypatch, [])
    assert bridge.handle_dm_command("/chats") is True


def test_chats_lists_names_and_dates(bridge, monkeypatch):
    _stub_chats(bridge, monkeypatch, [
        {"id": "c1", "topic": "Heka Core", "last_message_time": "2026-07-18T09:00:00Z"},
        {"id": "c2", "last_message_sender": "Bob", "last_message_time": "2026-07-17T00:00:00Z"},
    ])
    bridge.handle_chats()
    out = _sends(bridge)[-1]
    assert "Heka Core" in out and "2026-07-18" in out
    assert "Bob" in out               # falls back to last_message_sender


def test_chats_marks_muted(bridge, monkeypatch):
    _stub_chats(bridge, monkeypatch, [
        {"id": "c1", "topic": "Loud Group", "last_message_time": "2026-07-18T00:00:00Z"}])
    bridge.set_muted("c1", True)
    bridge.handle_chats()
    assert "🔕" in _sends(bridge)[-1]


def test_chats_empty(bridge, monkeypatch):
    _stub_chats(bridge, monkeypatch, [])
    bridge.handle_chats()
    assert any("No recent chats" in s for s in _sends(bridge))


def test_chats_failure_relayed(bridge, monkeypatch):
    def boom(*a):
        raise RuntimeError("ic3 500")
    monkeypatch.setattr(bridge, "teams", boom)
    bridge.handle_chats()
    assert any("Couldn't list chats" in s for s in _sends(bridge))


def test_chats_capped(bridge, monkeypatch):
    many = [{"id": f"c{i}", "topic": f"Chat {i}", "last_message_time": "2026-07-18T00:00:00Z"}
            for i in range(40)]
    _stub_chats(bridge, monkeypatch, many)
    bridge.handle_chats()
    # header + at most _CHATS_MAX rows
    assert _sends(bridge)[-1].count("•") <= bridge._CHATS_MAX
