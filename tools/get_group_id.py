#!/usr/bin/env python3
"""Print the Telegram chat id(s) the bot has seen recently.

Add the bot to your Topics-enabled supergroup, send any message in the group,
then run this. Copy the negative supergroup id into TELEGRAM_GROUP_ID.

    TELEGRAM_BOT_TOKEN=... python3 tools/get_group_id.py
"""
import os, json, urllib.request

tok = os.environ["TELEGRAM_BOT_TOKEN"]
with urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/getUpdates") as r:
    d = json.load(r)

seen = set()
for u in d.get("result", []):
    for key in ("message", "my_chat_member", "channel_post"):
        c = (u.get(key) or {}).get("chat") or {}
        if c and c.get("id") not in seen:
            seen.add(c.get("id"))
            print(f"id={c.get('id')}  type={c.get('type')}  "
                  f"title={c.get('title')!r}  is_forum={c.get('is_forum')}")
if not d.get("result"):
    print("No updates. Add the bot to the group and send a message there first.")
