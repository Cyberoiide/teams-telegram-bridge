"""Reactions bridge both ways: Teams reactions -> Telegram setMessageReaction,
and Telegram reactions -> teams react/unreact."""


def test_emoji_maps_roundtrip(bridge):
    assert bridge.TEAMS_TO_TG_EMOJI["like"] == "👍"
    assert bridge.TG_TO_TEAMS_EMOJI["👍"] == "like"
    # TG->Teams uses the WRITE spelling; every unicode maps to a react-able name
    for uni, name in bridge.TG_TO_TEAMS_EMOJI.items():
        assert bridge.TEAMS_TO_TG_EMOJI[name] == uni   # write name round-trips


def test_readback_spellings_mapped(bridge):
    # Teams reads laugh/sad/angry back under different names — all must map so
    # Teams->Telegram mirroring works (regression from live E2E test).
    assert bridge.TEAMS_TO_TG_EMOJI["cwl"] == "😁"       # laugh
    assert bridge.TEAMS_TO_TG_EMOJI["cry"] == "😢"       # sad
    assert bridge.TEAMS_TO_TG_EMOJI["angryface"] == "😡"  # angry


def test_tg_msg_for_teams_reverse_lookup(bridge):
    bridge.map_tg_message(500, "c1", "teams-7")
    assert bridge.tg_msg_for_teams("teams-7") == 500
    assert bridge.tg_msg_for_teams("nope") is None


# --- Teams -> Telegram --------------------------------------------------
def test_mirror_reaction_sets_on_mapped_message(bridge, monkeypatch):
    calls = []
    monkeypatch.setattr(bridge, "tg_set_reaction", lambda tg_id, e: calls.append((tg_id, e)))
    bridge.map_tg_message(88, "c1", "tm1")
    m = {"id": "tm1", "reactions": [{"emoji": "heart", "user_id": "u2"}]}
    bridge.mirror_reactions_to_tg(m)
    assert calls == [(88, "❤")]


def test_mirror_reaction_skips_unmapped(bridge, monkeypatch):
    calls = []
    monkeypatch.setattr(bridge, "tg_set_reaction", lambda *a: calls.append(a))
    bridge.mirror_reactions_to_tg({"id": "unknown", "reactions": [{"emoji": "like"}]})
    assert calls == []


def test_mirror_reaction_only_on_change(bridge, monkeypatch):
    calls = []
    monkeypatch.setattr(bridge, "tg_set_reaction", lambda tg_id, e: calls.append(e))
    bridge.map_tg_message(9, "c1", "tm2")
    m = {"id": "tm2", "reactions": [{"emoji": "like"}]}
    bridge.mirror_reactions_to_tg(m)          # sets 👍
    bridge.mirror_reactions_to_tg(m)          # unchanged -> no call
    assert calls == ["👍"]
    m2 = {"id": "tm2", "reactions": []}
    bridge.mirror_reactions_to_tg(m2)         # cleared
    assert calls == ["👍", ""]


def test_mirror_reaction_unmappable_never_set_no_call(bridge, monkeypatch):
    calls = []
    monkeypatch.setattr(bridge, "tg_set_reaction", lambda tg_id, e: calls.append(e))
    bridge.map_tg_message(3, "c1", "tm3")
    # unmappable emoji on a message we never reacted to -> no API call (avoids a
    # doomed clear retried every poll)
    bridge.mirror_reactions_to_tg({"id": "tm3", "reactions": [{"emoji": "confused"}]})
    assert calls == []


def test_mirror_clears_only_after_a_set(bridge, monkeypatch):
    calls = []
    monkeypatch.setattr(bridge, "tg_set_reaction", lambda tg_id, e: calls.append(e))
    bridge.map_tg_message(4, "c1", "tm4")
    bridge.mirror_reactions_to_tg({"id": "tm4", "reactions": [{"emoji": "like"}]})  # set 👍
    bridge.mirror_reactions_to_tg({"id": "tm4", "reactions": []})                    # clear
    assert calls == ["👍", ""]


# --- Telegram -> Teams --------------------------------------------------
def test_reaction_added_calls_react(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "chat_num_for_id", lambda cid: 5)
    monkeypatch.setattr(bridge, "msg_num_for_id", lambda t, i: 42)
    bridge.map_tg_message(200, "c9", "tmX")
    mr = {"chat": {"id": bridge.TG_GROUP_ID}, "message_id": 200,
          "old_reaction": [], "new_reaction": [{"type": "emoji", "emoji": "👍"}]}
    bridge.handle_reaction_update(mr)
    assert ("react", "like", "42", "-y") in bridge._calls["teams_do"]


def test_reaction_removed_calls_unreact(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "chat_num_for_id", lambda cid: 5)
    monkeypatch.setattr(bridge, "msg_num_for_id", lambda t, i: 42)
    bridge.map_tg_message(201, "c9", "tmY")
    mr = {"chat": {"id": bridge.TG_GROUP_ID}, "message_id": 201,
          "old_reaction": [{"type": "emoji", "emoji": "❤"}], "new_reaction": []}
    bridge.handle_reaction_update(mr)
    assert ("unreact", "heart", "42", "-y") in bridge._calls["teams_do"]


def test_reaction_unmapped_message_ignored(bridge):
    mr = {"chat": {"id": bridge.TG_GROUP_ID}, "message_id": 999999,
          "old_reaction": [], "new_reaction": [{"type": "emoji", "emoji": "👍"}]}
    bridge.handle_reaction_update(mr)
    assert bridge._calls["teams_do"] == []


def test_reaction_wrong_group_ignored(bridge, monkeypatch):
    bridge.map_tg_message(202, "c9", "tmZ")
    mr = {"chat": {"id": "-100OTHER"}, "message_id": 202,
          "old_reaction": [], "new_reaction": [{"type": "emoji", "emoji": "👍"}]}
    bridge.handle_reaction_update(mr)
    assert bridge._calls["teams_do"] == []


def test_mirror_maps_readback_name(bridge, monkeypatch):
    # a laugh reaction reads back as "cwl" -> must mirror as 😆
    calls = []
    monkeypatch.setattr(bridge, "tg_set_reaction", lambda tg_id, e: calls.append(e))
    bridge.map_tg_message(70, "c1", "tmL")
    bridge.mirror_reactions_to_tg({"id": "tmL", "reactions": [{"emoji": "cwl"}]})
    assert calls == ["😁"]


def test_mirror_cache_is_bounded(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "tg_set_reaction", lambda *a: None)
    monkeypatch.setattr(bridge, "tg_msg_for_teams", lambda t: None)
    for i in range(bridge._MIRROR_MAX + 100):
        bridge.mirror_reactions_to_tg({"id": f"m{i}", "reactions": [{"emoji": "like"}]})
    assert len(bridge._mirrored_reaction) <= bridge._MIRROR_MAX


def test_unmapped_reacted_msg_cached_no_rescan(bridge, monkeypatch):
    # a reacted message that isn't mapped: cache the emoji so the next poll skips
    # (no repeated tg_msg_for_teams scan).
    scans = []
    monkeypatch.setattr(bridge, "tg_msg_for_teams", lambda t: scans.append(t) or None)
    m = {"id": "um1", "reactions": [{"emoji": "like"}]}
    bridge.mirror_reactions_to_tg(m)   # scans once
    bridge.mirror_reactions_to_tg(m)   # unchanged -> must NOT scan again
    assert scans == ["um1"]
