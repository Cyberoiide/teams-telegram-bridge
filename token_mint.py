#!/usr/bin/env python3
"""Get a genuine Teams-client IC3 token via the container's PRT SSO cookie.

The broker won't mint ic3 directly, but it DOES issue the device-bound PRT SSO
cookie that Conditional Access accepts. So: inject that cookie as the
`x-ms-RefreshTokenCredential` header on login.microsoftonline.com requests,
drive Teams web to auto-login as a compliant device, then read the real
ic3.teams.office.com token out of MSAL's localStorage. That token is exactly
what real Teams web uses -> IC3 accepts it.

"Won't mint ic3 directly" is re-tested, not folklore: on 2026-08-03 the broker
refused every Teams/Skype scope with AAD `invalid_request` across the Edge,
Office and Teams client ids and both scope spellings, while the same call minted
Graph fine. Details + how to reopen it in
docs/incidents/2026-08-03-bridge-outage.md.
"""
import base64, contextlib, struct, json, subprocess, os, sys, time

HOST = os.path.expanduser("~/intune-container/target/release/intune-container")

# Broker refusals that only a human can clear. These are the broker's own code
# strings; anything else stays unnamed on purpose, so an unfamiliar code never
# claims a remedy it doesn't have.
NEEDS_REENROLL = ("interaction_required", "interactive_required",
                  "token_expired", "invalid_grant")

def write_secret(path, data):
    """Write a token file 0600 — these are live bearer tokens; default umask
    would leave them world-readable in the home dir."""
    fd = os.open(os.path.expanduser(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(data)

def jwt_claims(tok):
    """Decode a JWT payload. Returns {} for anything unparseable."""
    try:
        pl = tok.split(".")[1]; pl += "=" * (-len(pl) % 4)
        return json.loads(base64.urlsafe_b64decode(pl))
    except Exception:
        return {}

@contextlib.contextmanager
def broker_session():
    """Talk to the container's identity broker over the native-host stdio
    protocol (4-byte little-endian length prefix + JSON). Yields
    call(command, **params) -> reply dict."""
    p = subprocess.Popen([HOST, "native-host"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    def recv():
        n = struct.unpack("<I", p.stdout.read(4))[0]
        return json.loads(p.stdout.read(n))
    def call(command, **params):
        b = json.dumps({"command": command, **params}).encode()
        p.stdin.write(struct.pack("<I", len(b)) + b); p.stdin.flush()
        r = recv(); m = r.get("message")
        return m if isinstance(m, dict) else r
    try:
        recv()            # the broker's opening brokerStateChanged frame
        yield call
    finally:
        p.stdin.close(); p.terminate()

def refusal(resp):
    """Name why the broker said no, or None if it didn't refuse.

    Worth the few lines: a mint that fails silently costs days (the 2026-08-03
    outage ran 10 of them), and the broker usually says exactly why. Only its
    "a human must sign in" codes get that verdict.
    """
    blob = json.dumps(resp)
    low = blob.lower()
    if '"error"' not in low and "errorcode" not in low:
        return None
    if any(c in low for c in NEEDS_REENROLL):
        return ("device can no longer sign in silently (compliance or PRT lapsed) "
                "— re-enroll, see docs/RUNBOOK-token-recovery.md")
    return f"broker refused: {blob[:200]}"

def prt_cookie():
    with broker_session() as call:
        acc = call("getAccounts")["accounts"][0]
        r = call("acquirePrtSsoCookie", account=acc,
                 ssoUrl="https://teams.microsoft.com/")
    items = r.get("cookieItems") or []
    if not items:
        raise SystemExit(f"no PRT cookie: {refusal(r) or json.dumps(r)[:300]}")
    c = items[0]
    # The broker's key is `cookieName`. Reading `name` here used to work only
    # because the fallback happened to match what it returns.
    return c.get("cookieName") or "x-ms-RefreshTokenCredential", c.get("cookieContent")

def broker_graph_token():
    """A device-bound Graph token straight from the broker — no browser, ~1s.

    Deliberately NOT used for the bridge's Graph calls: its scopes are narrower
    than the token Teams web caches (no People.Read, no Files.ReadWrite.All), so
    swapping would silently break user search and uploads. It exists for the
    device-compliance probe in tools/compliance_check.py, which only needs the
    `deviceid` claim.
    """
    with broker_session() as call:
        acc = call("getAccounts")["accounts"][0]
        r = call("acquireTokenSilently", account=acc)
    tok = (r.get("brokerTokenResponse") or {}).get("accessToken")
    if not tok:
        raise RuntimeError(refusal(r) or "broker returned no Graph token")
    return tok

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        sys.exit(f"error: playwright not installed for {sys.executable}. "
                 f"Run: {sys.executable} -m pip install playwright && "
                 f"{sys.executable} -m playwright install chromium")
    cookie_name, cookie_val = prt_cookie()
    print(f"[prt] cookie {cookie_name} len={len(cookie_val)}", file=sys.stderr)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context()

        # Inject the PRT SSO cookie header on every auth request -> CA sees a
        # compliant device and completes silent sign-in.
        def on_route(route):
            h = dict(route.request.headers)
            u = route.request.url
            if "login.microsoftonline.com" in u or "login.microsoft.com" in u:
                h[cookie_name] = cookie_val
            route.continue_(headers=h)
        ctx.route("**/*", on_route)

        def jwt_aud(tok):
            return jwt_claims(tok).get("aud")

        page = ctx.new_page()
        page.goto("https://teams.microsoft.com/", wait_until="domcontentloaded")
        # Collect ALL MSAL access tokens from localStorage, classify by audience.
        # We want ic3 (chat) and, if present, graph (file upload / user search).
        found = {}  # aud-substring -> jwt
        WANT = {"ic3": "ic3.teams.office.com", "graph": "graph.microsoft.com"}
        for i in range(30):  # up to ~150s
            time.sleep(5)
            try:
                toks = page.evaluate("""() => {
                    const out = {};
                    try {
                        for (let i=0;i<localStorage.length;i++){
                            const k = localStorage.key(i);
                            const v = localStorage.getItem(k) || "";
                            if (k && (k.toLowerCase().includes('accesstoken') ||
                                      v.includes('"secret"'))) out[k]=v;
                        }
                    } catch(e) {}
                    return out;
                }""")
            except Exception as e:
                print(f"[{i}] evaluate skipped (navigating): {str(e)[:60]}", file=sys.stderr)
                continue
            for k, v in (toks or {}).items():
                try:
                    obj = json.loads(v); sec = obj.get("secret") or obj.get("accessToken")
                except Exception:
                    sec = v
                if not sec or sec.count(".") != 2:
                    continue
                aud = jwt_aud(sec) or ""
                for name, needle in WANT.items():
                    if needle in aud and name not in found:
                        found[name] = sec
                        print(f"[{i}] captured {name} aud={aud}", file=sys.stderr)
            print(f"[{i}] url={page.url[:50]} have={list(found)}", file=sys.stderr)
            # ic3 is required; graph is a bonus. Stop once ic3 is in hand and we've
            # given graph a couple extra cycles to appear.
            if "ic3" in found and (i >= 6 or "graph" in found):
                break
        if "ic3" in found:
            write_secret("~/ic3.jwt", found["ic3"])
            print("IC3_TOKEN_OK len", len(found["ic3"]), "aud=", jwt_aud(found["ic3"]))
        if "graph" in found:
            write_secret("~/graph.jwt", found["graph"])
            print("GRAPH_TOKEN_OK len", len(found["graph"]), "aud=", jwt_aud(found["graph"]))
        else:
            print("GRAPH_TOKEN_MISSING (Teams web didn't cache a graph token)")
        if "ic3" in found:
            browser.close(); return
        # timed out - dump what we saw for debugging
        print("NO IC3 TOKEN. final url:", page.url)
        allkeys = page.evaluate("() => Object.keys(localStorage)")
        print("localStorage keys sample:", [k for k in allkeys if 'token' in k.lower() or 'ic3' in k.lower()][:10])
        browser.close()

if __name__ == "__main__":
    main()
