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

# text we just sent to Teams via an outbound Telegram reply; skip echoing these.
sent_from_bridge = {}  # text -> expiry epoch
def mark_bridge_sent(text):
    sent_from_bridge[text.strip()] = time.time() + 120
def was_bridge_sent(text):
    t = text.strip(); exp = sent_from_bridge.get(t)
    if exp and exp > time.time():
        return True
    # opportunistic cleanup
    for k, v in list(sent_from_bridge.items()):
        if v < time.time():
            sent_from_bridge.pop(k, None)
    return False

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

def tg(method, **params):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode()
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data)) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                body = json.load(e) if e.headers.get("content-type","").startswith("application/json") else {}
                wait = (body.get("parameters") or {}).get("retry_after", 3)
                time.sleep(wait + 1); continue
            raise
    raise RuntimeError(f"tg {method}: gave up after 429s")

def tg_photo(thread_id, path, caption=""):
    """Upload a local image file to a topic via multipart/form-data."""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    boundary = "----tgbridge" + str(int(time.time()*1000))
    fields = {"chat_id": str(TG_GROUP_ID), "message_thread_id": str(thread_id)}
    if caption:
        fields["caption"] = caption[:1000]
        fields["parse_mode"] = "HTML"
    body = b""
    for k, v in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    with open(path, "rb") as f:
        data = f.read()
    fn = os.path.basename(path) or "image"
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{fn}\"\r\n"
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

def tg_document(thread_id, path, caption=""):
    """Upload a local non-image file to a topic as a document."""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument"
    boundary = "----tgbridgeD" + str(int(time.time()*1000))
    fields = {"chat_id": str(TG_GROUP_ID), "message_thread_id": str(thread_id)}
    if caption:
        fields["caption"] = caption[:1000]; fields["parse_mode"] = "HTML"
    body = b""
    for k, v in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    with open(path, "rb") as f:
        data = f.read()
    fn = os.path.basename(path) or "file"
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{fn}\"\r\n"
             f"Content-Type: application/octet-stream\r\n\r\n").encode()
    body += data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

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
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, "w"))

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
                         "region": REGION, "user_id": c.get("oid"),
                         "presence": "", "csa": "", "substrate": ""})
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
                deliver_message(m, tid)
            except Exception as e:
                print(f"[in] deliver {cid[:20]}: {e}", flush=True)
    state["seen"] = list(seen)[-2000:]
    save_state(state)

# inline <img src="..."> in message HTML
IMG_SRC = re.compile(r'<img[^>]+src="(https?://[^"]+)"', re.I)
def is_emoji_img(tag_ctx):
    return "schema.skype.com/Emoji" in tag_ctx or "animated-emoticon" in tag_ctx

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

    # 3) text (send if there is real text, or if no photo carried the header)
    if text:
        tg("sendMessage", chat_id=TG_GROUP_ID, message_thread_id=tid,
           text=f"{header}: {html.escape(text)}", parse_mode="HTML")
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
    name = want_name or f"photo{ext}"        # e.g. photo.jpg, not tgdl-xxxx.jpg
    d = tempfile.mkdtemp(prefix="tgdl-")
    path = os.path.join(d, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        with urllib.request.urlopen(url) as resp:
            os.write(fd, resp.read())
    except Exception as e:
        os.close(fd); print(f"[out-img] download: {e}", flush=True); return None
    os.close(fd)
    return path

def chat_num_for_id(cid):
    for ch in (teams("chats", "-n", "40") or []):
        if ch.get("id") == cid:
            return ch.get("display_num")
    return None

def outbound_loop():
    offset = 0
    while True:
        try:
            upd = tg("getUpdates", offset=offset, timeout=25)
            for u in upd.get("result", []):
                offset = u["update_id"] + 1
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
                teams_do("chat-send", str(target), text, "-y")
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
