#!/usr/bin/env python3
# Drive intune-container's sso-native-host over the Chrome native-messaging
# protocol: getAccounts, then acquireTokenSilently for the IC3 scope.
# Prints the ic3-audience JWT (or the broker error) so we can go/no-go the
# microsoft-teams-cli handoff.
import os, struct, json, subprocess, sys, base64

import shutil
HOST = os.environ.get("INTUNE_BIN") or shutil.which("intune-container") or os.path.expanduser("~/.local/bin/intune-container")
HOST_ARGS = ["native-host"]
IC3_SCOPE = "https://graph.microsoft.com/.default"

def send(proc, obj):
    data = json.dumps(obj).encode()
    proc.stdin.write(struct.pack("<I", len(data)) + data)
    proc.stdin.flush()

def recv(proc):
    raw = proc.stdout.read(4)
    if len(raw) < 4:
        err = proc.stderr.read().decode(errors="replace")
        raise SystemExit(f"host closed stdout early. stderr:\n{err}")
    (n,) = struct.unpack("<I", raw)
    return json.loads(proc.stdout.read(n))

def jwt_aud(tok):
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p)).get("aud")
    except Exception as e:
        return f"<decode failed: {e}>"

proc = subprocess.Popen([HOST] + HOST_ARGS, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# The host emits an initial broker-state message on startup; drain one.
try:
    first = recv(proc)
    print("startup msg:", json.dumps(first)[:200], file=sys.stderr)
except SystemExit as e:
    raise

def unwrap(r):
    # replies nest the payload under "message"
    m = r.get("message")
    return m if isinstance(m, dict) else r

send(proc, {"command": "getAccounts"})
acc_reply = unwrap(recv(proc))
accounts = acc_reply.get("accounts") or []
if not accounts:
    print("NO ACCOUNTS:", json.dumps(acc_reply)[:400])
    raise SystemExit(1)
account = accounts[0]
print("account username:", account.get("username"), file=sys.stderr)

send(proc, {"command": "acquireTokenSilently", "account": account,
            "scopes": [IC3_SCOPE]})
tok_reply = unwrap(recv(proc))

# Token can be under a few keys depending on broker version.
tok = (tok_reply.get("brokerTokenResponse", {}) or {}).get("accessToken") \
      or tok_reply.get("accessToken")
if tok:
    print("IC3_TOKEN_AUD:", jwt_aud(tok))
    print("IC3_TOKEN:", tok)
else:
    print("NO TOKEN. raw reply:")
    print(json.dumps(tok_reply, indent=2)[:1500])
