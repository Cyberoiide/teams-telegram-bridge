"""The echo guard stops a Telegram reply from looping back into Telegram when
the inbound poll later sees that same message in Teams."""


def test_marked_text_is_recognized(bridge):
    bridge.mark_bridge_sent("hello world")
    assert bridge.was_bridge_sent("hello world") is True


def test_whitespace_insensitive(bridge):
    bridge.mark_bridge_sent("  spaced  ")
    assert bridge.was_bridge_sent("spaced") is True


def test_unknown_text_not_flagged(bridge):
    assert bridge.was_bridge_sent("never sent this") is False


def test_expires_after_window(bridge, monkeypatch):
    bridge.mark_bridge_sent("temp")
    # jump the clock past the 120s expiry window
    monkeypatch.setattr(bridge.time, "time", lambda: 10**12)
    assert bridge.was_bridge_sent("temp") is False


def test_expiry_cleans_up_map(bridge, monkeypatch):
    bridge.mark_bridge_sent("old")
    monkeypatch.setattr(bridge.time, "time", lambda: 10**12)
    bridge.was_bridge_sent("something")   # triggers opportunistic cleanup
    assert "old" not in bridge.sent_from_bridge


# --- suffix matching: a `teams reply` reads back as quote+body, so the
# read-back text_content ENDS WITH the bare text we sent (bug from code review).
def test_reply_readback_suffix_matches(bridge):
    bridge.mark_bridge_sent("ok")
    # inbound poll sees the reply mashed: quoted author+text + our "ok"
    assert bridge.was_bridge_sent("Alice: original message ok") is True


def test_plain_send_still_exact_matches(bridge):
    bridge.mark_bridge_sent("hello world")
    assert bridge.was_bridge_sent("hello world") is True


def test_unrelated_text_not_suffix_matched(bridge):
    bridge.mark_bridge_sent("ok")
    assert bridge.was_bridge_sent("this is not related") is False


def test_empty_sent_never_matches_everything(bridge):
    bridge.mark_bridge_sent("")           # ignored, not stored
    assert bridge.was_bridge_sent("anything at all") is False
