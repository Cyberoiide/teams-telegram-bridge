"""tg_upload: kind -> Telegram method mapping, with the network stubbed."""
import io
import urllib.request
import pytest


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _capture(monkeypatch, bridge):
    seen = {}
    def fake_urlopen(req, *a, **k):
        seen["url"] = req.full_url
        seen["body"] = req.data
        return _Resp(b'{"ok": true}')
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


def test_photo_hits_sendPhoto(bridge, monkeypatch, tmp_path):
    seen = _capture(monkeypatch, bridge)
    f = tmp_path / "x.jpg"; f.write_bytes(b"\xff\xd8\xff")
    bridge.tg_upload("photo", 1, str(f))
    assert seen["url"].endswith("/sendPhoto")
    assert b'name="photo"; filename=' in seen["body"]


def test_document_hits_sendDocument(bridge, monkeypatch, tmp_path):
    seen = _capture(monkeypatch, bridge)
    f = tmp_path / "x.pdf"; f.write_bytes(b"%PDF")
    bridge.tg_upload("document", 1, str(f))
    assert seen["url"].endswith("/sendDocument")
    assert b'name="document"; filename=' in seen["body"]


def test_unknown_kind_rejected(bridge, monkeypatch, tmp_path):
    _capture(monkeypatch, bridge)
    f = tmp_path / "x"; f.write_bytes(b"z")
    with pytest.raises(KeyError):
        bridge.tg_upload("sticker", 1, str(f))


def test_download_filename_basenamed(bridge, monkeypatch, tmp_path):
    # Telegram doc.file_name is attacker-controlled; must be basename'd so a
    # "../../x" name can't escape the temp dir.
    import urllib.request, io, os
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(bridge, "tg", lambda m, **k: {"result": {"file_path": "x.bin"}})
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: R(b"data"))
    p = bridge.tg_download_file("fid", want_name="../../../evil.sh")
    assert os.path.basename(p) == "evil.sh"
    assert os.path.dirname(p).startswith("/tmp") or "tgdl-" in p   # stayed in temp dir
