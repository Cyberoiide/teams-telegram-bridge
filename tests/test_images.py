"""Inline-image classification: emoji vs real, hosted vs public."""


def test_emoji_img_detected(bridge):
    ctx = '<span itemtype="http://schema.skype.com/Emoji"><img itemid="smile" src="https://x/emoji.png">'
    assert bridge.is_emoji_img(ctx) is True


def test_animated_emoticon_detected(bridge):
    assert bridge.is_emoji_img('class="animated-emoticon-20-smile"><img src="..."') is True


def test_real_image_not_emoji(bridge):
    assert bridge.is_emoji_img('<p><img src="https://fr-prod.asyncgw.teams.microsoft.com/x">') is False


def test_img_src_regex_extracts_urls(bridge):
    html = ('<p>hi</p><img src="https://asyncgw.teams.microsoft.com/a">'
            '<img itemid="x" src="https://media.giphy.com/b.gif">')
    urls = bridge.IMG_SRC.findall(html)
    assert urls == ["https://asyncgw.teams.microsoft.com/a",
                    "https://media.giphy.com/b.gif"]


def test_hosted_image_streamed_and_uploaded(bridge, monkeypatch):
    # a hosted Teams image -> fetch_hosted_image returns (filename, bytes) ->
    # tg_photo_bytes (streamed, no temp file)
    monkeypatch.setattr(bridge, "fetch_hosted_image", lambda url: ("image.jpg", b"\xff\xd8\xff"))
    msg = {"sender": "Alice",
           "content": '<img src="https://fr-prod.asyncgw.teams.microsoft.com/o/views/imgo">',
           "text_content": ""}
    bridge.deliver_message(msg, tid=7)
    calls = bridge._calls["tg_photo_bytes"]
    assert len(calls) == 1
    assert calls[0][0] == 7 and calls[0][1] == "image.jpg" and calls[0][2] == b"\xff\xd8\xff"


def test_public_image_sent_by_url(bridge):
    # a giphy/public url -> tg_photo_url (Telegram fetches it), no download
    msg = {"sender": "Bob",
           "content": '<img src="https://media.giphy.com/x.gif">',
           "text_content": ""}
    bridge.deliver_message(msg, tid=3)
    assert len(bridge._calls["tg_photo_url"]) == 1
    assert bridge._calls["tg_photo_url"][0][1] == "https://media.giphy.com/x.gif"


def test_emoji_only_message_sends_text_not_photo(bridge):
    msg = {"sender": "Cat",
           "content": '<span itemtype="http://schema.skype.com/Emoji"><img src="https://x/e.png"></span>',
           "text_content": "lol"}
    bridge.deliver_message(msg, tid=1)
    assert bridge._calls["tg_photo"] == []
    assert bridge._calls["tg_photo_url"] == []
    # text still delivered
    assert any(m == "sendMessage" for m, _ in bridge._calls["tg"])


def test_fetch_hosted_image_returns_bytes(bridge, monkeypatch):
    # returns (filename, bytes) with the right extension, no temp file on disk
    import urllib.request, io
    monkeypatch.setattr(bridge, "ic3_token", lambda: "tok")
    class R(io.BytesIO):
        headers = {"content-type": "image/png"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: R(b"PNGDATA"))
    got = bridge.fetch_hosted_image("https://asyncgw.teams.microsoft.com/x")
    assert got == ("image.png", b"PNGDATA")


def test_tg_upload_path_still_reads_file(bridge, monkeypatch, tmp_path):
    # the path-based wrapper (used by the attachment save-to path) still works
    f = tmp_path / "a.pdf"; f.write_bytes(b"%PDF-1.4")
    seen = {}
    monkeypatch.setattr(bridge, "tg_upload_bytes",
                        lambda kind, tid, fn, data, caption="": seen.update(kind=kind, fn=fn, data=data) or True)
    bridge.tg_upload("document", 3, str(f))
    assert seen == {"kind": "document", "fn": "a.pdf", "data": b"%PDF-1.4"}


def test_attachment_tempdir_cleaned(bridge, monkeypatch):
    # the tbatt- dir created for attachment download must be removed after,
    # not leaked in /tmp (regression: it used to accumulate).
    import bridge as b, tempfile, os
    created = {}
    real_mkdtemp = tempfile.mkdtemp
    def spy(*a, **k):
        d = real_mkdtemp(*a, **k); created["d"] = d; return d
    monkeypatch.setattr(b.tempfile, "mkdtemp", spy)
    monkeypatch.setattr(b, "teams", lambda *a: [])          # download yields nothing
    monkeypatch.setattr(b, "chat_num_for_id", lambda c: 1)
    m = {"sender": "A", "content": "", "text_content": "",
         "display_num": 5, "attachments": [{"name": "doc.pdf"}]}
    b.deliver_message(m, tid=1)
    assert "d" in created and not os.path.exists(created["d"])   # cleaned up
