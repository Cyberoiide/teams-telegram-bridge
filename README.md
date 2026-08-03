# teams-telegram-bridge

Read and reply to your Microsoft Teams chats from Telegram — including from your
phone — when your organization restricts Teams to a managed browser.

Each Teams chat becomes its own **Telegram forum topic**. Messages sync both
ways — text, images, replies, reactions, and formatting included.

```
Microsoft Teams  ⇄  [ bridge on your server ]  ⇄  Telegram (one topic per chat)
```

---

## ⚠️ Read this first

This tool automates access to Microsoft Teams through **undocumented internal
APIs** and routes your corporate messages through infrastructure **you** run.

- It very likely conflicts with your employer's acceptable-use / security policy
  and with Microsoft's terms of service. **Check with your IT/security team.**
- Corporate messages leaving Teams into your own server + a Telegram bot is a
  real data-governance exposure (DLP, confidentiality, possibly regulated data).
- It rides internal endpoints that **can change without notice** and break it.
- Your admin can detect and revoke access; misuse can be a disciplinary matter.

Provided as-is, for educational and personal-productivity use. **You are
responsible for using it within your organization's rules and the law.**

---

## How it works

Many orgs enforce a Conditional Access policy that only lets Teams run in a
managed browser (e.g. Edge) on an enrolled, compliant device. This project
satisfies that policy from a headless Linux server instead:

1. **[intune-container](https://github.com/magicabdel/intune-container)** runs
   Microsoft's Intune agent + identity broker in a rootless container. After a
   one-time interactive enrollment, the broker holds a device-bound **Primary
   Refresh Token (PRT)** and can issue a **PRT SSO cookie** silently.
2. `token_mint.py` injects that PRT SSO cookie into a headless Chromium
   (Playwright), loads `teams.microsoft.com`, and — because Conditional Access
   now sees a compliant device — completes sign-in with no MFA prompt. It then
   reads the genuine `ic3.teams.office.com` (chat) and `graph.microsoft.com`
   (file upload) access tokens out of the page.
3. Those tokens feed
   [microsoft-teams-cli](https://github.com/yusufaltunbicak/microsoft-teams-cli),
   which talks to Teams' internal IC3 chat API.
4. `bridge.py` polls Teams for new messages → posts them into per-chat Telegram
   topics, and sends your Telegram replies (text + images) back to Teams. Tokens
   are re-minted automatically before they expire (~24 h).

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full picture.

## Features

- ✅ Two-way sync: Teams ⇄ Telegram
- ✅ One Telegram **forum topic per Teams chat** (1:1, group, self-notes)
- ✅ **Reply threading** both ways — a Telegram reply becomes a Teams reply to the same message
- ✅ **Reactions** both ways (👍 ❤ 😁 😱 😢 😡 — Telegram's supported set)
- ✅ **Rich text** — bold/italic/underline/strike, inline code, code blocks, @mentions
- ✅ **Emoji** preserved inline (Teams emoticons → unicode)
- ✅ Inbound images (inline hosted Teams images + file attachments)
- ✅ Outbound images/files (Telegram photo/document → Teams)
- ✅ Long messages (big code blocks) split to fit Telegram's 4096-char limit
- ✅ Silent, headless token refresh — no repeated MFA after first enrollment
- ✅ Scales by change-detection (one list call per poll; only opens chats that changed)

## Commands

Type these in Telegram (`/help` lists them; the main ones autocomplete in the `/` menu). Most run in the group's **General** topic; `/del` and `/mute` run **inside a chat's own topic**.

| Command | Where | What |
|---------|-------|------|
| `/dm <who> <message>` | General | Start a new 1:1 chat by name or email (alias `/to`). Their reply appears as a new topic. |
| `/group <a, b, …> \| <message>` | General | Start a group chat — comma-separated people, optional first message after a pipe. |
| `/chats` | General | List your recent Teams chats (🔕 marks muted ones). |
| `/search <words>` | General | Search your Teams messages (alias `/find`). |
| `/mute` / `/unmute` | in a topic | Stop / resume mirroring that chat. |
| `/del` | in a topic | Reply to a message **you** sent to unsend it in Teams (alias `/unsend`). |
| `/help` | anywhere | Show the command list. |

Everything else just works: reply in a topic to answer that chat, react to mirror the reaction, send a photo/file, edit a Teams message to update it in Telegram.

## Requirements

- A Linux host (an always-on server/VM) with the
  [intune-container prerequisites](https://github.com/magicabdel/intune-container)
  (unprivileged user namespaces, cgroup v2, `uidmap`).
- Python 3.10+, `pipx`, Playwright + Chromium.
- A Microsoft 365 / Teams work account.
- A Telegram bot + a Topics-enabled supergroup.

## Quick start

```sh
# 1. deps
pipx install microsoft-teams-cli
pip install -r requirements.txt
playwright install --with-deps chromium      # --with-deps: system libs Chromium needs

# 2. a virtual display :99 — the broker + Playwright use it (headless server).
#    Runs the whole way through; enrollment (step 3) needs it on screen via VNC.
sudo apt-get install -y xvfb
Xvfb :99 -screen 0 1280x800x24 &
export DISPLAY=:99

# 3. intune-container: install + enroll ONCE (interactive — sign in + MFA).
#    On a headless box you view :99 over VNC — see docs/SETUP.md for that.
curl -fsSL https://raw.githubusercontent.com/magicabdel/intune-container/master/install.sh | sh
intune-container enroll      # sign in + approve MFA once, in the :99 window
intune-container start       # headless from here on

# 4. configure
cp .env.example .env         # fill in bot token, group id, region

# 5. verify the token path works end-to-end
DISPLAY=:99 python3 token_mint.py   # should print IC3_TOKEN_OK + GRAPH_TOKEN_OK

# 6. run
set -a && . ./.env && set +a
python3 bridge.py
```

**The enrollment in step 3 is interactive and is the one part this snippet
can't do for you** — on a headless server you expose `:99` over VNC to click
through the Microsoft sign-in. Full walkthrough (VNC setup, prerequisites like
user-namespaces/`uidmap`, Telegram bot + group id): **[docs/SETUP.md](docs/SETUP.md)**.
For running it 24/7 and getting pinged if it breaks, see
[Running as a service](#running-as-a-service).

## Configuration

All config is via environment variables — see [`.env.example`](.env.example).

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_GROUP_ID` | Topics-enabled supergroup id (bot must be admin) |
| `TEAMS_REGION` | `emea` / `amer` / `apac` |
| `ECHO_SELF` | Mirror your own sent Teams messages too (default 1) |
| `POLL_SEC` | New-message poll interval (default 5) |
| `REFRESH_SEC` | Token re-mint interval (default 72000 = 20 h) |

## Running as a service

To survive reboots and auto-restart on crash, install the user systemd units in
[`systemd/`](systemd/) (a virtual display unit + the bridge unit). See the
comments in those files. Enable lingering (`loginctl enable-linger "$USER"`) so
they run without an active login.

### Health watchdog (get pinged when it breaks — and told when it's fine)

The bridge can die in ways it can't report itself — crash, OOM, reboot, or the
Teams token silently going invalid (a device-compliance lapse; see
[docs/RUNBOOK-token-recovery.md](docs/RUNBOOK-token-recovery.md)). Install the
watchdog timer to get **Telegram status messages**:

```sh
cp systemd/watchdog.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now watchdog.timer
```

Every 5 minutes `tools/watchdog.sh` checks five things:

| Check | Catches |
|---|---|
| service is active | crash, OOM, reboot, stopped |
| `state.json` advancing | alive but wedged — the case `is-active` hides |
| `teams auth-status` valid | token dead |
| container keyring not locked | the keyring re-locks on its own; the broker then drops off the bus and every token call fails. Named separately because it looks like an auth failure but the fix is `intune-container stop && intune-container start` — a bare `start` short-circuits on a running container and does **not** unlock it |
| device still compliant in Entra | **the only check that fires before messages stop** — see below |

That last one is the useful one. Compliance lapses up to ~24h *before* the token
already in hand expires, and nothing else notices in that window: the service is
active, the poll is advancing, `auth-status` still says valid, and
`intune-container doctor` is all green because it never asks Entra about
compliance. `tools/compliance_check.py` asks Entra directly (broker mints a
device-bound Graph token in ~1s, its `deviceid` claim identifies the device,
Graph reports `isCompliant`), turning a silent day-long fuse into a warning. Run
it by hand any time:

```sh
tools/compliance_check.py     # 0 = compliant, 1 = NOT, 2 = cannot tell
```

What the watchdog sends:

| When | Message |
|---|---|
| something breaks | 🔴 `Teams bridge DOWN:` + which check failed + link to the runbook |
| still broken | the same alert again every `BEAT_BAD_SEC` (default **6h**) until fixed |
| back to healthy | 🟢 `Teams bridge recovered` |
| healthy, quietly | 🟢 `Teams bridge up — last poll Ns ago, token expires in 23h 5m`, every `BEAT_OK_SEC` (default **24h**) |

The repetition is the point. A single alert is how one outage stayed unnoticed
for 10 days ([post-mortem](docs/incidents/2026-08-03-bridge-outage.md)) — the
alert fired correctly on day one and was simply missed. With a heartbeat,
**silence means the watchdog itself is dead**, which is information. Tune the two
intervals with `Environment=BEAT_OK_SEC=...` in `watchdog.service`.

It's a standalone script (bash + curl, reads the same `.env`), deliberately
separate from the bridge so it still alerts when the bridge is fully down.

## Tests

```sh
pip install pytest
python -m pytest
```

The suite covers the pure routing logic — echo-guard, image classification
(emoji vs hosted vs public), message delivery/escaping, and the poll loop's
change-detection and self-message handling — with all network/subprocess calls
stubbed, so no Teams/Telegram credentials are needed. CI runs on 3.10–3.12.

## Contributing

Hacking on it? See **[CONTRIBUTING.md](CONTRIBUTING.md)** — dev setup (no
credentials needed for the tests), the branch/PR flow, and conventions.

## Limitations

- **Bot messages are left-aligned.** Telegram bots can only post as themselves,
  so your own mirrored messages show your name but aren't right-aligned.
- **@mentions don't ping across platforms.** A Teams @mention renders as bold
  `@Name` text in Telegram (and vice-versa), but can't actually notify the other
  platform's user — the accounts aren't linked.
- **Reactions** are limited to the fixed set Telegram accepts (👍 ❤ 😁 😱 😢 😡);
  other Teams reactions aren't mirrored. A reaction added to an older message
  isn't mirrored until the next new message in that chat.
- **Poll latency** is a few seconds (polling, not push). Fine for chat.
- **Internal-API fragility** — a Teams update can break message parsing.
- Relies on the unofficial `microsoft-teams-cli` and internal IC3 endpoints.

## Credits

- [intune-container](https://github.com/magicabdel/intune-container) — compliant-device broker
- [microsoft-teams-cli](https://github.com/yusufaltunbicak/microsoft-teams-cli) — IC3 chat client
- [siemens/linux-entra-sso](https://github.com/siemens/linux-entra-sso) — the SSO broker protocol

## License

[MIT](LICENSE).
