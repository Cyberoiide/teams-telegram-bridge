# teams-telegram-bridge

Read and reply to your Microsoft Teams chats from Telegram — including from your
phone — when your organization restricts Teams to a managed browser.

Each Teams chat becomes its own **Telegram forum topic**. Messages sync both
ways, text and images included.

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
playwright install chromium

# 2. intune-container: install + enroll once (interactive, needs a display).
#    See docs/SETUP.md for the headless VNC enrollment walkthrough.
curl -fsSL https://raw.githubusercontent.com/magicabdel/intune-container/master/install.sh | sh
intune-container enroll      # sign in + approve MFA once
intune-container start       # headless from here on

# 3. configure
cp .env.example .env         # fill in bot token, group id, region

# 4. verify the token path works end-to-end
DISPLAY=:99 python3 token_mint.py   # should print IC3_TOKEN_OK + GRAPH_TOKEN_OK

# 5. run
set -a && . ./.env && set +a
python3 bridge.py
```

Full step-by-step (including the headless enrollment): **[docs/SETUP.md](docs/SETUP.md)**.

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
