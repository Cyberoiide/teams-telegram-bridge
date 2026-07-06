"""Teams reply/quote messages render as a Telegram blockquote + reply, instead
of the mashed-together text_content."""

REPLY_HTML = (
    '<blockquote itemscope itemtype="http://schema.skype.com/Reply" itemid="178">'
    '<strong itemprop="mri" itemid="8:orgid:75431bcf">Elena LOUMAGNE</strong>'
    '<span itemprop="time" itemid="178"></span>'
    '<p itemprop="preview">Dispo mardi 7 svp ?</p></blockquote>'
    '<p>up <span itemtype="http://schema.skype.com/Mention" itemid="0">Tout le monde</span></p>'
)


def test_reply_extracts_author_and_quote(bridge):
    out = bridge.format_reply(REPLY_HTML)
    assert out is not None
    assert "<blockquote>" in out
    assert "Elena LOUMAGNE" in out
    assert "Dispo mardi 7 svp ?" in out


def test_reply_includes_reply_body_separately(bridge):
    out = bridge.format_reply(REPLY_HTML)
    # the reply text is present and OUTSIDE the quote block
    assert "up Tout le monde" in out
    after_quote = out.split("</blockquote>", 1)[1]
    assert "up Tout le monde" in after_quote
    assert "Dispo mardi" not in after_quote      # quote stayed in the quote


def test_non_reply_returns_none(bridge):
    assert bridge.format_reply("<p>just a normal message</p>") is None
    assert bridge.format_reply("") is None


def test_reply_escapes_html(bridge):
    evil = ('<blockquote itemtype="http://schema.skype.com/Reply">'
            '<strong itemprop="mri">A</strong>'
            '<p itemprop="preview">&lt;script&gt;</p></blockquote><p>hi</p>')
    out = bridge.format_reply(evil)
    assert "<script>" not in out       # no raw script tag injected


def test_reply_author_only_no_preview(bridge):
    html_ = ('<blockquote itemtype="http://schema.skype.com/Reply">'
             '<strong itemprop="mri">Bob</strong></blockquote><p>yo</p>')
    out = bridge.format_reply(html_)
    assert "Bob" in out and "yo" in out


def test_strip_tags(bridge):
    assert bridge.strip_tags("<p>hi <b>there</b></p>") == "hi there"
    assert bridge.strip_tags("") == ""
