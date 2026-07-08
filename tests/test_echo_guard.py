"""The echo guard stops a Telegram reply from looping back into Telegram when
the inbound poll later sees that same message in Teams. Keyed by (chat_id, text)
so the same short text in a different chat isn't falsely skipped."""

C = "19:chatA"          # a chat id used across these tests
D = "19:chatB"          # a different chat


def test_marked_text_is_recognized(bridge):
    bridge.mark_bridge_sent(C, "hello world")
    assert bridge.was_bridge_sent(C, "hello world") is True


def test_whitespace_insensitive(bridge):
    bridge.mark_bridge_sent(C, "  spaced  ")
    assert bridge.was_bridge_sent(C, "spaced") is True


def test_unknown_text_not_flagged(bridge):
    assert bridge.was_bridge_sent(C, "never sent this") is False


def test_other_chat_not_flagged(bridge):
    # same text, DIFFERENT chat -> must NOT be treated as our echo (the bug).
    bridge.mark_bridge_sent(C, "ok")
    assert bridge.was_bridge_sent(D, "ok") is False
    assert bridge.was_bridge_sent(C, "ok") is True


def test_expires_after_window(bridge, monkeypatch):
    bridge.mark_bridge_sent(C, "temp")
    # jump the clock past the 120s expiry window
    monkeypatch.setattr(bridge.time, "time", lambda: 10**12)
    assert bridge.was_bridge_sent(C, "temp") is False


def test_expiry_cleans_up_map(bridge, monkeypatch):
    bridge.mark_bridge_sent(C, "old")
    monkeypatch.setattr(bridge.time, "time", lambda: 10**12)
    bridge.was_bridge_sent(C, "something")   # triggers opportunistic cleanup
    assert (C, "old") not in bridge.sent_from_bridge


# --- suffix matching: a `teams reply` reads back as quote+body, so the
# read-back text_content ENDS WITH the bare text we sent (bug from code review).
def test_reply_readback_suffix_matches(bridge):
    bridge.mark_bridge_sent(C, "ok")
    # inbound poll sees the reply mashed: quoted author+text + our "ok"
    assert bridge.was_bridge_sent(C, "Alice: original message ok") is True


def test_plain_send_still_exact_matches(bridge):
    bridge.mark_bridge_sent(C, "hello world")
    assert bridge.was_bridge_sent(C, "hello world") is True


def test_unrelated_text_not_suffix_matched(bridge):
    bridge.mark_bridge_sent(C, "ok")
    assert bridge.was_bridge_sent(C, "this is not related") is False


def test_empty_sent_never_matches_everything(bridge):
    bridge.mark_bridge_sent(C, "")           # ignored, not stored
    assert bridge.was_bridge_sent(C, "anything at all") is False
