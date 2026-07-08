"""Shared fixtures. Import bridge with a minimal env and network stubbed out."""
import os, sys, importlib
import pytest

# Make the repo root importable and satisfy the two required env vars so
# `import bridge` succeeds without a real Telegram/Teams setup.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("TELEGRAM_GROUP_ID", "-100999")


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    """Fresh bridge module with all outbound calls captured, not executed."""
    import bridge as b
    importlib.reload(b)

    calls = {"tg": [], "tg_photo": [], "tg_photo_url": [], "tg_document": [],
             "teams_do": [], "teams": []}

    # capture Telegram sends
    monkeypatch.setattr(b, "tg", lambda method, **kw: (calls["tg"].append((method, kw)) or {"result": {"message_thread_id": 1}}))
    monkeypatch.setattr(b, "tg_photo", lambda tid, path, caption="": (calls["tg_photo"].append((tid, path, caption)) or True))
    monkeypatch.setattr(b, "tg_photo_url", lambda tid, url, caption="": (calls["tg_photo_url"].append((tid, url, caption)) or True))
    monkeypatch.setattr(b, "tg_document", lambda tid, path, caption="": calls["tg_document"].append((tid, path, caption)))
    monkeypatch.setattr(b, "teams_do", lambda *a: calls["teams_do"].append(a))
    # isolate state to a temp file
    monkeypatch.setattr(b, "STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(b, "state", {"chat_to_topic": {}, "topic_to_chat": {}, "seen": []})
    monkeypatch.setattr(b, "seen", {})   # insertion-ordered dict (see bridge.seen)
    b._calls = calls
    return b
