"""`/search <query>` searches Teams messages (read-only teams search) and posts
a compact result list to the General topic."""
import pytest


def _sends(bridge):
    return [kw["text"] for m, kw in bridge._calls["tg"] if m == "sendMessage"]


def _stub_search(bridge, monkeypatch, results):
    def fake(*args):
        assert args[0] == "search"
        return results
    monkeypatch.setattr(bridge, "teams", fake)


def test_search_dispatched_from_general(bridge, monkeypatch):
    _stub_search(bridge, monkeypatch, [])
    assert bridge.handle_dm_command("/search budget") is True


def test_find_alias(bridge, monkeypatch):
    _stub_search(bridge, monkeypatch, [])
    assert bridge.handle_dm_command("/find budget") is True


def test_search_formats_results(bridge, monkeypatch):
    results = [
        {"sender": "Bob", "chat_title": "Heka Core", "timestamp": "2026-07-01T09:00:00Z",
         "text_content": "the budget is approved"},
        {"sender": "Alice", "chat_title": "", "timestamp": "2026-06-30T10:00:00Z",
         "text_content": "let's sync on budget"},
    ]
    _stub_search(bridge, monkeypatch, results)
    bridge.handle_search("budget")
    out = _sends(bridge)[-1]
    assert "Bob" in out and "Heka Core" in out and "budget is approved" in out
    assert "Alice" in out and "2026-06-30" in out


def test_search_no_results(bridge, monkeypatch):
    _stub_search(bridge, monkeypatch, [])
    bridge.handle_search("zxcv")
    assert any("No matches" in s for s in _sends(bridge))


def test_search_empty_query_usage(bridge):
    bridge.handle_search("")
    assert any("Usage:" in s for s in _sends(bridge))


def test_search_failure_relayed(bridge, monkeypatch):
    def boom(*a):
        raise RuntimeError("ic3 500")
    monkeypatch.setattr(bridge, "teams", boom)
    bridge.handle_search("x")
    assert any("Search failed" in s for s in _sends(bridge))


def test_search_caps_results(bridge, monkeypatch):
    many = [{"sender": f"U{i}", "chat_title": "C", "timestamp": "2026-07-01T00:00:00Z",
             "text_content": f"msg {i}"} for i in range(50)]
    _stub_search(bridge, monkeypatch, many)
    bridge.handle_search("x")
    out = _sends(bridge)[-1]
    # only up to _SEARCH_MAX bullet lines rendered
    assert out.count("\n\n") <= bridge._SEARCH_MAX


def test_bare_search_no_crash_shows_usage(bridge, monkeypatch):
    # "/search" or "/search   " (no query) must not IndexError -> shows usage
    _stub_search(bridge, monkeypatch, [])
    assert bridge.handle_dm_command("/search") is True
    assert bridge.handle_dm_command("/search    ") is True
    assert any("Usage:" in s for s in _sends(bridge))


def test_snippet_escaped_and_clamped(bridge, monkeypatch):
    _stub_search(bridge, monkeypatch, [
        {"sender": "X", "chat_title": "C", "timestamp": "2026-07-01T00:00:00Z",
         "text_content": "<script> " + "a" * 400}])
    bridge.handle_search("x")
    out = _sends(bridge)[-1]
    assert "&lt;script&gt;" in out          # escaped, not raw
    assert "a" * 200 not in out             # clamped under 160
