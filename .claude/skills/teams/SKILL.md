---
name: teams
description: Drive Microsoft Teams from this box via the `teams` CLI — list chats, read messages, post, reply, react, search, send files, and file merge-request review requests in the right channel with the house message format. Use whenever the task involves reading or sending a Teams message, asking "what's happening in Teams", answering someone on Teams, posting an MR/review request, or debugging the teams-telegram-bridge's Teams side. Encodes which chats are safe to post to and which must never be posted to.
---

# Teams via the `teams` CLI

`teams` is installed and authenticated on this box (`/home/claude/.local/bin/teams`, pipx package `microsoft-teams-cli`). It talks to the undocumented internal Teams (IC3) APIs using tokens minted by `token_mint.py`. No MCP server is needed — Bash plus this CLI is the whole interface.

The account is a **real corporate account** (Clément BOSLE, Sia Partners tenant). Every send is visible to real colleagues and cannot be unsent. The read side is free; the write side is governed by the allowlist below.

## 0. Preflight — always check auth first

```sh
teams auth-status --check --json
```

Look at `data.tokens.ic3`. If `false`, **stop** — nothing will work, and the failure is silent and confusing (see `docs/RUNBOOK-token-recovery.md`; the usual cause is lapsed device compliance, and `intune-container doctor` will lie to you and stay green). `presence`, `csa` and `substrate` are normally `false` — that is expected and only breaks `teams user-search` / `set-status`.

## 1. The CLI contract — read vs. mutate

This split is the single most common way to get it wrong. The two classes behave differently:

| | Read commands | Mutating commands |
|---|---|---|
| Examples | `chats` `chat` `read` `search` `unread` `summary` `attachments` `auth-status` `whoami` `schedule-list` | `send` `chat-send` `reply` `react` `unreact` `edit` `delete` `forward` `send-file` `group-chat` `mark-read` `set-status` `schedule` |
| `--json` | **Required.** Append it; parse the `{"ok":true,"schema_version":"1.0","data":[...]}` envelope and read `data`. | **Rejected.** Do not pass it. |
| Preview | n/a | `--dry-run` prints the intended payload as JSON and exits without sending. **Use it before every first-time send.** |
| Confirmation | none | prompts interactively; pass `-y`/`--yes` to skip, `--no-input` to fail instead of hanging |
| User-supplied text | **Cannot use `--`** — it would make the appended `--json` positional and break parsing. Reject text starting with `-` instead. | **Pass user text after `--`** so a leading `-` isn't parsed as a flag. |

```sh
# read
teams chats -n 20 --json
teams chat "19:...@thread.tacv2" -n 30 --json

# mutate: preview, then send
teams --dry-run chat-send 48:notes -- "hello"
teams chat-send -y 48:notes -- "hello"
```

Failure mode to guard against: **`teams` sometimes reports failure as exit 0 plus `{"ok": false}` on stdout** (e.g. a 403/400 from the API). A rejected send looks like success unless you check the body. `bridge.py:262 teams_do()` has the canonical handling — copy it if you script this.

## 2. Addressing — chat ids are stable, message numbers are not

**Chats: always use the id.** `teams chat` and `teams chat-send` accept a raw conversation id anywhere a number is expected — `client.py:1231` `_resolve_chat_id` returns the argument unchanged when it contains a `:` and either an `@`, a `48:`/`28:` prefix, or is longer than 50 characters. (That prefix branch is why `48:notes` works despite having no `@`.) Ids are stable forever; `display_num` is just a position in the last listing and shifts as chats reorder.

```sh
teams chat "19:yf2-R9Z4M9-ba9--x4Qrsah6Y0-mW4v3GQ159M-Dogs1@thread.tacv2" -n 20 --json   # good
teams chat 23 --json                                                                     # fragile
```

**Messages: `display_num` is ephemeral and there is no id-based alternative.** `react`, `reply`, `read`, `edit`, `delete` and `forward` take *only* `MSG_NUM`, which is only valid against the most recent listing. Reusing a number you saw earlier in the conversation can react to, reply to, or **delete the wrong message in a live corporate chat.**

The mandatory two-step recipe — re-read immediately before acting, match on the stable `id`, use the fresh `display_num`:

```sh
teams chat "<chat-id>" -n 30 --json > /tmp/c.json
python3 -c "
import json
msgs = json.load(open('/tmp/c.json'))['data']
m = next(x for x in msgs if x['id'] == '<stable-message-id>')
print(m['display_num'])
"
# then, in the same breath:
teams react -y like <that-number>
```

`bridge.py:827 msg_num_for_id()` is exactly this helper — reuse it rather than rewriting it if you're in Python.

**Never carry a `display_num` across turns.** If more than one command ran since you read it, read again.

## 3. Reading — the two API limits that bite

- **`--offset` is a no-op on `chat`.** `client.py:219-250` computes `pageSize = top + skip`, slices `messages[-(top+skip):]`, then `[skip:]` — the result is always the newest `top` messages. Verified: `-n 10 --offset 0` and `-n 10 --offset 20` return byte-identical output. **Depth comes from `-n` alone.**
- **`-n 200` is the ceiling** on `chat`. `-n 240` (and `--before` with `-n >= 150`) returns HTTP 400 from IC3. You cannot page further back than the newest ~200 messages of a channel with this CLI.
- `teams chats` *does* paginate with `--offset`, in pages of 60, up to ~240 entries, **but pages overlap** — always dedupe by `id`. Two passes minutes apart yield the same 218 unique chats.
- The CLI drops non-text message types (`client.py:233-236` keeps only `Text`, `RichText/Html`, `RichText`), so bot-card-heavy channels return far fewer rows than you asked for. That is not an error.

Message objects carry: `id` (stable), `display_num` (ephemeral), `conversation_id`, `sender`, `sender_id`, `content` (raw Teams HTML — the truth), `text_content` (flattened), `subject`, `timestamp`, `is_from_me`, `reactions`, `attachments`.

Analyse `content`, not `text_content`, when format matters — mentions, links and code blocks only exist in the HTML.

## 4. Where you may send

**Default: you may not.** 219 chats are reachable; 4 are writable, and only 1 without asking.

### Send freely

| id | what |
|---|---|
| `48:notes` | **"Notes to self"** — the user's own notes chat. The only safe target for tests and scratch messages. Never appears in `teams chats`; addressed by that fixed id. |

### Send for one specific purpose, after confirming the drafted text with the user

| id | channel | may carry |
|---|---|---|
| `19:yf2-R9Z4M9-ba9--x4Qrsah6Y0-mW4v3GQ159M-Dogs1@thread.tacv2` | **[Run] Engine merge requests** | MR review requests for `git.sia.partners/stratumn/platform/*` — see §5 |
| `19:f4b2e5764ffd4762b1f05697045eb35f@thread.tacv2` | **[Run] 🔄 Config Merge Requests** | MR review requests for `git.sia.partners/stratumn/configuration/*` |
| `19:8c31731328ee49e09e055dba5f9055a7@thread.tacv2` | **⏮ Reviews** | MR review requests for `git.sia-partners.com/{k8s,cloud,iac-projects,agentstore,platforms,devops,heka}/*` |
| `19:b22a4db9472040859f5efac89f522316@thread.tacv2` | **Heka.core - Update Alerts** | planned-maintenance and incident notices only — never an MR |

### Never send

- **Any `19:meeting_...` chat** (77 of them) — transient meeting side-channels.
- **Bot / alerting feeds** — `19:4a8ad1c1d15847f5826a75328438b6ec@thread.tacv2` (📣 Alerting 📣, Grafana + Power Automate; last human message 2025-03-13), `19:AOt-7oJPjyaZ5NkNd313SjJS-ndWEiMxh3BPOuNZ-dY1@thread.tacv2` (prod paging feed, bot `prolix`). Posting here pages people.
- **Firm-wide / leadership audiences** — `19:eIyR8uPENYpGFze3c1dUjRgdexp7AtU-g9tY1OTE_CY1@thread.tacv2` (Sia Group, CEO posts here), `19:83n42Zrf_A1t2xzWf58SKB0jGu7GXDWCwJiRTOkbDBs1@thread.tacv2` (FIM BU), `19:b8b73df873ec487d90342e5f6e5a9582@thread.tacv2` (Sia AI Ecosystem, 35 senders), plus the AD&Q_*, Paris office, Sia Sport and Squad Race channels.
- **Client-facing / cross-tenant channels with external people in the room** — `19:NcXo1CZ7h4gcGfKooiHz0rbyF1bxK-tkAYIJ6D1Vhdk1@thread.tacv2` (Stratumn client defect triage), `19:xmY4_k-kYN7uMPSd2QGINBjJYL3JVU-48FPsZW-TmWg1@thread.tacv2` (SPEN/PRAE).
- **Large support queues** — Claude - Support Center (26 senders), 🚨 SiaGPT - Support Centre (18 senders). A post here creates real work for named engineers.
- **Anything you could not identify.** Thin evidence means never.

### Everything else — ask first, naming the chat

The remaining ~112 chats (56 one-to-one DMs with named colleagues, 45 ad-hoc group chats, team channels) are real human venues. Sending needs explicit per-message confirmation from the user that names *this* chat. Approval to post in one chat never carries to another.

`references/chat-inventory.md` has the full 219-chat table with per-chat verdicts and the evidence behind each one. Read it when you need a chat that isn't listed above.

### The rule, restated

Compose → show the user the exact text and the exact target → send only after they confirm. `48:notes` is the sole exception. Posting to a channel is outward-facing and irreversible; a wasted confirmation costs one message, a wrong post costs a real apology.

## 5. Merge-request review requests

### Route by repository path, not by topic

| the MR lives in | post to |
|---|---|
| `git.sia.partners/stratumn/platform/*` (incl. `components/*`) | **[Run] Engine merge requests** |
| `git.sia.partners/stratumn/configuration/*` | **[Run] 🔄 Config Merge Requests** |
| `git.sia-partners.com/**` (k8s, cloud, iac-projects, agentstore, platforms, devops, heka, community) | **⏮ Reviews** |

**There are two GitLab hosts and they are both live.** `git.sia.partners` serves `stratumn/*`; `git.sia-partners.com` serves everything else. This is not a half-finished migration — both appear every month across the whole history. `k8s/*` shows up on both, so pick the host the way the target channel does, never by guessing. (The `glab-cli` skill only knows `git.sia-partners.com` and will not resolve a Stratumn MR URL.)

Linear namespaces track the same split: `linear.app/heka-internal/issue/STMN-<n>/<slug>` for Engine, `.../CONFIG-<n>` for Config, `linear.app/heka/issue/CORE-<n>` for ⏮ Reviews.

### The house format for [Run] Engine merge requests

The user's own four posts there share a consistent signature that differs from the channel norm — **match his, not the norm**:

```
<Hello|Yo|Wassup> [Run] Engine merge requests !

<one to three sentences, English, present tense, saying what the MR does and why>

<Related linear ticket : |Follow this ticket, |Following this linear ticket> https://linear.app/heka-internal/issue/STMN-<n>/<slug>

https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/<id>
```

Verbatim, one of his (2026-07-24):

> Wassup [Run] Engine merge requests !
>
> Follow this ticket, here is the MR to increase the token from 15 mins to 30 mins (1800 seconds) :
>
> https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/585

What is load-bearing in his style: the space before `!` after the channel name (`requests !`, never a comma), a blank line after the greeting line, the MR URL last and bare, the Linear link present (3 of 4 posts), and **no closing "Thanks", no emoji** — the channel norm has both, he doesn't. His follow-ups are French, lowercase, terse (`c'est merged en master`, `j'ai changé ! c'est vers master mtn`).

The channel norm, for reference when writing as someone else or matching the majority: `Hello [Run] Engine merge requests,` / blank / `Please review this MR <what it does>.` / blank / Linear link / `Thanks 🙂`. Body prose wraps identifiers in `<code>`. 17 of 33 posts carry a Linear link, and its absence gets noticed out loud ("Is this related to a linear ticket ?").

Reviewers reply in text, not reactions: `Approved`, `Approve`, `Reviewed`, `C'est approved`, `Approved and merged`. No one says LGTM. Claim-taking comes first (`Je prends`, `je regarde`, `I'll take a look`). Authors bump with a bare `up`. A ❤️ on the approval is the author's thank-you.

### Sibling channels differ — do not copy Engine's format across

- **[Run] 🔄 Config Merge Requests** — English only, always `Hi @channel,`, `Please review below MR.`, a numbered list of changes, often the env it was tested on (`tested on staging env`), closing `Thank you.`. Linear appears as a bare `[CONFIG-398]` id inside the MR title far more often than as a URL (8 of 60 posts have a URL).
- **⏮ Reviews** — the terse one, and the channel the user posts in most (47 of 200 messages). Channel mention optional (53%). Bare GitLab URL as the last line, **no sign-off** (5% have one), and the ask includes the apply step: `Could you please review and apply it?` — the reviewer runs terraform. The `CORE-nnnn` id goes in the title as bare text, essentially never as a URL (1 of 80).

`references/mr-message-format.md` holds the full evidence: verbatim HTML of representative posts, per-channel counts, anchor-text frequencies, subject-line conventions, and the project-path inventory.

### Two things the CLI cannot reproduce — read before promising a post

`teams chat-send` builds its payload in `client.py:284-322`, and that payload has **no `subject` key at all** and **`"mentions": "[]"` hardcoded**. There is no flag for either, on any command. Consequences:

1. **No channel @mention, so no notification.** Every real MR post in these channels mentions the channel, which is what pings the reviewers. Teams tokenises the channel name per word, so `[Run] Engine merge requests` is four separate `<span itemtype="http://schema.skype.com/Mention" itemid="0..3">` elements bound to MRIs via `properties.mentions`. Emitting that markup by hand renders as inert text and pings nobody. Sending the plain literal `[Run] Engine merge requests` is the honest fallback: it reads correctly, it just doesn't notify.
2. **No title.** These are `thread.tacv2` channels where the request is a *titled post* — 34 of 35 Engine MR posts carry a `subject` like `[helm] atomic rollback for stratumn upgrades`. A `chat-send` post is untitled, and `teams edit` can't add one afterwards.

So a CLI-sent MR request is **structurally degraded**: right text, no title, no ping. Say so when you offer it. Two honest options — offer both, let the user pick:

- **Draft for the user to paste** into Teams, where they get the title and a real mention. Default for anything that needs reviewers to actually notice.
- **Send it via `chat-send`** and tell the user to expect no ping and no title, so they can nudge the channel themselves.

Raw HTML *does* pass through verbatim (`client.py:292` only wraps input that doesn't start with `<`), so `<p>`, `<p>&nbsp;</p>` spacers, `<a href="...">MR</a>` anchors, `<ul>/<ol>/<li>` and `<code>` all work. Plain text with `\n` becomes one `<p>` per non-blank line — blank lines are dropped, so plain-text mode cannot produce the `<p>&nbsp;</p>` spacer that every real post has. Send HTML when the spacing matters.

## 6. The other operations

```sh
# find someone's chat
teams chats -n 60 --json                      # dedupe by id; --offset 60/120/180 for more
teams unread --json
teams search "query" -n 20 --json             # add --chat <id> --from <name> --after YYYY-MM-DD
                                              # NOTE: reject a query starting with `-`; you cannot use `--` here

# read
teams chat "<chat-id>" -n 50 --json
teams read <fresh-msg-num> --json             # --raw for the unrendered HTML
teams attachments <fresh-msg-num> --json

# write (each needs a fresh msg num — see §2 — and a confirmed target — see §4)
teams chat-send -y "<chat-id>" -- "text"
teams reply -y <fresh-msg-num> -- "text"
teams react -y like <fresh-msg-num>           # like|heart|laugh|surprised|sad|angry
teams unreact -y like <fresh-msg-num>
teams send-file -y "<chat-id>" /path/to/file
teams edit -y <fresh-msg-num> -- "new text"
teams delete -y <fresh-msg-num>               # irreversible; confirm with the user first, always
```

Reaction vocabulary on the wire is wider than the six the CLI accepts (`1f389_partypopper`, `2728_sparkles`, `ok`, `rofl`, `skull` all appear in real data) — you can read them, you can only send the six.

## 7. Interaction with the live bridge

A systemd user service (`teams-telegram-bridge`) polls Teams every `POLL_SEC` and mirrors messages into Telegram forum topics. Two consequences when you use the CLI on this box:

- **Anything you send via the CLI shows up in Telegram too**, within ~5s. `ECHO_SELF=1` is the default (`bridge.py:32`), and the bridge's own-echo suppression only recognises messages *it* sent (`mark_bridge_sent`). A CLI send isn't one, so `poll_inbound` treats it as new and mirrors it. Not a bug — just expect the copy.
- **Don't fight the bridge for state.** It is the only writer of `~/.cache/teams-bridge/state.json`. Read it if you want the chat↔topic map; never write it.

## 8. Hard rules

1. **Never send to a chat the user did not name**, except `48:notes`. No exploratory sends, no "let me test whether this works" in a real chat.
2. **Never reuse a `display_num` across commands.** Re-read, match by `id`, then act.
3. **`--dry-run` before any first-time send** to a chat or in a new format.
4. `teams delete` and `teams edit` alter other people's view of history. Confirm the exact target message with the user first, every time.
5. Don't log or echo token files (`~/ic3.jwt`, `~/graph.jwt`, `~/.cache/teams-cli/tokens.json`).
6. This bridges a corporate account through unofficial APIs — a genuine ToS grey zone. Don't quietly widen the blast radius.

## 9. Why `teams chat` still prompts

`.claude/settings.json` allowlists the unambiguous read commands so they run without a permission prompt: `chats`, `read`, `search`, `unread`, `summary`, `attachments`, `auth-status`, `whoami`, `status`, `user-search`, `schedule-list`.

Two read paths are deliberately left off it:

- **`teams chat`** — `Bash(teams chat:*)` is a prefix rule, and `teams chat-send ...` also starts with `teams chat`. Allowlisting the read would very plausibly allowlist the send. Reading one chat costs one prompt; an unconfirmed post to a corporate channel costs an apology.
- **`teams schedule-list`** is allowlisted, but bare `teams schedule:*` is not — it would also cover `schedule`, `schedule-cancel` and `schedule-run`, all mutating.

Don't "fix" this by widening the rules. If the prompts get tedious, allowlist a *specific* full command, not a prefix that reaches a mutation.

## Making this skill available outside this repo

It lives in the bridge repo, so it only loads when working here. To use it anywhere:

```sh
ln -s "$PWD/.claude/skills/teams" ~/.claude/skills/teams
```
