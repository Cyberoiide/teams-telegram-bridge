#!/usr/bin/env python3
"""Post a Teams message with a channel @mention and a subject line.

`teams chat-send` can do neither: its payload has no `subject` key and hardcodes
`"mentions": "[]"` (see teams_cli/client.py send_message). A channel post without
those is untitled and notifies nobody, which is the whole point of posting an MR
review request. This adds both by building the IC3 payload directly, reusing
teams_cli for auth and transport.

The mention shape was read off real messages in the channel, not guessed:

    properties.mentions = '[{"@type":"http://schema.skype.com/Mention",
                             "itemid":0,
                             "mri":"<the channel conversation id>",
                             "mentionType":"channel",
                             "displayName":"[Run]"}, ...]'

One object per whitespace-separated word of the channel name, itemid counting
from 0, each bound to a matching <span itemid="N"> in the HTML body. The MRI for
a channel mention is the channel's own conversation id -- not the groupId, not
the channel's SMTP address.

Usage:
    tools/teams_post.py --chat <conv-id> --body-file msg.html \
        [--subject "[ci] make deploys blocking"] \
        [--mention "[Run] Engine merge requests"] [--dry-run]

The body file must contain the literal token @@MENTION@@ wherever the mention
goes; it is replaced by the generated spans. Omit --mention and the token is
simply dropped.

ponytail: deliberately NOT a patch to teams_cli in site-packages -- a pipx
upgrade would silently wipe that. If teams-cli ever grows real --subject/--mention
support, delete this file and use it.
"""
import argparse
import json
import sys
from datetime import datetime, timezone

MENTION_TOKEN = "@@MENTION@@"
MENTION_SCHEMA = "http://schema.skype.com/Mention"


def build_mention(display_text, conv_id, first_itemid=0):
    """-> (html, mentions list) for a channel mention of `display_text`.

    Teams tokenises a channel mention per word: "[Run] Engine merge requests"
    becomes four spans / four mention objects sharing one MRI, joined by &nbsp;
    exactly as the real client emits them.
    """
    words = display_text.split()
    if not words:
        return "", []
    spans, mentions = [], []
    for i, word in enumerate(words):
        itemid = first_itemid + i
        spans.append(
            f'<span itemtype="{MENTION_SCHEMA}" itemscope="" '
            f'itemid="{itemid}">{word}</span>'
        )
        mentions.append({
            "@type": MENTION_SCHEMA,
            "itemid": itemid,
            "mri": conv_id,
            "mentionType": "channel",
            "displayName": word,
        })
    return "&nbsp;".join(spans), mentions


def build_payload(client, conv_id, content, subject=None, mentions=None):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    props = {
        "formatVariant": "TEAMS",
        "cards": "[]",
        "links": "[]",
        "mentions": json.dumps(mentions or [], separators=(",", ":")),
        "files": "[]",
    }
    if subject is not None:
        props["subject"] = subject
    return {
        "id": "-1",
        "type": "Message",
        "conversationid": conv_id,
        "from": client._user_mri,
        "composetime": now,
        "originalarrivaltime": now,
        "content": content,
        "messagetype": "RichText/Html",
        "contenttype": "Text",
        "imdisplayname": client._display_name,
        "clientmessageid": client._make_client_message_id(),
        "properties": props,
        "crossPostChannels": [],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--chat", required=True, help="conversation id (19:...@thread.tacv2)")
    ap.add_argument("--body-file", required=True,
                    help=f"HTML body; {MENTION_TOKEN} is replaced by the mention spans")
    ap.add_argument("--subject", default=None, help="title of the channel post")
    ap.add_argument("--mention", default=None,
                    help="channel display name to @mention, e.g. '[Run] Engine merge requests'")
    ap.add_argument("--dry-run", action="store_true", help="print the payload, send nothing")
    args = ap.parse_args()

    with open(args.body_file, encoding="utf-8") as fh:
        content = fh.read().strip()

    if args.mention:
        if MENTION_TOKEN not in content:
            sys.exit(f"error: --mention given but {MENTION_TOKEN} is not in the body")
        html, mentions = build_mention(args.mention, args.chat)
    else:
        html, mentions = "", []
    content = content.replace(MENTION_TOKEN, html)

    from teams_cli.auth import get_tokens
    from teams_cli.client import TeamsClient

    client = TeamsClient(get_tokens())
    if not client._display_name:
        from teams_cli.auth import _decode_display_name
        client._display_name = _decode_display_name(client._ic3) or "User"

    payload = build_payload(client, args.chat, content, args.subject, mentions)

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    resp = client._ic3_post(
        f"/users/ME/conversations/{args.chat}/messages",
        json_data=payload,
        is_write=True,
    )
    print(json.dumps(resp, ensure_ascii=False))


if __name__ == "__main__":
    main()
