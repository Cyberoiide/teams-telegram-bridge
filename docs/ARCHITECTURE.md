# Architecture

## The problem

Organizations commonly enforce a Microsoft Entra **Conditional Access** policy
that only permits Teams on a managed browser running on an enrolled, compliant
device. On an unmanaged machine (or a plain headless server) sign-in is rejected
with error `53003` ("blocked by Conditional Access").

The bridge needs to talk to Teams from an always-on Linux server, so it has to
satisfy that policy without a human and without a real managed desktop.

## The token chain

```
┌─────────────────────────────────────────────────────────────────────┐
│  intune-container (rootless, on the server)                          │
│    Microsoft Identity Broker holds a device-bound PRT after a         │
│    one-time interactive Intune/Entra enrollment (Workplace Join).     │
│    Exposes acquirePrtSsoCookie / acquireTokenSilently over D-Bus.     │
└───────────────┬───────────────────────────────────────────────────────┘
                │  PRT SSO cookie (x-ms-RefreshTokenCredential)
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  token_mint.py  (Playwright + headless Chromium)                     │
│    1. get PRT SSO cookie from the broker (native-messaging host)      │
│    2. inject it as a header on login.microsoftonline.com requests     │
│    3. load teams.microsoft.com → CA sees a compliant device →         │
│       silent sign-in, NO MFA prompt                                   │
│    4. scrape the MSAL access tokens from the page's localStorage:     │
│         • ic3.teams.office.com   (chat read/send)                     │
│         • graph.microsoft.com    (file upload, user search)           │
└───────────────┬───────────────────────────────────────────────────────┘
                │  ic3 + graph JWTs (valid ~24h)
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  microsoft-teams-cli  (token cache: ~/.cache/teams-cli/tokens.json)  │
│    Talks to Teams' internal IC3 chat API. Read chats/messages,        │
│    send messages, download attachments, upload files (via Graph).     │
└───────────────┬───────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  bridge.py                                                            │
│    • inbound loop : poll chats → post new messages to Telegram topics │
│    • outbound loop: Telegram replies → send to Teams                  │
│    • refresh loop : re-mint tokens before they expire                 │
└───────────────────────────────────────────────────────────────────────┘
```

## Why not the Microsoft Graph API directly?

The clean, official path (Graph change-notifications / `getAllMessages`) needs
**admin-consented application permissions** and a public webhook — unavailable to
a regular user in a locked-down tenant. Delegated Graph polling is possible but
often blocked by tenant user-consent and Conditional Access policy. The internal
IC3 path used here is what the real Teams web client uses, so it works with the
same permissions a normal user already has.

## Why the broker can't mint the IC3 token directly

The intune-container broker issues tokens as the **Edge** first-party client id.
Microsoft's AAD rejects a request for the `ic3.teams.office.com` resource from a
non-Teams client (`invalid_request`), regardless of redirect URI or scope. So
instead of asking the broker for the IC3 token, we ask it only for the **PRT SSO
cookie** (which it will issue), and let the real Teams web client acquire the IC3
token itself inside the browser — where it's a first-party request that succeeds.

## Message → Telegram mapping

- Each Teams chat id maps to one Telegram forum **topic**, created on first
  message and remembered in `state.json` (`chat_to_topic` / `topic_to_chat`).
- Inbound images: inline hosted Teams images are fetched with the IC3 bearer
  token; file attachments via `teams attachments`. Both re-uploaded to Telegram.
- Outbound images: the Telegram file is downloaded, then `teams send-file`
  uploads it to OneDrive and attaches it (requires the Graph token).
- An echo guard (`sent_from_bridge`) prevents a Telegram reply from being
  re-mirrored back into Telegram when the poll later sees it in Teams.

## Efficiency

The inbound poll makes **one** `teams chats` list call per cycle and compares
each chat's `last_message_time` against a stored watermark. Only chats that
actually changed are opened. Steady-state cost is one subprocess per cycle plus
one per genuinely-updated chat — independent of total chat count.
