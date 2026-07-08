"""Teams rich formatting (bold/italic/underline/strike/code/pre/mentions) is
converted to the Telegram HTML subset instead of being stripped to plain text.
render_text returns final Telegram-ready HTML (already escaped)."""


def test_bold(bridge):
    assert bridge.render_text("<p><strong>hi</strong></p>") == "<b>hi</b>"


def test_bold_b_alias(bridge):
    assert bridge.render_text("<b>hi</b>") == "<b>hi</b>"


def test_italic(bridge):
    assert bridge.render_text("<em>hi</em>") == "<i>hi</i>"


def test_italic_i_alias(bridge):
    assert bridge.render_text("<i>hi</i>") == "<i>hi</i>"


def test_underline(bridge):
    assert bridge.render_text("<u>hi</u>") == "<u>hi</u>"


def test_strike(bridge):
    assert bridge.render_text("<s>hi</s>") == "<s>hi</s>"
    assert bridge.render_text("<strike>hi</strike>") == "<s>hi</s>"
    assert bridge.render_text("<del>hi</del>") == "<s>hi</s>"


def test_inline_code(bridge):
    assert bridge.render_text("<code>x=1</code>") == "<code>x=1</code>"


def test_code_block(bridge):
    assert bridge.render_text("<pre>line1\nline2</pre>") == "<pre>line1\nline2</pre>"


def test_mention(bridge):
    m = ('<p>hey <span itemtype="http://schema.skype.com/Mention" itemid="0">'
         'Alice Smith</span> there</p>')
    assert bridge.render_text(m) == "hey <b>@Alice Smith</b> there"


def test_nested_bold_italic(bridge):
    assert bridge.render_text("<b><i>hi</i></b>") == "<b><i>hi</i></b>"


def test_unknown_tag_dropped_text_kept(bridge):
    assert bridge.render_text('<span class="x">hi</span>') == "hi"


def test_injection_escaped(bridge):
    # stray < & and a script tag in TEXT must be escaped, not emitted as HTML
    assert bridge.render_text("<p>a &lt; b &amp; c</p>") == "a &lt; b &amp; c"
    assert bridge.render_text("<p>1 < 2 & 3</p>") == "1 &lt; 2 &amp; 3"
    out = bridge.render_text("<script>alert(1)</script>")
    assert "<script>" not in out


def test_emoji_and_formatting_combine(bridge):
    m = ('<p><strong>look</strong> <img itemtype="http://schema.skype.com/Emoji" '
         'itemid="thumbsup" alt="👍"></p>')
    assert bridge.render_text(m) == "<b>look</b> 👍"
