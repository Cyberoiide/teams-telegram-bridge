# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A bridge that mirrors Microsoft Teams chats to Telegram (both directions) so you can use Teams from your phone when your org restricts it to a managed browser. It works around Conditional Access by minting genuine Teams tokens on a headless server via the intune-container broker's PRT SSO cookie (see `docs/ARCHITECTURE.md` — read it before touching auth). Rides undocumented internal Teams (IC3) APIs; fragile by nature.

## Architecture (the parts that span files)

- **`bridge.py`** — the whole runtime, three threads started in `main()`:
  - `inbound_loop` → `poll_inbound`: polls `teams chats`/`chat` every `POLL_SEC`, mirrors new messages into per-Teams-chat Telegram **forum topics**. Reactions are mirrored here too (before the seen-skip). Only writer of `state.json`.
  - `outbound_loop`: Telegram `getUpdates` (long-poll) → sends replies/files/reactions back to Teams. `allowed_updates` must include `message_reaction`.
  - `refresh_loop`: re-mints tokens every `REFRESH_SEC` by running `token_mint.py`; on failure keeps the last valid token (degrades, doesn't wedge).
- **`token_mint.py`** — the auth trick: gets the device-bound PRT SSO cookie from the intune-container broker, injects it into headless Chromium (Playwright), drives `teams.microsoft.com` to a compliant-device silent login, scrapes the `ic3` + `graph` access tokens from MSAL localStorage. Run by `refresh_loop` as a subprocess with the SAME interpreter (`sys.executable`) — that interpreter MUST have `playwright` installed.
- **State & maps** (`state.json`, `~/.cache/teams-bridge/`): `chat_to_topic`/`topic_to_chat` (chat↔topic), `tg_to_teams` (Telegram msg → Teams msg, for reply threading; persisted, bounded), `seen` (dedup), `watermarks` (per-chat last_message_time, to skip unchanged chats). Two threads touch `state` — writes go through `STATE_LOCK` + atomic temp+`os.replace`.
- **teams-cli boundary**: `teams(*args)` = read commands (append `--json`, parse the `{ok,data}` envelope). `teams_do(*args)` = mutating commands (NO `--json` — they reject it). User text passed after `--` so a leading `-` isn't parsed as a flag.
- **Rendering**: Teams sends HTML; `render_text` converts emoji (`<img alt>`), bold/italic/code/pre, @mentions → Telegram HTML, escaping once via `\x00` sentinels. `format_reply` parses the reply blockquote. Telegram caps messages at 4096 chars — long messages (e.g. code blocks) must be split.

## Recovery (bridge down / tokens won't mint)

The #1 outage mode: the bridge is `active` but silently can't auth — `token_mint.py` stops minting `ic3` because the **device compliance lapsed** (Entra CA rejects the PRT SSO cookie). The trap: `intune-container doctor` stays **all green** and `systemctl is-active` says `active`, so both lie. The real signals are `teams auth-status --check` → `"valid": false`, a stale `~/ic3.jwt`, and the log falling back to `Opening Teams... Log in`. Fix = interactive **re-enroll** (`intune-container enroll`) done over a VNC screencast of display `:99`, then re-mint + restart. Full step-by-step, including the VNC setup and the gotchas: **[docs/RUNBOOK-token-recovery.md](docs/RUNBOOK-token-recovery.md)**.

## Commands

```sh
# Tests (no credentials needed — network/subprocess are stubbed in conftest)
export TELEGRAM_BOT_TOKEN=test:token TELEGRAM_GROUP_ID=-100999
python3 -m pytest -q                 # full suite
python3 -m pytest tests/test_reactions.py -q          # one file
python3 -m pytest tests/test_reactions.py::test_emoji_maps_roundtrip -q   # one test

# Syntax check (what CI runs)
python3 -m py_compile bridge.py token_mint.py tools/get_group_id.py
```

## Testing against the LIVE bridge (important)

There is a real, running instance as a **systemd user service** on this box. The service runs `bridge.py` **from the primary worktree's checkout** (`~/teams-telegram-bridge/bridge.py`) with the linuxbrew python that has playwright. So:

- To test a change end-to-end you must get that code onto the checkout the service runs, then restart it:
  ```sh
  systemctl --user restart teams-telegram-bridge
  systemctl --user is-active teams-telegram-bridge      # -> active
  tail -f /tmp/bridge-systemd.log                        # logs (a drop-in redirects stdout here)
  ```
- Health after restart: log shows `[in] primed`; `teams auth-status --check` shows `ic3: valid`; state.json mtime advances each poll (~POLL_SEC).
- The service's ExecStart uses the FULL playwright-python path (a drop-in override), because `refresh_loop` spawns `token_mint.py` with `sys.executable`. If you point it at a python without playwright, token refresh fails.
- **Unit tests are mocked — they do NOT prove it works.** Every feature so far had real bugs that only surfaced when a message/reaction/photo was actually pushed through the live bridge. ALWAYS finish with a live end-to-end check. Some directions (Telegram→Teams reactions, incoming photos) can only be triggered by the human — ask them to perform the tap/send and then read `/tmp/bridge-systemd.log` to confirm.
- **Never send test messages to arbitrary Teams chats.** Only send when the user asks, to a target they named. The `48:notes` self-chat ("Notes to self") is the safe target for self-driven tests — it's addressed by that fixed id and never appears in the chat list.

## Worktree discipline (avoid clobbering in-flight work)

The repo has ONE primary checkout that the systemd service runs from. When multiple branches are in flight (there usually are), **do NOT switch branches in the primary checkout** — it changes the code the live service will load on next restart and can displace another branch's uncommitted work. Instead create an isolated worktree off `main`:

```sh
git worktree add ../ttb-<name> -b <branch> origin/main
```
Do the work there; the primary checkout stays on `main` (or whatever the live service should run). Clean up with `git worktree remove` when merged.

## Change workflow (strict)

Every change goes through this — never commit straight to `main`:

1. Branch: `fix/<name>`, `feat/<name>`, or `chore/<name>` off `main` (in a worktree, above).
2. **Run `/ponytail` before, during, and after** — a lazy senior-dev lens kept active continuously, not just on request. Before: does this need to exist (YAGNI), is there an existing helper/stdlib. During: simplest form that works, reuse the existing maps/helpers. After: `/ponytail-audit` or `/ponytail-review` on what landed; mark deliberate shortcuts with a `ponytail:` comment naming the ceiling. This repo deliberately has zero runtime deps beyond playwright — `urllib` over `requests`, regex over an HTML parser for the fixed Skype markup are correct lazy choices, not debt.
3. Non-trivial logic leaves one runnable test (pytest, mocked).
4. Push the branch, open a PR (`gh pr create`).
5. Review with `/code-review` (correctness) — for big surface, fan out subagents across dimensions (threading/state, poll, outbound, security). Apply confirmed fixes on the branch.
6. Live end-to-end test on the branch (restart systemd from that checkout; drive the real flow).
7. Human reviews the PR → then merge (squash, `--delete-branch`).

## Releases

Semver. Feature → minor bump, fix → patch. After merging to `main`:

```sh
git checkout main && git pull
gh release create vX.Y.Z --title "vX.Y.Z — <summary>" --notes "<user-facing notes>"
```
Write release notes for a user (what changed / fixed), list known limitations, link the compare URL `vPREV...vX.Y.Z`. Line so far: v0.1.0 → reply threading v0.2.0 → emoji v0.2.1 → reactions v0.3.0 → rich formatting v0.4.0.

## Hard rules

- **No "Claude"/AI attribution** anywhere — commit messages, PR titles/bodies, release notes. Scan before pushing (`git log`, PR body, release body).
- This bridges a corporate account through unofficial APIs — genuine ToS/policy grey zone. Keep the risk visible in the README; don't quietly expand scope.
- Bot/group tokens are env-only (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_GROUP_ID`); never hardcode or log them. Token files (`~/ic3.jwt`, `~/graph.jwt`) are written `0600`.
