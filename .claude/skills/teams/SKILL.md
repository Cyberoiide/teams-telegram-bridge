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

### Writing in [Run] Engine merge requests — his voice, not the channel's

**Write exactly as the user writes.** His four MR posts there share one skeleton, and it is deliberately not the channel majority's. Don't blend the two.

Fixed points he never breaks, 4 out of 4:

- **Greeting word, then the channel name, then ` !`** — a space before the `!`, never a comma, never a bare mention. Greetings he uses: `Hello` ×2, `Yo`, `Wassup`. `Hello` is the safe default; `Yo`/`Wassup` are his alone in that channel.
- **A blank line immediately after the greeting line.**
- **No sign-off, no "Thanks", no emoji.** The channel has them (14/33 and 13/33); he never does. This is the most visible difference — don't add politeness he doesn't use.
- **Body opens casually, downplaying the size:** `Little MR to …`, `Here is a little MR to …`, `here is the MR to …`, `This MR aims to …`.
- **Subject: `[<lowercase component>] <lowercase description>`.** His four, verbatim: `[helm] readiness and liveliness probes`, `[grafana] alerting base + removal of dead code`, `[account-api] increase token from 15 to 30 mins`, `[helm] atomic rollback for stratumn upgrades`. The component tag is **lowercase** — the rest of the channel capitalises (`[Engine]`, `[Conduent]`, `[Hotfix]`). Pass it as `--subject` to `tools/teams_post.py`; `chat-send` cannot set one.
- **Space before `:` and `!`** throughout, in English and French alike (`… (1800 seconds) :`, `Related linear ticket : `, `just updated !`). Francophone typing habit — keep it.

He alternates between exactly two body shapes. Pick by whether the MR needs prose around it.

**Shape A — bulleted link last (3 of 4).** Prose, then the MR URL bare in a bullet, as the final element. Verbatim, 2026-07-24, subject `[account-api] increase token from 15 to 30 mins`:

> Wassup [Run] Engine merge requests !
>
> Follow this ticket, here is the MR to increase the token from 15 mins to 30 mins (1800 seconds) :
>
> - https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/585

`ticket` is the anchor text carrying the Linear URL. The two-paragraph variant, 2026-07-23, subject `[grafana] alerting base + removal of dead code` — here Linear gets its own line above the bullet:

> Yo [Run] Engine merge requests !
>
> Here is a little MR to recreate the alerting service for Grafana towards our Teams Channel Alerting.
> The old way of doing it through webhooks is not expired. This updated version is just sending a mail through Sendgrid to the channel.
>
> Related linear ticket : https://linear.app/heka-internal/issue/STMN-3338/implement-grafana-alerting-for-stmn-3276-signals-rulegroups-contact
>
> - https://git.sia.partners/k8s/cetautomatix/helmfiles/-/merge_requests/55

(Second paragraph follows the first with no blank line between them.)

**Shape B — one inline paragraph (1 of 4).** No bullet, no separate link line: the MR anchored as `This MR`, the ticket as `this linear ticket`, and the sentence simply stops — no closing period. Verbatim, 2026-07-28, subject `[helm] atomic rollback for stratumn upgrades`:

> Hello [Run] Engine merge requests !
>
> This MR aims to activate the atomic feature of helm so that if an apply fails, it will automatically rollback on the last good helm revision. Following this linear ticket

Linear lead-ins, verbatim: `Related linear ticket : ` · `Follow this ticket, ` · `Following `. His 2026-07-15 post has no Linear link at all, but a missing ticket gets challenged in-channel ("Is this related to a linear ticket ?") — include one whenever a ticket exists.

### Producing one, end to end — the validated recipe

This is the exact procedure that produced a message he reviewed and approved. Follow it; don't improvise a different shape.

**Step 1 — pull the ticket from Linear, don't guess the content.** The Linear MCP gives you the real title, the real "Why", *and* the MR URL, so you never invent an MR number:

```
mcp__plugin_linear_linear__get_issue({ id: "STMN-3369" })
```

Use these fields: `title` → the subject line · `description` (the `## Why` / `## What` sections) → concrete facts for the body · **`attachments[].url` → the GitLab MR link** (Linear records the MR as an attachment, e.g. `https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/589`) · `assignee`, `status` → sanity-check it's his MR and actually awaiting review.

**Step 2 — route by the MR's repo path** (§5 table). `stratumn/platform/*` → [Run] Engine merge requests.

**Step 3 — write the subject** as `[<lowercase component>] <lowercase description>`, derived from the MR title. For `🧰 ci: make preprod & release helm deploys blocking [STMN-3369]` → `[ci] make preprod & release helm deploys blocking`. Hand it to him separately; the CLI can't set it.

**Step 4 — compose the body as raw HTML.** Plain text with `\n` drops blank lines, so the `<p>&nbsp;</p>` spacers every one of his posts has would vanish. Write the HTML to a file and pass it in, so the shell never mangles the markup:

```sh
cat > /tmp/mrmsg.html <<'EOF'
<p>Hello [Run] Engine merge requests !</p>
<p>&nbsp;</p>
<p><BODY — one or two sentences, casual, present tense, opening "Little MR to …"></p>
<p>&nbsp;</p>
<p>Related linear ticket : <a href="<LINEAR_URL>"><LINEAR_URL></a></p>
<p>&nbsp;</p>
<ul>
<li><a href="<MR_URL>"><MR_URL></a></li></ul>
EOF

teams --dry-run chat-send "<chat-id>" -- "$(cat /tmp/mrmsg.html)"    # inspect
teams chat-send -y "<chat-id>" -- "$(cat /tmp/mrmsg.html)"           # then send
```

The heredoc must be quoted (`<<'EOF'`) so `&nbsp;` and the URLs pass through untouched. Content starting with `<` is sent verbatim (`client.py:292`), which is what preserves the spacers and the bullet.

**Step 5 — confirm the target with him before sending to a channel.** `48:notes` needs no confirmation and is the right place to show him a preview first.

**The approved output, verbatim** — subject `[ci] make preprod & release helm deploys blocking`:

> Hello [Run] Engine merge requests !
>
> Little MR to make the preprod and release helm deploys blocking. allow_failure: true was hiding real failures — the migration pre-upgrade hook died in pipeline 190536 and the pipeline still went green.
>
> Related linear ticket : https://linear.app/heka-internal/issue/STMN-3369/remove-allow-failuretrue-on-stratumn-helm-deploy-jobs-or-add-explicit
>
> - https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/589

Why that body works, as a pattern to copy: **one sentence saying what the MR does**, then **an em-dash clause giving the concrete failure it fixes**, pulled from the ticket's `## Why` — a specific pipeline number and the actual symptom, not a vague "improves reliability". Identifiers (`allow_failure: true`) stay bare, not in `<code>` — he doesn't use `<code>`, though the channel majority does.

### For a real channel post, use `tools/teams_post.py` — it gets the title and the ping

`teams chat-send` cannot set a subject or a mention, so a post made with it is untitled and **notifies nobody**. `tools/teams_post.py` (in this repo) builds the IC3 payload directly to add both, reusing `teams_cli` for auth and transport. Same body HTML, plus a `@@MENTION@@` token where the channel mention belongs:

```sh
cat > /tmp/mr.html <<'EOF'
<p>Hello @@MENTION@@&nbsp;!</p>
<p>&nbsp;</p>
<p><BODY></p>
<p>&nbsp;</p>
<p>Related linear ticket : <a href="<LINEAR_URL>"><LINEAR_URL></a></p>
<p>&nbsp;</p>
<ul>
<li><a href="<MR_URL>"><MR_URL></a></li></ul>
EOF

PY=/home/claude/.local/share/pipx/venvs/microsoft-teams-cli/bin/python   # needs teams_cli importable

$PY tools/teams_post.py --dry-run \
  --chat "19:yf2-R9Z4M9-ba9--x4Qrsah6Y0-mW4v3GQ159M-Dogs1@thread.tacv2" \
  --body-file /tmp/mr.html \
  --subject "[ci] make preprod & release helm deploys blocking" \
  --mention "[Run] Engine merge requests"
```

Drop `--dry-run` to send. Notes that matter:

- **Run it with the pipx interpreter** that has `teams_cli` (path above), not bare `python3`.
- **`--mention` requires `@@MENTION@@` in the body** — the tool exits rather than silently posting an unmentioned message.
- **The mention MRI is the channel's own conversation id.** Not the `groupId` from the channel deeplink, not the channel's SMTP address (`…@fr.teams.ms`) — those are for other APIs and don't belong in this payload.
- Teams tokenises a channel mention **per word**: `[Run] Engine merge requests` → four spans and four mention objects, itemids 0-3, all sharing that one MRI, joined by `&nbsp;`. `⏮ Reviews` is two. The tool does this for you; `tests/test_teams_post.py` pins the shape to a real post read back off the wire.
- **`--subject` is what makes it a titled channel post.** Verified: a message sent this way reads back with `properties.subject` set, where a `chat-send` message reads back `None`.
- Every span needs a matching mention object with the same itemid. Hand-writing the spans without the `mentions` property is the failure that looks like success — it renders as plain text and pings nobody.

Preview in `48:notes` first if he wants to see it: the HTML round-trips byte-for-byte. Leave `--mention` off for previews, since the mention would target the real channel.

**Posting to the channel notifies every member.** Confirm the final text and the target with him before sending; §4 applies in full.

**Follow-ups switch to French**, lowercase, terse: `yes, just updated !` · `j'ai changé ! c'est vers master mtn` · `ah oui je peux check` · `c'est fixed (même mr) et testé en staging` · `c'est merged en master`. Match that register for status updates on his own MR — never polished English.

The channel majority writes `Hello [Run] Engine merge requests,` / `Please review this MR <what it does>.` / Linear link / `Thanks 🙂`. **Not his style — don't reach for it.** It's noted only so you recognise it in others' posts.

Reviewers reply in text, not reactions: `Approved`, `Approve`, `Reviewed`, `C'est approved`, `Approved and merged`. No one says LGTM. Claim-taking comes first (`Je prends`, `je regarde`, `I'll take a look`). Authors bump with a bare `up`. A ❤️ on the approval is the author's thank-you.

### Sibling channels differ — do not copy Engine's format across

- **[Run] 🔄 Config Merge Requests** — English only, always `Hi @channel,`, `Please review below MR.`, a numbered list of changes, often the env it was tested on (`tested on staging env`), closing `Thank you.`. Linear appears as a bare `[CONFIG-398]` id inside the MR title far more often than as a URL (8 of 60 posts have a URL).
- **⏮ Reviews** — the terse one, and the channel the user posts in most (47 of 200 messages). Channel mention optional (53%). Bare GitLab URL as the last line, **no sign-off** (5% have one), and the ask includes the apply step: `Could you please review and apply it?` — the reviewer runs terraform. The `CORE-nnnn` id goes in the title as bare text, essentially never as a URL (1 of 80).

`references/mr-message-format.md` holds the full evidence: verbatim HTML of representative posts, per-channel counts, anchor-text frequencies, subject-line conventions, and the project-path inventory.

### Which sender to use

| | `teams chat-send` | `tools/teams_post.py` |
|---|---|---|
| Title (`subject`) | no | **yes**, `--subject` |
| Channel @mention / notification | no | **yes**, `--mention` |
| Right for | replies, follow-ups, 1:1 chats, previews | titled channel posts that must reach reviewers |

`chat-send` builds its payload at `client.py:284-322`, which has **no `subject` key at all** and **`"mentions": "[]"` hardcoded** — no flag on any command changes that. So a `chat-send` channel post is untitled and notifies nobody, while 34 of 35 real Engine MR posts are titled and all mention the channel. That's why `tools/teams_post.py` exists; use it for MR review requests (recipe in §5).

Anything hand-writing `<span itemtype="http://schema.skype.com/Mention" itemid="N">` **without** a matching `properties.mentions` entry renders as inert text and pings nobody — a failure that reads exactly like success. Don't do it by hand; the tool keeps the two in sync.

Raw HTML passes through verbatim in both senders (`client.py:292` only wraps input that doesn't start with `<`), so `<p>`, `<p>&nbsp;</p>` spacers, `<a href="...">MR</a>` anchors, `<ul>/<ol>/<li>` and `<code>` all work. Plain text with `\n` becomes one `<p>` per non-blank line — blank lines are dropped, so plain-text mode cannot produce the `<p>&nbsp;</p>` spacer that every real post has. Send HTML when the spacing matters.

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
