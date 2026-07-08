"""Emoji-only Teams messages (empty text_content) recover the unicode emoji
from the <img alt=""> instead of showing [non-text message]."""

# real Teams emoticon HTML (from `teams chat`): text_content is empty.
WINK = ('<p><span title="Wink" type="(wink)" class="animated-emoticon-20-wink" '
        'itemscope=""><img itemscope="" itemtype="http://schema.skype.com/Emoji" '
        'itemid="wink" src="https://statics.teams.cdn.office.net/x/20_f.png" '
        'title="Wink" alt="😉" style="width:20px; height:20px"></span></p>')

# two emoji in ONE paragraph (how Teams sends consecutive emoji)
TWO = ('<p><span class="animated-emoticon-20-wink"><img '
       'itemtype="http://schema.skype.com/Emoji" itemid="wink" alt="😉"></span>'
       '<span class="animated-emoticon-20-giggle"><img '
       'itemtype="http://schema.skype.com/Emoji" itemid="giggle" alt="🤭"></span></p>')


def test_single_emoji_extracted(bridge):
    assert bridge.render_text(WINK) == "😉"


def test_multiple_emoji_in_order(bridge):
    assert bridge.render_text(TWO) == "😉🤭"


def test_no_emoji_returns_empty(bridge):
    assert bridge.render_text("<p>just text</p>") == "just text"
    assert bridge.render_text("") == ""


def test_real_image_not_treated_as_emoji(bridge):
    # a hosted photo <img> (not an emoji) must NOT be pulled into the text
    html_ = '<img src="https://fr-prod.asyncgw.teams.microsoft.com/o" alt="photo">'
    assert bridge.render_text(html_) == ""


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


# --- regressions caught in review ---
def test_html_entities_decoded_once(bridge):
    # render_text returns final Telegram HTML: entities decoded exactly once then
    # re-escaped, so a single &amp;/&lt; survives (renders "&"/"<" in Telegram).
    assert bridge.render_text("<p>me &amp; you</p>") == "me &amp; you"
    assert bridge.render_text("<p>a &lt; b &gt; c</p>") == "a &lt; b &gt; c"


def test_ampersand_message_not_double_escaped(bridge):
    m = {"sender": "A", "content": "<p>me &amp; you</p>", "text_content": "me & you"}
    bridge.deliver_message(m, tid=1)
    body = [kw for meth, kw in bridge._calls["tg"] if meth == "sendMessage"][0]["text"]
    # exactly one level of escaping in the delivered HTML body
    assert "me &amp; you" in body
    assert "&amp;amp;" not in body


def test_block_boundaries_become_newlines(bridge):
    assert bridge.render_text("<p>line1</p><p>line2</p>") == "line1\nline2"
    assert bridge.render_text("a<br>b") == "a\nb"


def test_multiline_message_keeps_breaks(bridge):
    m = {"sender": "A", "content": "<p>one</p><p>two</p>", "text_content": "onetwo"}
    bridge.deliver_message(m, tid=1)
    body = [kw for meth, kw in bridge._calls["tg"] if meth == "sendMessage"][0]["text"]
    assert "one\ntwo" in body


def test_empty_paragraphs_collapse(bridge):
    # Teams separates paragraphs with empty <p>&nbsp;</p>; without collapsing,
    # a multi-paragraph group message becomes a wall of \n\n\n\n. Blank runs
    # collapse to a single blank line; one paragraph break survives.
    content = "<p>a</p><p>&nbsp;</p><p>&nbsp;</p><p>b</p><p>&nbsp;</p><p>c</p>"
    assert bridge.render_text(content) == "a\n\nb\n\nc"


def test_code_block_blank_lines_collapse(bridge):
    # ponytail ceiling: the blank-line collapse also runs inside <pre>, so 3+
    # blank lines in a code block become one. Pinned so it's intentional, not a
    # silent regression — widen render_text to skip <pre> spans if it matters.
    assert bridge.render_text("<pre>a\n\n\n\nb</pre>") == "<pre>a\n\nb</pre>"
