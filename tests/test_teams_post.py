"""tools/teams_post.py builds the IC3 payload by hand to get a subject line and a
working channel @mention, neither of which `teams chat-send` can do. The mention
shape was copied off real messages in the channel, so the test pins it to that
shape -- if a field name or the per-word split drifts, the post silently stops
notifying anyone, which looks identical to success.

teams_post imports teams_cli lazily inside main(), so importing it here needs no
credentials and touches no network.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import teams_post  # noqa: E402

CHANNEL = "19:yf2-R9Z4M9-ba9--x4Qrsah6Y0-mW4v3GQ159M-Dogs1@thread.tacv2"

# Verbatim from a real post in the channel (Clément BOSLE, 2026-07-28), read back
# out of properties.mentions. This is the contract.
REAL = [
    {"@type": "http://schema.skype.com/Mention", "itemid": 0, "mri": CHANNEL,
     "mentionType": "channel", "displayName": "[Run]"},
    {"@type": "http://schema.skype.com/Mention", "itemid": 1, "mri": CHANNEL,
     "mentionType": "channel", "displayName": "Engine"},
    {"@type": "http://schema.skype.com/Mention", "itemid": 2, "mri": CHANNEL,
     "mentionType": "channel", "displayName": "merge"},
    {"@type": "http://schema.skype.com/Mention", "itemid": 3, "mri": CHANNEL,
     "mentionType": "channel", "displayName": "requests"},
]


class _StubClient:
    """Only the four attributes build_payload touches."""
    _user_mri = "8:orgid:5f5e928f-4aa0-4efa-a680-e3c9abb77439"
    _display_name = "Clément BOSLE"

    @staticmethod
    def _make_client_message_id():
        return "1234567890123456789"


def test_channel_mention_matches_the_real_payload_exactly():
    _, mentions = teams_post.build_mention("[Run] Engine merge requests", CHANNEL)
    assert mentions == REAL


def test_mention_html_is_one_span_per_word_joined_by_nbsp():
    html, mentions = teams_post.build_mention("[Run] Engine merge requests", CHANNEL)
    assert html.count("<span") == 4 == len(mentions)
    assert html.count("&nbsp;") == 3          # separators only, none trailing
    for i, word in enumerate(["[Run]", "Engine", "merge", "requests"]):
        assert f'itemid="{i}">{word}</span>' in html
    # every span must have a mention object with the same itemid, or it renders
    # as inert text and notifies nobody
    assert [m["itemid"] for m in mentions] == [0, 1, 2, 3]


def test_mention_mri_is_the_channel_id_not_a_group_or_user_id():
    _, mentions = teams_post.build_mention("⏮ Reviews", "19:abc@thread.tacv2")
    assert {m["mri"] for m in mentions} == {"19:abc@thread.tacv2"}
    assert all(m["mentionType"] == "channel" for m in mentions)


def test_two_word_channel_name_yields_two_mentions():
    html, mentions = teams_post.build_mention("⏮ Reviews", CHANNEL)
    assert len(mentions) == 2
    assert [m["displayName"] for m in mentions] == ["⏮", "Reviews"]
    assert html.count("&nbsp;") == 1


def test_empty_mention_text_produces_nothing():
    assert teams_post.build_mention("", CHANNEL) == ("", [])
    assert teams_post.build_mention("   ", CHANNEL) == ("", [])


def test_first_itemid_offset_lets_a_person_mention_follow_a_channel_one():
    _, chan = teams_post.build_mention("[Run] Engine merge requests", CHANNEL)
    _, person = teams_post.build_mention("Théophile WALLEZ", CHANNEL,
                                         first_itemid=len(chan))
    assert [m["itemid"] for m in person] == [4, 5]


def test_payload_serialises_mentions_as_a_json_string():
    _, mentions = teams_post.build_mention("[Run] Engine merge requests", CHANNEL)
    payload = teams_post.build_payload(_StubClient(), CHANNEL, "<p>hi</p>",
                                       subject="[ci] x", mentions=mentions)
    raw = payload["properties"]["mentions"]
    assert isinstance(raw, str), "IC3 wants mentions as a JSON string, not a list"
    assert json.loads(raw) == REAL
    assert payload["properties"]["subject"] == "[ci] x"
    assert payload["messagetype"] == "RichText/Html"
    assert payload["conversationid"] == CHANNEL


def test_payload_omits_subject_when_not_given_but_always_sends_mentions():
    payload = teams_post.build_payload(_StubClient(), CHANNEL, "<p>hi</p>")
    assert "subject" not in payload["properties"]
    assert payload["properties"]["mentions"] == "[]"
