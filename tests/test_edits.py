"""Teams message edits mirror to Telegram via editMessageText. Teams keeps the
same message id on edit (only content changes), so an edit is detected as a
re-read whose rendered body differs from what we last delivered."""


def _sends(bridge):
    return [kw for m, kw in bridge._calls["tg"] if m == "sendMessage"]


def _edits(bridge):
    return [kw for m, kw in bridge._calls["tg"] if m == "editMessageText"]


def _deliver(bridge, mid, content, chat="c1", tid=1):
    m = {"id": mid, "sender": "A", "content": content, "text_content": "",
         "_chat_id": chat}
    bridge.deliver_message(m, tid=tid)
    return m


def test_deliver_records_body_for_edit_detection(bridge):
    _deliver(bridge, "m1", "<p>hello</p>")
    assert "m1" in bridge._delivered_body


def test_edit_fires_editmessagetext(bridge):
    # deliver, then the same id comes back with changed content -> one edit
    _deliver(bridge, "m1", "<p>hello</p>")
    bridge.state["tg_to_teams"] = {"555": ["c1", "m1"]}   # tg msg 555 mirrors m1
    handled = bridge.mirror_edit_to_tg(
        {"id": "m1", "sender": "A", "content": "<p>hello EDITED</p>", "text_content": ""})
    assert handled is True
    edits = _edits(bridge)
    assert len(edits) == 1
    assert edits[0]["message_id"] == 555
    assert "EDITED" in edits[0]["text"]


def test_unchanged_content_no_edit(bridge):
    _deliver(bridge, "m1", "<p>hello</p>")
    bridge.state["tg_to_teams"] = {"555": ["c1", "m1"]}
    bridge.mirror_edit_to_tg(
        {"id": "m1", "sender": "A", "content": "<p>hello</p>", "text_content": ""})
    assert _edits(bridge) == []          # identical body -> no API call


def test_edit_of_unknown_message_ignored(bridge):
    # never delivered -> not our message -> no edit attempt
    handled = bridge.mirror_edit_to_tg(
        {"id": "ghost", "sender": "A", "content": "<p>x</p>", "text_content": ""})
    assert handled is False
    assert _edits(bridge) == []


def test_edit_without_tg_mapping_no_call(bridge):
    # delivered (so hash known) but no tg_to_teams entry -> can't locate the msg
    _deliver(bridge, "m1", "<p>hello</p>")
    bridge.state["tg_to_teams"] = {}
    bridge.mirror_edit_to_tg(
        {"id": "m1", "sender": "A", "content": "<p>changed</p>", "text_content": ""})
    assert _edits(bridge) == []


def test_second_identical_edit_not_resent(bridge):
    _deliver(bridge, "m1", "<p>hello</p>")
    bridge.state["tg_to_teams"] = {"555": ["c1", "m1"]}
    edited = {"id": "m1", "sender": "A", "content": "<p>v2</p>", "text_content": ""}
    bridge.mirror_edit_to_tg(edited)      # fires
    bridge.mirror_edit_to_tg(edited)      # same content again -> no second edit
    assert len(_edits(bridge)) == 1


def test_oversized_edit_does_not_refire(bridge):
    # regression: baseline must be the FULL body, not the truncated send, or an
    # edit over 4096 chars would refire editMessageText on every poll.
    _deliver(bridge, "m1", "<p>short</p>")
    bridge.state["tg_to_teams"] = {"555": ["c1", "m1"]}
    big = {"id": "m1", "sender": "A", "content": "<p>" + ("z" * 9000) + "</p>",
           "text_content": ""}
    bridge.mirror_edit_to_tg(big)         # fires once, truncated
    bridge.mirror_edit_to_tg(big)         # same (full) content -> must NOT refire
    edits = _edits(bridge)
    assert len(edits) == 1
    assert len(edits[0]["text"]) <= bridge.TG_LIMIT
