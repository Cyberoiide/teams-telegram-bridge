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


def test_hosted_image_downloaded_and_uploaded(bridge, monkeypatch, tmp_path):
    # a hosted Teams image -> fetch_hosted_image path -> tg_photo
    fake = tmp_path / "img.jpg"; fake.write_bytes(b"\xff\xd8\xff")
    monkeypatch.setattr(bridge, "fetch_hosted_image", lambda url: str(fake))
    msg = {"sender": "Alice",
           "content": '<img src="https://fr-prod.asyncgw.teams.microsoft.com/o/views/imgo">',
           "text_content": ""}
    bridge.deliver_message(msg, tid=7)
    assert len(bridge._calls["tg_photo"]) == 1
    assert bridge._calls["tg_photo"][0][0] == 7


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
