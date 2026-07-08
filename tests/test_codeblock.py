"""Oversized code blocks must not silently vanish. Telegram caps a message at
4096 chars and returns 200 {"ok": false} past that; the bridge used to treat
that as success. These cover the split + the ok-check."""
import re
import html


def test_split_html_short_passthrough(bridge):
    assert bridge.split_html("hello") == ["hello"]


def test_split_html_chunks_under_limit(bridge):
    # one giant single-line code block (the real k8s base64 case: no <br>)
    payload = "A" * 30000
    body = f"<b>me</b>: <pre><code>{payload}</code></pre>"
    chunks = bridge.split_html(body)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= bridge.TG_LIMIT


def test_split_html_never_cuts_a_tag(bridge):
    body = "<pre><code>" + ("x" * 30000) + "</code></pre>"
    for c in bridge.split_html(body):
        # no truncated "<pr" / "</cod" — every < has a matching >
        assert c.count("<") == c.count(">")


def test_split_html_preserves_code_payload(bridge):
    payload = "".join(str(i % 10) for i in range(30000))
    body = f"<pre><code>{payload}</code></pre>"
    # strip the tags we (re)inserted, the surviving text must equal the payload
    joined = "".join(re.sub(r"</?[a-z]+>", "", c) for c in bridge.split_html(body))
    assert joined == payload


def test_split_html_reopens_pre_across_chunks(bridge):
    body = "<pre><code>" + ("y" * 30000) + "</code></pre>"
    chunks = bridge.split_html(body)
    for c in chunks:
        assert c.startswith("<pre><code>") and c.endswith("</code></pre>")


def test_split_html_never_cuts_an_entity(bridge):
    # render_text escapes content, so real code becomes &lt; &gt; &amp;. A char
    # slice could end mid-entity ("&amp") which Telegram rejects with 400.
    payload = ("if (a &lt; b &amp;&amp; c &gt; d) { x++; } " * 800)
    body = f"<pre><code>{payload}</code></pre>"
    for c in bridge.split_html(body):
        inner = c[len("<pre><code>"):-len("</code></pre>")]
        # no chunk may end with a dangling (unterminated) entity
        assert not re.search(r"&[#\w]{0,7}$", inner), repr(inner[-12:])


def test_oversized_message_sends_multiple(bridge):
    m = {"sender": "Dev", "content": "<pre><code>" + ("Z" * 30000) + "</code></pre>",
         "text_content": "", "id": "1", "_chat_id": "c1"}
    bridge.deliver_message(m, tid=7)
    sends = [kw for meth, kw in bridge._calls["tg"] if meth == "sendMessage"]
    assert len(sends) > 1
    for s in sends:
        assert len(s["text"]) <= bridge.TG_LIMIT


def test_tg_flags_api_rejection(bridge, monkeypatch, capsys):
    # unstub tg: exercise the real transport against a fake urlopen returning ok:false
    import importlib, bridge as real
    importlib.reload(real)

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": false, "description": "message is too long"}'

    monkeypatch.setattr(real.urllib.request, "urlopen", lambda *a, **k: FakeResp())
    out = real.tg("sendMessage", chat_id=1, text="x")
    assert out is None
    assert "too long" in capsys.readouterr().out
