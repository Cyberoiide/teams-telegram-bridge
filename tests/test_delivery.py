"""deliver_message text/fallback behavior + teams() JSON unwrapping."""


def test_plain_text_message(bridge):
    msg = {"sender": "Théo", "content": "<p>salut</p>", "text_content": "salut"}
    bridge.deliver_message(msg, tid=5)
    sends = [kw for m, kw in bridge._calls["tg"] if m == "sendMessage"]
    assert len(sends) == 1
    assert "salut" in sends[0]["text"]
    assert "Th" in sends[0]["text"]          # sender name present


def test_sender_name_html_escaped(bridge):
    msg = {"sender": "<script>", "content": "", "text_content": "hi"}
    bridge.deliver_message(msg, tid=1)
    body = [kw for m, kw in bridge._calls["tg"] if m == "sendMessage"][0]["text"]
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_empty_nontext_message_gets_placeholder(bridge):
    msg = {"sender": "X", "content": "", "text_content": ""}
    bridge.deliver_message(msg, tid=1)
    body = [kw for m, kw in bridge._calls["tg"] if m == "sendMessage"][0]["text"]
    assert "non-text message" in body


def test_missing_sender_defaults(bridge):
    msg = {"content": "", "text_content": "yo"}
    bridge.deliver_message(msg, tid=1)
    body = [kw for m, kw in bridge._calls["tg"] if m == "sendMessage"][0]["text"]
    assert "?" in body


def test_teams_unwraps_data_envelope(bridge, monkeypatch):
    import subprocess
    class R:
        returncode = 0
        stdout = '{"ok": true, "schema_version": "1.0", "data": [{"id": "c1"}]}'
        stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert bridge.teams("chats") == [{"id": "c1"}]


def test_teams_empty_output_returns_list(bridge, monkeypatch):
    import subprocess
    class R:
        returncode = 0; stdout = ""; stderr = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert bridge.teams("chats") == []


def test_teams_raises_on_error(bridge, monkeypatch):
    import subprocess, pytest
    class R:
        returncode = 1; stdout = ""; stderr = "boom"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    with pytest.raises(RuntimeError):
        bridge.teams("chats")
