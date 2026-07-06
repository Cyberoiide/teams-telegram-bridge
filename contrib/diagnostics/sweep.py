#!/usr/bin/env python3
# Sweep broker authParameters combos for an IC3-accepted token.
import struct, json, base64, subprocess, os
HOST = os.path.expanduser("~/intune-container/target/release/intune-container")

TEAMS = "5e3ce6c0-2b1f-4285-8d4b-75ee78787346"
EDGE  = "d7b530a4-7680-4c23-a8bf-c52c121d2e87"

def call(env, scope):
    e = {**os.environ, **env}
    p = subprocess.Popen([HOST, "native-host"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=e)
    def send(o): b=json.dumps(o).encode(); p.stdin.write(struct.pack("<I",len(b))+b); p.stdin.flush()
    def recv(): n=struct.unpack("<I",p.stdout.read(4))[0]; return json.loads(p.stdout.read(n))
    def uw(r): m=r.get("message"); return m if isinstance(m,dict) else r
    recv()
    send({"command":"getAccounts"}); acc=uw(recv())["accounts"][0]
    send({"command":"acquireTokenSilently","account":acc,"scopes":[scope]})
    r=uw(recv()); p.stdin.close(); p.terminate()
    tok=(r.get("brokerTokenResponse") or {}).get("accessToken") or r.get("accessToken")
    if tok:
        x=tok.split(".")[1]; x+="="*(-len(x)%4)
        return "OK aud="+str(json.loads(base64.urlsafe_b64decode(x)).get("aud")), tok
    err=(r.get("brokerTokenResponse") or {}).get("error") or {}
    tel=r.get("telemetry") or {}
    return f"ERR tag={err.get('tag')} {tel.get('api_error_tag','')} sub={err.get('subStatus')}", None

REDIRECTS = {
    "nativeclient": "https://login.microsoftonline.com/common/oauth2/nativeclient",
    "teams-ms":     "https://teams.microsoft.com/",
    "teams-cloud":  "https://teams.cloud.microsoft/",
    "msal-teams":   "msauth://com.microsoft.teams/...",  # mobile-ish, long shot
    "ng-teams":     "https://ng.msg.teams.microsoft.com/",
}
SCOPES = [
    "https://ic3.teams.office.com/.default",
    "https://ic3.teams.office.com/Teams.AccessAsUser.All",
    "https://api.spaces.skype.com/.default",
]
AUTH_COMMON = "https://login.microsoftonline.com/common"
AUTH_ORG    = "https://login.microsoftonline.com/organizations"

combos = []
for cid, cname in [(TEAMS,"teams"),(EDGE,"edge")]:
    for rname, r in REDIRECTS.items():
        for scope in SCOPES:
            combos.append((cname, cid, rname, r, scope, AUTH_COMMON))

best = None
for cname, cid, rname, r, scope, auth in combos:
    env = {"INTUNE_CLIENT_ID": cid, "INTUNE_REDIRECT_URI": r, "INTUNE_AUTHORITY": auth}
    try:
        res, tok = call(env, scope)
    except Exception as e:
        res, tok = f"EXC {e}", None
    sc = scope.split("/")[-1]
    print(f"{cname:5} {rname:12} {sc:28} -> {res}", flush=True)
    if tok and "ic3.teams.office.com" in res:
        best = tok
        open(os.path.expanduser("~/ic3.jwt"),"w").write(tok)
        print("  ^^^ IC3 TOKEN CAPTURED -> ~/ic3.jwt")
        break
print("\nRESULT:", "GOT IC3 TOKEN" if best else "no ic3 token in sweep")
