#!/usr/bin/env python3
# Call the Microsoft Identity Broker over the container's D-Bus socket DIRECTLY,
# bypassing intune-container's native-host so we can set an arbitrary clientId.
# Goal: prove whether the Teams first-party client can mint an ic3 token from
# this device's PRT. Uses jeepney (pure python) on the raw unix socket.
import socket, glob, json, base64, sys
from jeepney import new_method_call, DBusAddress
from jeepney.io.blocking import open_dbus_connection

BROKER = DBusAddress("/com/microsoft/identity/broker1",
                     bus_name="com.microsoft.identity.broker1",
                     interface="com.microsoft.identity.Broker1")
PROTO = "0.0"
SESSION = "ic3-probe"

# client ids to try
EDGE  = "d7b530a4-7680-4c23-a8bf-c52c121d2e87"
TEAMS = "5e3ce6c0-2b1f-4285-8d4b-75ee78787346"
IC3   = "https://ic3.teams.office.com/.default"

def bus_path():
    for p in glob.glob("/proc/*/root/run/user/0/bus"):
        return p
    raise SystemExit("no container bus socket found")

def conn():
    # jeepney can open a connection to an explicit unix socket path
    return open_dbus_connection(bus=f"unix:path={bus_path()}")

def call(c, method, req_obj):
    req = json.dumps(req_obj)
    msg = new_method_call(BROKER, method, "sss", (PROTO, SESSION, req))
    reply = c.send_and_get_reply(msg)
    return json.loads(reply.body[0])

def unwrap(r):
    m = r.get("message")
    return m if isinstance(m, dict) else r

def aud(tok):
    p = tok.split(".")[1]; p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p)).get("aud")

def auth_params(account, client_id, scope):
    return {
        "account": account,
        "additionalQueryParametersForAuthorization": {},
        "authority": "https://login.microsoftonline.com/common",
        "authorizationType": 1,
        "clientId": client_id,
        "redirectUri": "https://login.microsoftonline.com/common/oauth2/nativeclient",
        "requestedScopes": [scope],
        "username": account.get("username"),
        "uxContextHandle": -1,
    }

c = conn()
accounts = unwrap(call(c, "getAccounts", {"clientId": EDGE, "redirectUri": SESSION})).get("accounts") or []
if not accounts:
    raise SystemExit("no accounts")
acc = accounts[0]
print("account:", acc.get("username"), file=sys.stderr)

for label, cid in [("TEAMS", TEAMS), ("EDGE", EDGE)]:
    r = unwrap(call(c, "acquireTokenSilently",
                    {"authParameters": auth_params(acc, cid, IC3)}))
    tok = (r.get("brokerTokenResponse") or {}).get("accessToken") or r.get("accessToken")
    if tok:
        print(f"[{label}] client={cid[:8]} -> TOKEN aud={aud(tok)}")
        print(f"[{label}] TOKEN={tok}")
    else:
        err = (r.get("brokerTokenResponse") or {}).get("error") or r
        ctx = err.get("context") if isinstance(err, dict) else err
        print(f"[{label}] client={cid[:8]} -> NO TOKEN: {ctx}")
