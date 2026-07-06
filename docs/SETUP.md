# Setup

End-to-end setup on a fresh Linux server (Ubuntu 24.04 assumed).

## 0. Prerequisites

```sh
# rootless-container prereqs for intune-container
sudo apt-get update
sudo apt-get install -y uidmap
# Ubuntu 24.04 restricts unprivileged user namespaces by default:
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
# (persist it)
echo "kernel.apparmor_restrict_unprivileged_userns=0" | sudo tee /etc/sysctl.d/99-userns.conf

# your user needs a subuid/subgid range starting at 100000
echo "$USER:100000:65536" | sudo tee -a /etc/subuid
echo "$USER:100000:65536" | sudo tee -a /etc/subgid
```

Python side:

```sh
sudo apt-get install -y python3 python3-venv pipx
pipx install microsoft-teams-cli
pip install --user playwright
python3 -m playwright install chromium
python3 -m playwright install-deps chromium
```

## 1. Install intune-container

```sh
curl -fsSL https://raw.githubusercontent.com/magicabdel/intune-container/master/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
# it's a GUI+CLI binary; on a headless server install the GUI runtime libs so
# the CLI can load:
sudo apt-get install -y libwayland-cursor0 libgtk-3-0 libwebkit2gtk-4.1-0 \
     libayatana-appindicator3-1 librsvg2-2
intune-container init        # downloads rootfs (prompts for an unused password)
```

## 2. Enroll once (interactive — needs a screen)

Enrollment opens the Intune Portal for interactive sign-in + MFA. On a headless
server, expose a virtual display over VNC just for this step:

```sh
sudo apt-get install -y xvfb x11vnc openbox novnc websockify
export DISPLAY=:99
Xvfb :99 -screen 0 1280x800x24 &
DISPLAY=:99 openbox &
x11vnc -display :99 -rfbport 5900 -nopw -localhost -forever -bg
# expose it in the browser (bind to a trusted interface, e.g. a VPN IP):
websockify --web=/usr/share/novnc <YOUR_TRUSTED_IP>:6080 localhost:5900 &
```

Open `http://<YOUR_TRUSTED_IP>:6080/vnc.html`, then:

```sh
DISPLAY=:99 intune-container enroll   # sign in + approve MFA in the VNC window
```

After it reports the device enrolled, you can tear down VNC — everything below
is headless. Keep the container running:

```sh
intune-container start
intune-container doctor       # should show: Registration ✓, broker ✓, keyring ✓
```

> **Alternative (no VNC):** enroll on your own Linux desktop with a screen, then
> `intune-container backup` and copy the archive to the server. **Note:** the
> PRT is device-bound, so a restored backup may not silently mint tokens on a
> different machine — enrolling directly on the server is the reliable path.

## 3. Configure the bridge

```sh
cp .env.example .env
$EDITOR .env      # TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_ID, TEAMS_REGION
```

Telegram side:
1. @BotFather → `/newbot` → copy the token into `TELEGRAM_BOT_TOKEN`.
2. @BotFather → `/setprivacy` → **Disable** (so the bot reads your topic replies).
3. Create a group → **Edit → Topics: ON** (upgrades it to a supergroup).
4. Add the bot, make it **Admin** with **Manage Topics**.
5. Send any message in the group, then:
   ```sh
   TELEGRAM_BOT_TOKEN=... python3 tools/get_group_id.py
   ```
   Copy the negative supergroup id into `TELEGRAM_GROUP_ID`.

## 4. Verify the token path

```sh
set -a && . ./.env && set +a
DISPLAY=:99 python3 token_mint.py
#   -> IC3_TOKEN_OK ... aud= https://ic3.teams.office.com
#   -> GRAPH_TOKEN_OK ... aud= https://graph.microsoft.com

# inject + live-check:
cat ~/ic3.jwt | teams login --with-token --region "$TEAMS_REGION"
teams auth-status --check          # ic3: valid
teams chats -n 5                    # your real chats
```

## 5. Run

```sh
set -a && . ./.env && set +a
python3 bridge.py
```

New Teams messages appear as topics in your group; reply in a topic to send
back. See [systemd/](../systemd) if you want it to survive reboots (optional).

## Troubleshooting

- **`teams` says "Auto re-login failed"** on send-file / send: the Graph token is
  missing or expired. Re-run `token_mint.py` (it captures both ic3 + graph) and
  re-inject.
- **No messages forwarding**: check `intune-container doctor` (broker/keyring),
  and that `token_mint.py` still returns a valid token (PRT can expire).
- **Enrollment window won't sign in**: Conditional Access sometimes blocks the
  device-code path; use the interactive portal (auth-code) as above.
- **VNC keyboard dead keys** (can't type `^`, accents): run `setxkbmap us` on the
  `:99` display, or paste via the noVNC clipboard.
