"""teams_do must treat teams-cli's exit-0 + {"ok": false} stdout as a failure
(the API sometimes reports 400/403 that way), while letting normal non-JSON
success output ("Message sent to X") through.

Uses a fresh bridge import (not the `bridge` fixture, which stubs teams_do) so
the real function runs against a faked subprocess.run."""
import importlib
import types
import pytest


def _fake_run(stdout="", returncode=0, stderr=""):
    def run(*a, **k):
        return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
    return run


@pytest.fixture
def realbridge(monkeypatch):
    import bridge as b
    importlib.reload(b)          # fresh, un-stubbed teams_do
    return b


def test_ok_false_stdout_raises(realbridge, monkeypatch):
    monkeypatch.setattr(realbridge.subprocess, "run",
                        _fake_run('{"ok": false, "error": "403 Forbidden"}'))
    with pytest.raises(RuntimeError, match="403"):
        realbridge.teams_do("send", "bob", "-y", "--", "hi")


def test_nonjson_success_passthrough(realbridge, monkeypatch):
    monkeypatch.setattr(realbridge.subprocess, "run", _fake_run("Message sent to Bob"))
    assert realbridge.teams_do("send", "bob", "-y", "--", "hi") == "Message sent to Bob"


def test_ok_true_json_passthrough(realbridge, monkeypatch):
    monkeypatch.setattr(realbridge.subprocess, "run", _fake_run('{"ok": true, "data": 1}'))
    assert '"ok": true' in realbridge.teams_do("react", "like", "5", "-y")


def test_nonzero_exit_still_raises(realbridge, monkeypatch):
    monkeypatch.setattr(realbridge.subprocess, "run",
                        _fake_run("", returncode=1, stderr="boom"))
    with pytest.raises(RuntimeError, match="boom"):
        realbridge.teams_do("send", "bob", "-y", "--", "hi")
