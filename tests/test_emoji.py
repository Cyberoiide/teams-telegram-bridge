"""Emoji-only Teams messages (empty text_content) recover the unicode emoji
from the <img alt=""> instead of showing [non-text message]."""

# real Teams emoticon HTML (from `teams chat`): text_content is empty.
WINK = ('<p><span title="Wink" type="(wink)" class="animated-emoticon-20-wink" '
        'itemscope=""><img itemscope="" itemtype="http://schema.skype.com/Emoji" '
        'itemid="wink" src="https://statics.teams.cdn.office.net/x/20_f.png" '
        'title="Wink" alt="😉" style="width:20px; height:20px"></span></p>')

TWO = (WINK +
       '<span class="animated-emoticon-20-giggle"><img '
       'itemtype="http://schema.skype.com/Emoji" itemid="giggle" alt="🤭"></span>')


def test_single_emoji_extracted(bridge):
    assert bridge.emoji_text(WINK) == "😉"


def test_multiple_emoji_in_order(bridge):
    assert bridge.emoji_text(TWO) == "😉🤭"


def test_no_emoji_returns_empty(bridge):
    assert bridge.emoji_text("<p>just text</p>") == ""
    assert bridge.emoji_text("") == ""


def test_real_image_not_treated_as_emoji(bridge):
    # a hosted photo <img> (not an emoji) must NOT be pulled into emoji_text
    html_ = '<img src="https://fr-prod.asyncgw.teams.microsoft.com/o" alt="photo">'
    assert bridge.emoji_text(html_) == ""


def test_emoji_only_message_delivers_emoji_not_placeholder(bridge):
    m = {"sender": "Clément", "content": WINK, "text_content": ""}
    bridge.deliver_message(m, tid=1)
    sends = [kw for meth, kw in bridge._calls["tg"] if meth == "sendMessage"]
    assert len(sends) == 1
    assert "😉" in sends[0]["text"]
    assert "non-text message" not in sends[0]["text"]


def test_truly_empty_message_still_placeholder(bridge):
    m = {"sender": "X", "content": "", "text_content": ""}
    bridge.deliver_message(m, tid=1)
    body = [kw for meth, kw in bridge._calls["tg"] if meth == "sendMessage"][0]["text"]
    assert "non-text message" in body


# --- render_text: rebuild message text from content, emoji inline in position
MIXED = ('<p>petit <span class="animated-emoticon-20-thumbsup"><img '
         'itemtype="http://schema.skype.com/Emoji" itemid="thumbsup" alt="👍">'
         '</span> mdrr</p>')


def test_render_text_keeps_emoji_inline(bridge):
    assert bridge.render_text(MIXED) == "petit 👍 mdrr"


def test_render_text_plain(bridge):
    assert bridge.render_text("<p>just words</p>") == "just words"


def test_render_text_emoji_only(bridge):
    assert bridge.render_text(WINK) == "😉"


def test_render_text_drops_non_emoji_img(bridge):
    html_ = '<p>see <img src="https://asyncgw.teams.microsoft.com/x" alt="pic"> this</p>'
    # non-emoji image removed, text preserved (photo handled by the image path)
    assert bridge.render_text(html_) == "see  this"


def test_mixed_text_emoji_delivered(bridge):
    m = {"sender": "A", "content": MIXED, "text_content": "petit mdrr"}
    bridge.deliver_message(m, tid=1)
    body = [kw for meth, kw in bridge._calls["tg"] if meth == "sendMessage"][0]["text"]
    assert "👍" in body and "petit" in body and "mdrr" in body
