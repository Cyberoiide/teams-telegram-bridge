#!/usr/bin/env python3
"""Teams <-> Telegram bridge (forum-topics layout).

Auth  : container broker issues the device-bound PRT SSO cookie; Playwright
        drives Teams web as a compliant device and scrapes the genuine
        ic3.teams.office.com token (see teams_web_token.py). The token lasts
        ~24h; we re-mint on a timer. teams-cli reads/sends via the IC3 API.
Layout: one Telegram forum TOPIC per Teams chat. Inbound Teams msgs post into
        their topic; a reply inside a topic routes to that Teams chat.

ponytail: polling (not Trouter ws) — seconds of latency is fine for a personal
          bridge. Add Trouter only if that latency actually bites.
"""
import os, sys, json, time, subprocess, threading, html, re, glob, tempfile
import urllib.request, urllib.parse

# Config is read from the environment, but ONLY the bot token / group id are
# required — and only when actually running (main()), not at import time, so the
# module can be imported for tests without a full environment.
_HERE       = os.path.dirname(os.path.abspath(__file__))
TG_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_GROUP_ID = os.environ.get("TELEGRAM_GROUP_ID", "")   # supergroup w/ topics, bot = admin
TOKEN_SCRIPT= os.environ.get("TOKEN_SCRIPT", os.path.join(_HERE, "token_mint.py"))
CACHE       = os.path.expanduser("~/.cache/teams-cli/tokens.json")
STATE       = os.path.expanduser("~/.cache/teams-bridge/state.json")
REGION      = os.environ.get("TEAMS_REGION", "emea")
POLL_SEC    = int(os.environ.get("POLL_SEC", "5"))
REFRESH_SEC = int(os.environ.get("REFRESH_SEC", "72000"))  # 20h (token good ~24h)
# Forward your OWN sent messages too, so the full conversation is readable from
# Telegram/phone. We still skip messages the BRIDGE itself sent (outbound from a
# Telegram reply) to avoid an echo loop — see sent_from_bridge.
ECHO_SELF   = os.environ.get("ECHO_SELF", "1") == "1"

# text we just sent to Teams (from a Telegram message); skip echoing it back.
# Match on SUFFIX, not equality: a message sent via `teams reply` reads back with
# the quoted text mashed in front of the body (author+quote+body), so the
# read-back text_content *ends with* the bare text we sent. Plain sends match by
# equality (also a suffix). See format_reply for the mashing.
sent_from_bridge = {}  # sent-text -> expiry epoch
def mark_bridge_sent(text):
    t = (text or "").strip()
    if t:
        sent_from_bridge[t] = time.time() + 120
def was_bridge_sent(text):
    t = (text or "").strip(); now = time.time()
    hit = False
    for s, exp in list(sent_from_bridge.items()):
        if exp < now:
            sent_from_bridge.pop(s, None)
        elif s and (t == s or t.endswith(s)):
            hit = True
    return hit

# Files can't be content-matched. After the bridge uploads a file we remember
# (chat id, filename) for a window; when the inbound poll later sees our OWN
# attachment message with that filename in that chat, we skip re-mirroring it.
sent_file_key = {}  # (chat_id, filename) -> expiry epoch
def mark_bridge_file(chat_id, filename):
    sent_file_key[(chat_id, filename)] = time.time() + 600
def was_bridge_file(chat_id, filenames):
    now = time.time()
    for k, v in list(sent_file_key.items()):
        if v < now:
            sent_file_key.pop(k, None)
    return any(sent_file_key.get((chat_id, fn), 0) > now for fn in filenames)

def att_filenames(m):
    """Filenames of a message's attachments (Teams file messages)."""
    return [a.get("name") for a in (m.get("attachments") or []) if a.get("name")]

# Serializes access to the shared `state` dict across the inbound and outbound
# threads (both mutate + save it). See save_state / map_tg_message.
STATE_LOCK = threading.Lock()

# Maps a Telegram message id we posted -> (teams chat id, teams message id) of
# the message it mirrors. Lets an outbound Telegram *reply* become a Teams reply
# to the right message. Persisted in state.json so replies survive restarts.
# Bounded so it doesn't grow forever.
_TG_MAP_MAX = 4000
def _tg_map():
    return state.setdefault("tg_to_teams", {})
def map_tg_message(tg_msg_id, chat_id, teams_msg_id):
    if tg_msg_id is None or teams_msg_id is None:
        return
    with STATE_LOCK:                               # mutation shared across threads
        m = _tg_map()
        m[str(tg_msg_id)] = [chat_id, teams_msg_id]   # JSON keys are strings
        if len(m) > _TG_MAP_MAX:                       # drop oldest ~10%
            for k in list(m)[:_TG_MAP_MAX // 10]:
                m.pop(k, None)
def lookup_tg_message(tg_msg_id):
    v = _tg_map().get(str(tg_msg_id))
    return tuple(v) if v else None
def tg_msg_for_teams(teams_msg_id):
    """Reverse lookup: the Telegram message id we posted for a Teams message id
    (or None). Used to mirror Teams reactions onto the Telegram message."""
    tid = str(teams_msg_id)
    for k, v in _tg_map().items():
        if v and str(v[1]) == tid:
            return int(k)
    return None

# Teams<->Telegram reaction mapping. Two gotchas, both found by live testing:
#  1. Teams' read-back name differs from the send name (laugh->cwl, sad->cry,
#     angry->angryface) — both spellings mapped so mirroring catches all.
#  2. Telegram only accepts a fixed set of reaction emoji; 😆/😮/😠 are rejected
#     (REACTION_INVALID). The valid ones verified against the API are used here.
# Telegram unicode <- Teams reaction name (send + read-back spellings):
TEAMS_TO_TG_EMOJI = {
    "like": "👍",
    "heart": "❤",
    "laugh": "😁", "cwl": "😁",
    "surprised": "😱",
    "sad": "😢", "cry": "😢",
    "angry": "😡", "angryface": "😡",
}
# Telegram unicode -> the name to PASS to `teams react/unreact` (write spelling).
TG_TO_TEAMS_EMOJI = {"👍": "like", "❤": "heart", "😁": "laugh",
                     "😱": "surprised", "😢": "sad", "😡": "angry"}

# last reaction-emoji we saw per Teams message, so we only hit the API when it
# changes. One entry per message the poll touches (not just reacted ones), so
# it's bounded like `seen`/`tg_map` to stop unbounded growth over long runs.
# teams_msg_id -> tg emoji (or "").
_mirrored_reaction = {}
_MIRROR_MAX = 4000
def _remember_reaction(teams_id, emoji):
    _mirrored_reaction[teams_id] = emoji
    if len(_mirrored_reaction) > _MIRROR_MAX:      # drop oldest ~10%
        for k in list(_mirrored_reaction)[:_MIRROR_MAX // 10]:
            _mirrored_reaction.pop(k, None)
def tg_set_reaction(tg_msg_id, emoji):
    """Set (or clear, emoji="") the bot's reaction on a Telegram message."""
    reaction = json.dumps([{"type": "emoji", "emoji": emoji}]) if emoji else "[]"
    try:
        tg("setMessageReaction", chat_id=TG_GROUP_ID, message_id=tg_msg_id,
           reaction=reaction)
    except Exception as e:
        print(f"[react] set {emoji or 'clear'}: {e}", flush=True)

def mirror_reactions_to_tg(m):
    """Reflect a Teams message's reactions onto its mirrored Telegram message.
    Bots can hold one reaction, so we show the first mappable one (or clear)."""
    teams_id = m.get("id")
    if teams_id is None:
        return
    emoji = ""
    for r in (m.get("reactions") or []):
        e = TEAMS_TO_TG_EMOJI.get(r.get("emoji"))
        if e:
            emoji = e; break
    prev = _mirrored_reaction.get(teams_id)     # None = never seen this message
    if prev == emoji:
        return                                  # unchanged -> no API call
    # never clear a message we never set a reaction on (avoids retrying a doomed
    # clear every poll on old/unreactable messages).
    if prev is None and emoji == "":
        _remember_reaction(teams_id, "")        # remember, don't call the API
        return
    tg_id = tg_msg_for_teams(teams_id)
    # cache the seen emoji either way (even when unmapped) so we don't re-scan the
    # whole map every poll for a reacted-but-unmapped message.
    _remember_reaction(teams_id, emoji)
    if tg_id is not None:
        tg_set_reaction(tg_id, emoji)

def tg(method, **params):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode()
    for _ in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data)) as r:
                resp = json.load(r)
            # Telegram signals failure via 200 OK + {"ok": false}, NOT an HTTP
            # error. Without this check a rejected send (e.g. body too long) looks
            # like success and the message silently vanishes.
            if not resp.get("ok"):
                print(f"[tg] {method} rejected: {resp.get('description')}", flush=True)
                return None
            return resp
        except urllib.error.HTTPError as e:
            if e.code == 429:
                body = json.load(e) if e.headers.get("content-type","").startswith("application/json") else {}
                wait = (body.get("parameters") or {}).get("retry_after", 3)
                time.sleep(wait + 1); continue
            raise
    raise RuntimeError(f"tg {method}: gave up after 429s")

def tg_upload(kind, thread_id, path, caption=""):
    """Upload a local file to a topic via multipart/form-data.
    kind: "photo" (sendPhoto) or "document" (sendDocument)."""
    method = {"photo": "sendPhoto", "document": "sendDocument"}[kind]
    url = f"https://api.telegram.org/bot{TG_TOKEN}/{method}"
    boundary = "----tgbridge" + str(int(time.time()*1000))
    fields = {"chat_id": str(TG_GROUP_ID), "message_thread_id": str(thread_id)}
    if caption:
        fields["caption"] = caption[:1000]; fields["parse_mode"] = "HTML"
    body = b""
    for k, v in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    with open(path, "rb") as f:
        data = f.read()
    fn = os.path.basename(path) or kind
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{kind}\"; filename=\"{fn}\"\r\n"
             f"Content-Type: application/octet-stream\r\n\r\n").encode()
    body += data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    for _ in range(4):
        try:
            with urllib.request.urlopen(req) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(3); continue
            raise
    return None

def tg_photo(thread_id, path, caption=""):
    return tg_upload("photo", thread_id, path, caption)

def tg_document(thread_id, path, caption=""):
    return tg_upload("document", thread_id, path, caption)

def tg_photo_url(thread_id, photo_url, caption=""):
    """Let Telegram fetch a public image URL directly (giphy etc)."""
    try:
        return tg("sendPhoto", chat_id=TG_GROUP_ID, message_thread_id=thread_id,
                  photo=photo_url, caption=caption[:1000], parse_mode="HTML")
    except Exception:
        return None

def teams(*args):
    """Read commands: append --json and parse the {ok,data} wrapper."""
    r = subprocess.run(["teams", *args, "--json"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"teams {args}: {r.stderr[:200] or r.stdout[:200]}")
    if not r.stdout.strip():
        return []
    d = json.loads(r.stdout)
    return d.get("data", d) if isinstance(d, dict) else d

def teams_do(*args):
    """Mutating commands (chat-send etc): NO --json flag (they don't accept it)."""
    r = subprocess.run(["teams", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"teams {args}: {r.stderr[:200] or r.stdout[:200]}")
    return r.stdout.strip()

# The "Notes to self" chat (Clément BOSLE (you)) never appears in `teams chats`,
# but is fully usable by its fixed id. We always poll + always give it a topic.
# read:  teams chat 48:notes    send: teams chat-send 48:notes <msg>
SELF_CHAT_ID = "48:notes"
SELF_CHAT_TITLE = "Notes to self"

# --- state: map Teams chat id <-> Telegram topic id ------------------------
def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"chat_to_topic": {}, "topic_to_chat": {}, "seen": []}

def save_state(s):
    # Serialize the dump under STATE_LOCK so it can't race the other thread's
    # map_tg_message mutation ("dict changed size during iteration"), and write
    # atomically (temp + os.replace) so a crash/concurrent save can't leave a
    # truncated state.json.
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with STATE_LOCK:
        blob = json.dumps(s)
        tmp = STATE + ".tmp"
        with open(tmp, "w") as f:
            f.write(blob)
        os.replace(tmp, STATE)

state = load_state()
seen = set(state.get("seen", []))

def topic_for_chat(chat_id, title):
    """Return Telegram message_thread_id for a Teams chat, creating a topic once."""
    m = state["chat_to_topic"]
    if chat_id in m:
        return m[chat_id]
    name = (title or chat_id)[:120] or "Teams chat"
    r = tg("createForumTopic", chat_id=TG_GROUP_ID, name=name)
    tid = r["result"]["message_thread_id"]
    m[chat_id] = tid
    state["topic_to_chat"][str(tid)] = chat_id
    save_state(state)
    return tid

# --- auth refresh (Playwright PRT->ic3 path) -------------------------------
def refresh_token():
    # teams_web_token.py drives Teams web and writes ~/ic3.jwt (+ ~/graph.jwt if
    # available). We inject both as a tokens.json bundle so send-file (Graph) and
    # chat read/send (ic3) both work.
    r = subprocess.run([sys.executable, TOKEN_SCRIPT], capture_output=True, text=True,
                       env={**os.environ, "DISPLAY": ":99"})
    ic3p = os.path.expanduser("~/ic3.jwt")
    if "IC3_TOKEN_OK" not in r.stdout or not os.path.exists(ic3p):
        raise RuntimeError(f"token mint failed: {r.stdout[-200:]} {r.stderr[-200:]}")
    import base64
    ic3 = open(ic3p).read().strip()
    def claims(t):
        p = t.split(".")[1]; p += "="*(-len(p)%4)
        return json.loads(base64.urlsafe_b64decode(p))
    c = claims(ic3)
    graphp = os.path.expanduser("~/graph.jwt")
    graph = open(graphp).read().strip() if os.path.exists(graphp) else ""
    bundle = json.dumps({"ic3": ic3, "ic3_exp": c["exp"], "graph": graph,
                         "region": REGION, "user_id": c.get("oid")})
    p = subprocess.run(["teams", "login", "--with-token", "--region", REGION],
                       input=bundle, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"teams login failed: {p.stderr[:200]}")

def refresh_loop():
    while True:
        try:
            refresh_token(); print("[auth] token refreshed", flush=True)
        except Exception as e:
            print(f"[auth] FAILED: {e}", flush=True)
            time.sleep(120); continue
        time.sleep(REFRESH_SEC)

# --- inbound: Teams -> Telegram topics -------------------------------------
def poll_inbound(post=True):
    """Scan chats for new messages. post=False just marks them seen (prime)."""
    # ONE list call per cycle. Only open a chat whose last_message_time advanced
    # past the watermark we stored — so steady-state cost is 1 subprocess/cycle
    # plus one per chat that genuinely changed, regardless of total chat count.
    watermarks = state.setdefault("watermarks", {})  # chat id -> last seen msg time
    chats = teams("chats", "-n", "40") or []
    # self-chat is invisible to `chats`; append it as a synthetic entry read by id
    chats = list(chats) + [{"id": SELF_CHAT_ID, "display_num": SELF_CHAT_ID,
                             "topic": SELF_CHAT_TITLE, "last_message_time": None}]
    for ch in chats:
        cid = ch.get("id"); num = ch.get("display_num")
        title = ch.get("topic") or ch.get("last_message_sender") or cid
        if cid is None or num is None:
            continue
        lmt = ch.get("last_message_time") or ""
        # self-chat has no list timestamp -> always read it (can't watermark-skip)
        is_self = (cid == SELF_CHAT_ID)
        if not is_self:
            if not post and lmt:
                watermarks[cid] = lmt   # prime: record without reading
                continue
            if lmt and watermarks.get(cid) == lmt:
                continue                # unchanged -> skip
        # per-chat isolation: one unreadable chat must not abort the whole poll
        try:
            msgs = teams("chat", str(num), "-n", "8") or []
        except Exception:
            continue
        if not is_self:
            watermarks[cid] = lmt
        for m in msgs:
            mid = m.get("id") or f"{cid}:{m.get('timestamp')}"
            # reactions change on ALREADY-delivered messages, so mirror them
            # before the seen-skip below (only for messages we posted to Telegram).
            if post:
                mirror_reactions_to_tg(m)
            if mid in seen:
                continue
            seen.add(mid)
            if not post:
                continue
            if m.get("is_from_me"):
                if not ECHO_SELF:
                    continue
                # skip messages the bridge itself sent (avoid echo loop)
                if was_bridge_sent(m.get("text_content") or m.get("content") or ""):
                    continue
                # if this own-message's attachment matches a file we just
                # uploaded to this chat, it's our echo -> skip.
                fns = att_filenames(m)
                if fns and was_bridge_file(cid, fns):
                    continue
            try:
                tid = topic_for_chat(cid, title)
                m["_chat_id"] = cid           # for tg->teams reply mapping
                deliver_message(m, tid)
            except Exception as e:
                print(f"[in] deliver {cid[:20]}: {e}", flush=True)
    state["seen"] = list(seen)[-2000:]
    save_state(state)

# inline <img src="..."> in message HTML
IMG_SRC = re.compile(r'<img[^>]+src="(https?://[^"]+)"', re.I)
def is_emoji_img(tag_ctx):
    return "schema.skype.com/Emoji" in tag_ctx or "animated-emoticon" in tag_ctx

# Teams emoticons render as <img itemtype=".../Emoji" ... alt="😉"> and the
# message's text_content DROPS them entirely — so "petit 👍 mdrr" arrives as
# "petit mdrr" and an emoji-only message arrives empty ([non-text message]).
# Rebuild the text from `content`: substitute each emoji <img> with its alt="",
# drop any non-emoji <img>, then strip remaining tags — keeping emoji inline in
# the right spot.
_RE_IMG = re.compile(r'<img\b[^>]*>', re.I)
_RE_ALT = re.compile(r'\balt="([^"]*)"', re.I)
_RE_BLOCK_BREAK = re.compile(r'<br\s*/?>|</p>|</div>|</li>', re.I)

# Teams formatting tags -> the single-letter Telegram tag they map to. We can't
# html.escape the whole rendered string (it'd break real <b>…</b>) nor leave it
# raw (injection). So each known tag becomes a \x00-sentinel, ALL text is escaped
# once, then sentinels swap back to real Telegram tags. \x00 can't occur in Teams
# HTML text, so it's a safe marker that survives html.escape untouched.
_FMT = {"strong": "b", "b": "b", "em": "i", "i": "i", "u": "u",
        "s": "s", "strike": "s", "del": "s", "code": "c", "pre": "p"}
_SENT = {"b": "b", "i": "i", "u": "u", "s": "s", "c": "code", "p": "pre"}
_RE_FMT = re.compile(r'<(/?)(' + "|".join(_FMT) + r')\b[^>]*>', re.I)
_RE_MENTION = re.compile(
    r'<span[^>]*schema\.skype\.com/Mention[^>]*>(.*?)</span>', re.I | re.S)
_RE_SENT = re.compile('\x00(/?)([biuscp])\x00')

TG_LIMIT = 4096                          # Telegram's hard per-message char cap

def split_html(s):
    """Split an HTML message body into pieces each <= TG_LIMIT chars, never
    cutting a tag and reopening <pre>/<code> across a boundary so every piece is
    valid standalone HTML. Telegram rejects (200 {"ok":false}) anything longer,
    which used to drop big code blocks silently.
    ponytail: only tracks pre/code (the tags that realistically span 4096 chars);
    a bold/italic run that long would split mid-tag — widen the state if it ever
    happens."""
    if len(s) <= TG_LIMIT:
        return [s]
    budget = TG_LIMIT - 32               # headroom for the reopen/close wrappers
    chunks, buf = [], ""
    in_pre = in_code = False
    reopen = lambda: ("<pre>" if in_pre else "") + ("<code>" if in_code else "")
    close  = lambda: ("</code>" if in_code else "") + ("</pre>" if in_pre else "")
    def flush():
        nonlocal buf
        chunks.append(buf + close())
        buf = reopen()
    for tok in re.split(r'(<[^>]+>)', s):
        if not tok:
            continue
        if tok.startswith("<") and tok.endswith(">"):     # a tag, keep intact
            if len(buf) + len(tok) > budget:
                flush()
            buf += tok
            low = tok.lower()
            if   low.startswith("<pre"):  in_pre = True
            elif low == "</pre>":         in_pre = False
            elif low.startswith("<code"): in_code = True
            elif low == "</code>":        in_code = False
        else:                                              # text: pack in units
            # render_text has escaped this text, so break on entity boundaries —
            # slicing mid "&amp;" yields a dangling entity Telegram rejects (400).
            # Each unit is one whole entity or a single char (both <= budget).
            for unit in re.findall(r'&[#\w]+;|.', tok, re.S):
                if len(buf) + len(unit) > budget:
                    flush()
                buf += unit
    if buf and buf != reopen():
        chunks.append(buf + close())
    return chunks

def render_text(content):
    """Teams message HTML -> Telegram-ready HTML (already escaped for
    parse_mode=HTML). Emoji preserved inline (from <img alt="">), bold/italic/
    underline/strike/code/pre converted, @mentions rendered as <b>@Name</b>,
    all other tags dropped."""
    def repl(mo):
        tag = mo.group(0)
        if is_emoji_img(tag):
            ma = _RE_ALT.search(tag)
            return ma.group(1) if ma else ""
        return ""                       # non-emoji image: handled elsewhere
    s = _RE_IMG.sub(repl, content or "")
    s = _RE_MENTION.sub(
        lambda m: f"\x00b\x00@{strip_tags(m.group(1))}\x00/b\x00", s)
    s = _RE_FMT.sub(lambda m: f"\x00{m.group(1)}{_FMT[m.group(2).lower()]}\x00", s)
    s = _RE_BLOCK_BREAK.sub("\n", s)     # </p>, <br>, </div>, </li> -> newline
    s = _RE_TAGS.sub("", s)              # drop remaining (unknown) tags
    s = html.escape(html.unescape(s))    # normalize entities, then escape text once
    s = _RE_SENT.sub(lambda m: f"<{m.group(1)}{_SENT[m.group(2)]}>", s)
    # collapse the blank lines the block->\n substitution can leave
    return "\n".join(line.rstrip() for line in s.split("\n")).strip()

# Teams "reply" messages embed a <blockquote itemtype=".../Reply"> holding the
# quoted author (<strong itemprop="mri">) and quoted text (<p itemprop="preview">),
# followed by the actual reply. text_content mashes all three together with no
# separators, so we parse them out and render a proper Telegram quote instead.
_RE_QUOTE = re.compile(
    r'<blockquote[^>]*schema\.skype\.com/Reply.*?</blockquote>', re.I | re.S)
_RE_QUOTE_AUTHOR = re.compile(r'<strong[^>]*itemprop="mri"[^>]*>(.*?)</strong>', re.I | re.S)
_RE_QUOTE_PREVIEW = re.compile(r'itemprop="preview"[^>]*>(.*?)</p>', re.I | re.S)
_RE_TAGS = re.compile(r'<[^>]+>')

def strip_tags(s):
    return _RE_TAGS.sub("", s or "").strip()

def format_reply(content):
    """If `content` is a Teams reply, return HTML with the quote rendered as a
    Telegram blockquote above the reply text. Returns None if it isn't a reply."""
    mq = _RE_QUOTE.search(content or "")
    if not mq:
        return None
    block = mq.group(0)
    ma = _RE_QUOTE_AUTHOR.search(block)
    author = strip_tags(ma.group(1)) if ma else ""
    mp = _RE_QUOTE_PREVIEW.search(block)
    quoted = strip_tags(mp.group(1)) if mp else ""
    # the reply body is everything AFTER the blockquote
    reply = strip_tags(content[mq.end():])
    q_head = html.escape(author) + (": " if author and quoted else "")
    parts = []
    if author or quoted:
        parts.append(f"<blockquote>{q_head}{html.escape(quoted)}</blockquote>")
    if reply:
        parts.append(html.escape(reply))
    return "\n".join(parts) if parts else None

def ic3_token():
    try:
        return json.load(open(CACHE)).get("ic3")
    except Exception:
        return None

def fetch_hosted_image(url):
    """Download a Teams-hosted image (asyncgw/AMS) with the ic3 bearer token.
    Returns a local file path, or None."""
    tok = ic3_token()
    if not tok:
        return None
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req) as r:
            data = r.read()
            ctype = r.headers.get("content-type", "")
    except Exception as e:
        print(f"[img] fetch {url[:50]}: {e}", flush=True)
        return None
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
           "image/webp": ".webp"}.get(ctype.split(";")[0], ".img")
    fd, path = tempfile.mkstemp(suffix=ext, prefix="tbimg-")
    os.write(fd, data); os.close(fd)
    return path

def deliver_message(m, tid):
    sender  = m.get("sender") or "?"
    content = m.get("content") or ""
    text    = (m.get("text_content") or "").strip()
    header  = f"<b>{html.escape(sender)}</b>"
    sent_photo = False

    # 1) inline images in the message HTML
    for mo in IMG_SRC.finditer(content):
        start = max(0, mo.start()-120)
        if is_emoji_img(content[start:mo.end()]):
            continue                      # skip emoji/emoticon imgs
        url = mo.group(1)
        cap = header if not sent_photo else ""
        if "teams.microsoft.com" in url or "asyncgw" in url or "sharepoint" in url:
            # Teams-hosted: needs bearer token -> download then upload
            fp = fetch_hosted_image(url)
            if fp:
                if tg_photo(tid, fp, caption=cap):
                    sent_photo = True
                try: os.unlink(fp)
                except Exception: pass
        else:
            # public URL (giphy etc): let Telegram fetch it
            if tg_photo_url(tid, url, caption=cap):
                sent_photo = True

    # 2) real file attachments (uploaded docs/photos). Note the attachment's
    # name/type directly from the message; download via teams-cli by message id
    # is racy (display_num shifts between the list read and this call), so we
    # only surface a link when we can't reliably fetch bytes.
    num = m.get("display_num")
    atts = m.get("attachments") or []
    if num is not None and atts:
        d = tempfile.mkdtemp(prefix="tbatt-")
        try:
            teams("attachments", str(num), "-d", "--save-to", d)
        except Exception as e:
            print(f"[img] download {num}: {e}", flush=True)
        got = sorted(glob.glob(os.path.join(d, "*")))
        if not got:
            # couldn't fetch bytes — post the file name + link so nothing is lost
            for a in atts:
                nm = a.get("name") or "file"
                url = a.get("content_url") or ""
                tg("sendMessage", chat_id=TG_GROUP_ID, message_thread_id=tid,
                   text=f"{header}: 📎 {html.escape(nm)}" + (f'\n{html.escape(url)}' if url else ""),
                   parse_mode="HTML")
                sent_photo = True   # header consumed
        for fp in got:
            ext = os.path.splitext(fp)[1].lower()
            if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                if tg_photo(tid, fp, caption=header if not sent_photo else ""):
                    sent_photo = True
            else:
                try:
                    tg_document(tid, fp, caption=header)
                except Exception as e:
                    print(f"[file] {fp}: {e}", flush=True)

    # 3) text. Reply messages get the quote rendered separately; everything else
    # is rebuilt from `content` so inline emoji are preserved (text_content drops
    # them). Fall back to the raw text_content if content rendering is empty.
    quoted = format_reply(content)       # None unless it's a reply
    rendered = render_text(content) if not quoted else None  # final TG HTML
    # rendered is already escaped; the raw text_content fallback is not.
    text = rendered if rendered else (text and html.escape(text))
    if text or quoted:
        body = f"{header}:\n{quoted}" if quoted else f"{header}: {text}"
        # Big code blocks blow past Telegram's 4096 cap; split into valid HTML
        # pieces. Map the *first* piece's id so replies still thread correctly.
        r = None
        for i, piece in enumerate(split_html(body)):
            sent = tg("sendMessage", chat_id=TG_GROUP_ID, message_thread_id=tid,
                      text=piece, parse_mode="HTML")
            if i == 0:
                r = sent
        # remember tg message -> teams message so a Telegram reply can become a
        # Teams reply to this exact message.
        try:
            map_tg_message((r or {}).get("result", {}).get("message_id"),
                           m.get("_chat_id"), m.get("id"))
        except Exception:
            pass
    elif not sent_photo:
        # non-empty message we couldn't render (sticker/card) — note it
        tg("sendMessage", chat_id=TG_GROUP_ID, message_thread_id=tid,
           text=f"{header}: <i>[non-text message]</i>", parse_mode="HTML")

def inbound_loop():
    try:
        poll_inbound(post=False)  # prime: mark current as seen (no flood)
        print("[in] primed", flush=True)
    except Exception as e:
        print(f"[in] prime: {e}", flush=True)
    while True:
        try:
            poll_inbound()
        except Exception as e:
            print(f"[in] {e}", flush=True)
        time.sleep(POLL_SEC)

# --- outbound: Telegram topic reply -> Teams -------------------------------
def tg_download_file(file_id, want_name=None):
    """Download a Telegram file to a temp dir under a CLEAN name (that name is
    what Teams shows as the attachment). Returns the path or None."""
    try:
        r = tg("getFile", file_id=file_id)
        fp = r["result"]["file_path"]
    except Exception as e:
        print(f"[out-img] getFile: {e}", flush=True); return None
    url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{fp}"
    ext = os.path.splitext(fp)[1] or ".bin"
    # basename: want_name is attacker-controlled (Telegram doc.file_name); without
    # it a name like "../../../.bashrc" would escape the temp dir on os.open.
    name = os.path.basename(want_name or "") or f"photo{ext}"
    d = tempfile.mkdtemp(prefix="tgdl-")
    path = os.path.join(d, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        with urllib.request.urlopen(url) as resp:
            os.write(fd, resp.read())
    except Exception as e:
        os.close(fd)
        import shutil; shutil.rmtree(d, ignore_errors=True)   # don't leak the dir
        print(f"[out-img] download: {e}", flush=True); return None
    os.close(fd)
    return path

def chat_num_for_id(cid):
    for ch in (teams("chats", "-n", "40") or []):
        if ch.get("id") == cid:
            return ch.get("display_num")
    return None

def _scan_chat(chat_num, n, pick):
    """Read the last `n` messages of a chat and return pick(msgs), or None on
    error. Shared by the two message-lookup helpers below."""
    try:
        return pick(teams("chat", str(chat_num), "-n", str(n)) or [])
    except Exception:
        return None

def msg_num_for_id(chat_num, teams_msg_id):
    """Current display_num of a Teams message by its stable id (or None)."""
    def pick(msgs):
        for m in msgs:
            if str(m.get("id")) == str(teams_msg_id):
                return m.get("display_num")
        return None
    return _scan_chat(chat_num, 30, pick)

def newest_own_msg_id(chat_num, text):
    """After sending, find the id of our just-created message (newest from-me
    message whose text matches). Lets us map an outbound Telegram msg -> Teams."""
    want = (text or "").strip()
    def pick(msgs):
        best = None
        for m in msgs:
            if not m.get("is_from_me"):
                continue
            tc = (m.get("text_content") or "").strip()
            # suffix, not equality: a reply's read-back text_content is the quoted
            # text + our body, so it ends with `want` (same as was_bridge_sent).
            if want and (tc == want or tc.endswith(want)):
                best = m.get("id")   # msgs chronological; keep the last (newest) match
        return best
    return _scan_chat(chat_num, 8, pick)

def handle_reaction_update(mr):
    """A Telegram message_reaction update -> add/remove the Teams reaction on the
    mapped message. mr has message_id, old_reaction, new_reaction (emoji lists)."""
    if str((mr.get("chat") or {}).get("id")) != str(TG_GROUP_ID):
        return
    mapped = lookup_tg_message(mr.get("message_id"))
    if not mapped:
        return
    cid, teams_msg_id = mapped
    def emojis(lst):
        return {r.get("emoji") for r in (lst or []) if r.get("type") == "emoji"}
    old, new = emojis(mr.get("old_reaction")), emojis(mr.get("new_reaction"))
    target = cid if cid == SELF_CHAT_ID else chat_num_for_id(cid)
    if target is None:
        return
    mnum = msg_num_for_id(target, teams_msg_id)
    if mnum is None:
        print(f"[react] teams msg {teams_msg_id} not in recent -> skip", flush=True)
        return
    for e in new - old:                      # added reactions
        tk = TG_TO_TEAMS_EMOJI.get(e)
        if tk:
            print(f"[react] +{tk} on teams #{mnum}", flush=True)
            teams_do("react", tk, str(mnum), "-y")
    for e in old - new:                      # removed reactions
        tk = TG_TO_TEAMS_EMOJI.get(e)
        if tk:
            print(f"[react] -{tk} on teams #{mnum}", flush=True)
            teams_do("unreact", tk, str(mnum), "-y")

def outbound_loop():
    offset = 0
    # message_reaction isn't in the default update set — ask for it explicitly.
    allowed = json.dumps(["message", "edited_message", "message_reaction"])
    while True:
        try:
            upd = tg("getUpdates", offset=offset, timeout=25, allowed_updates=allowed)
            for u in upd.get("result", []):
                offset = u["update_id"] + 1
                mr = u.get("message_reaction")
                if mr:
                    try:
                        handle_reaction_update(mr)
                    except Exception as e:
                        print(f"[react] {e}", flush=True)
                    continue
                msg = u.get("message") or {}
                if str(msg.get("chat", {}).get("id")) != str(TG_GROUP_ID):
                    continue
                tid = msg.get("message_thread_id")
                if not tid:
                    continue
                cid = state["topic_to_chat"].get(str(tid))
                if not cid:
                    continue
                target = cid if cid == SELF_CHAT_ID else chat_num_for_id(cid)
                if target is None:
                    tg("sendMessage", chat_id=TG_GROUP_ID, message_thread_id=tid,
                       text="⚠️ couldn't resolve Teams chat"); continue

                text    = msg.get("text", "") or ""
                caption = msg.get("caption", "") or ""
                # photo: list of sizes, take the largest (last). document: file too.
                photo   = (msg.get("photo") or [])
                doc     = msg.get("document")

                if photo or doc:
                    if photo:
                        file_id = photo[-1]["file_id"]; want = None  # -> photo.jpg
                    else:
                        file_id = doc["file_id"]
                        want = doc.get("file_name")  # keep the real doc name
                    path = tg_download_file(file_id, want)
                    if not path:
                        tg("sendMessage", chat_id=TG_GROUP_ID, message_thread_id=tid,
                           text="⚠️ couldn't download the file from Telegram"); continue
                    try:
                        args = ["send-file", str(target), path, "-y"]
                        if caption:
                            args = ["send-file", str(target), path, "-m", caption, "-y"]
                            mark_bridge_sent(caption)
                        mark_bridge_file(cid, os.path.basename(path))  # skip echo
                        teams_do(*args)
                    except Exception as e:
                        tg("sendMessage", chat_id=TG_GROUP_ID, message_thread_id=tid,
                           text=f"⚠️ file send failed: {str(e)[:120]}")
                    finally:
                        import shutil
                        shutil.rmtree(os.path.dirname(path), ignore_errors=True)
                    continue

                if not text or text.startswith("/"):
                    continue
                mark_bridge_sent(text)  # so the inbound poll won't echo it back
                # if this is a Telegram reply to a message we know, send it as a
                # Teams reply to that same message.
                rt = (msg.get("reply_to_message") or {}).get("message_id")
                mapped = lookup_tg_message(rt) if rt else None
                if rt and not mapped:
                    print(f"[out] reply to unmapped tg msg {rt} -> plain send", flush=True)
                mnum = msg_num_for_id(target, mapped[1]) if mapped else None
                # `--` terminates options so a message starting with '-' is sent
                # as text, not parsed as a teams-cli flag.
                if mnum is not None:
                    print(f"[out] reply -> teams msg #{mnum}", flush=True)
                    teams_do("reply", str(mnum), "-y", "--", text)
                else:
                    if mapped:
                        print(f"[out] reply target {mapped[1]} not in recent 30 "
                              f"-> plain send", flush=True)
                    teams_do("chat-send", str(target), "-y", "--", text)
                # map THIS telegram message -> the Teams message it created, so a
                # later Telegram reply to your own outgoing text also threads.
                # map_tg_message persists on the inbound loop's next save (~POLL_SEC),
                # keeping a single state-file writer (the inbound thread).
                my_id = msg.get("message_id")
                if my_id is not None:
                    tmid = newest_own_msg_id(target, text)
                    if tmid:
                        map_tg_message(my_id, cid, tmid)
        except Exception as e:
            print(f"[out] {e}", flush=True); time.sleep(3)

def main():
    missing = [k for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_GROUP_ID")
               if not os.environ.get(k)]
    if missing:
        sys.exit(f"error: set {', '.join(missing)} (see .env.example)")
    threading.Thread(target=refresh_loop, daemon=True).start()
    time.sleep(1)
    threading.Thread(target=inbound_loop, daemon=True).start()
    outbound_loop()

if __name__ == "__main__":
    main()
