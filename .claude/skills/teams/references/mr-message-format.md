# MR review request format — evidence

Reverse-engineered from the live channels on 2026-08-04: 198 messages from **[Run] Engine merge requests**, 200 from **[Run] 🔄 Config Merge Requests**, 200 from **⏮ Reviews**, plus 62/24/199/170 from the four channels that turned out to be wrong venues.

Sample limits worth knowing: `--offset` is a no-op on `teams chat`, and `-n 200` is the hard ceiling (`-n 240` → HTTP 400). So this is the newest ~200 messages per channel, nothing older is reachable with this CLI.

Counts below are over *primary MR requests* — a message with an MR link plus either a subject or a channel mention. Engine n=35, Config n=60, Reviews n=80.

---

## Channel routing

| Repo path | Channel | Chat id |
|---|---|---|
| `git.sia.partners/stratumn/platform/*` | [Run] Engine merge requests | `19:yf2-R9Z4M9-ba9--x4Qrsah6Y0-mW4v3GQ159M-Dogs1@thread.tacv2` |
| `git.sia.partners/stratumn/configuration/*` | [Run] 🔄 Config Merge Requests | `19:f4b2e5764ffd4762b1f05697045eb35f@thread.tacv2` |
| `git.sia-partners.com/**` | ⏮ Reviews | `19:8c31731328ee49e09e055dba5f9055a7@thread.tacv2` |

The Engine channel has `topic: null` in `teams chats` output (it's a private channel), which is why it can't be found by name — address it by id. It surfaced only via a DM from Matthieu GAUCHER, 2026-07-22: *"On poste les MR là au fait 😉"*.

### Two GitLab hosts, both live

| Host | Namespaces | Messages | Channels |
|---|---|---|---|
| `git.sia.partners` | `stratumn/*` only (plus `k8s/cetautomatix/helmfiles`) | 99 | Config 60, Engine 43 |
| `git.sia-partners.com` | `k8s`, `cloud`, `iac-projects`, `agentstore`, `platforms`, `devops`, `heka`, `community` | 104 | Reviews 103, Heka Core 13, Heka chat 3 |

Monthly histograms overlap across the entire history, so this is not a migration in progress. `k8s/*` appears on both hosts. Pick the host from the target channel's convention; never infer it.

Canonical MR URL, both hosts: `https://<host>/<group>/<subgroup…>/<project>/-/merge_requests/<n>`, occasionally with a `#<sha>` diff anchor.

### Linear namespaces

| Workspace | Prefix | Channel | Tickets seen |
|---|---|---|---|
| `heka-internal` | `STMN` | Engine (17), Config (2) | STMN-2772 … STMN-3379 |
| `heka-internal` | `CONFIG` | Config (7) | CONFIG-268, -272, -298, -314, -325, -360, -373 |
| `heka` | `CORE` | Heka Core (6), Reviews (1) | CORE-4947 … CORE-5296 |

Shape: `https://linear.app/<workspace>/issue/<PREFIX>-<n>/<kebab-slug>`. The slug is optional — Config routinely posts the bare `https://linear.app/heka-internal/issue/CONFIG-268`. Lowercase variants (`/issue/stmn-3373/`) only ever appear inside Teams' `title=` mirror of the `href`; the `href` itself is uppercase.

---

## [Run] Engine merge requests

35 primary MR requests in 198 messages. 6 senders, zero bots. Bilingual: requests mostly English, follow-up chatter mostly French.

**Anatomy, in order:**

| Slot | Present | Form |
|---|---|---|
| Greeting | 30/33 | `Hello` 25, `Hey` 3, `Yo` 1, `Wassup` 1 |
| Channel mention | 33/33 | four `<span>` mentions, `itemid="0".."3"`, one per word of `[Run] Engine merge requests`, joined by `&nbsp;` |
| Punctuation after it | — | `,` 14 · nothing 7 · `&nbsp;!` 4 — **all four of Clément's** |
| Blank spacer | 32/33 | literal `<p>&nbsp;</p>` |
| Request sentence | 33/33 | own `<p>`; on the mention's line in 8/33 |
| GitLab link | 33/33 | inline in the sentence 28, own `<p>`/`<ul>` 5 |
| Linear link | **17/33 (52%)** | almost always the final `<p>`, alone |
| Closing thanks | 14/33 | `Thanks` 6, `Thanks!` 2, `Thanks !!`, `Merci`, `Thanks for reviewing it` |
| Emoji | 13/33 | 🙂 ×11, 🥳, 🙏, 👀 — always trailing, in the thanks line |
| Screenshot | 3/33 | `AMSImage` `<img>` in its own `<p>`, after the text |

No labels, no severity markers, no cc convention.

**Subject convention:** `[<Component>] <what>`. Observed: `[Engine]` ×18, `[Conduent]` ×6, `[Hotfix]`, `[helm]`, `[grafana]`, `[account-api]`, `[InitLink]`. The ticket id is almost never in the subject (one exception: `[Engine - 2949]`). 34 of 35 requests carry a subject.

**MR anchor text:** `MR` ×21 dominant. Then `This MR`, `MR here`, `here`, `hotfix`, `Config MR`, `SuperMR`, and role labels when several MRs ride in one post (`SAM` = platform monorepo, `Config` = claims-assignments, `DSL` = dsl). Bare URL as anchor text only 3 times — but 3 of the user's own 4 posts do exactly that.

**Linear anchor text:** `Issue` ×2, `issue` ×2, `ticket` ×2, then `L'issue`, `Linear issue`, `Linear ticket`, `Linear`, `Ticket`, `this linear ticket`, `ici`, `HERE`, `here`, bare URL ×2. Lead-ins: `lien de l'issue ici`, `Related linear ticket : `, `Following this linear ticket`.

**Recurring request phrasings:** `Please review this MR` ×7 · `could you review this/the MR` ×3 · `could you please review this MR` ×2 · `Possible de review la/ce …` ×2 · `Can you please have a look at this MR.` · `could you please approve this MR ?` · `Can anyone review it ? Thanks!` · `Petite MR à review svp.`

**Project paths seen:** `stratumn/platform/stratumn` ×32, `stratumn/configuration/conduent/claims-assignments` ×3, `stratumn/platform/components/dsl` ×1, `k8s/cetautomatix/helmfiles` ×1.

**Senders:** Bastien YOUSSFI 80 msgs / 19 requests · Théophile WALLEZ 52 / 0 (reviewer) · Matthieu GAUCHER 26 / 0 · Clément DELBARRE 16 / 0 (reviewer) · Leonor GROELL 15 / 10 · **Clément BOSLE 9 / 4**.

### Verbatim HTML — the channel norm

Bastien YOUSSFI, 2026-04-09, single-line request with a bare Linear URL:

```html
<p>Hey <span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="0">[Run]</span>&nbsp;<span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="1">Engine</span>&nbsp;<span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="2">merge</span>&nbsp;<span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="3">requests</span>, could you please review this <a href="https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/467" title="https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/467">MR</a> that solves the empty comment problem. Thanks <span title="Sourire" type="(smile)" class="animated-emoticon-20-smile" itemscope=""><img itemscope="" itemtype="http://schema.skype.com/Emoji" itemid="smile" src="https://statics.teams.cdn.office.net/evergreen-assets/personal-expressions/v2/assets/emoticons/smile/default/20_f.png" title="Sourire" alt="🙂" style="width:20px; height:20px"></span></p>
<p>&nbsp;</p>
<p><a href="https://linear.app/heka-internal/issue/STMN-2949/submit-action-impossible-when-comment-empty" rel="noreferrer noopener" title="https://linear.app/heka-internal/issue/stmn-2949/submit-action-impossible-when-comment-empty" target="_blank">https://linear.app/heka-internal/issue/STMN-2949/submit-action-impossible-when-comment-empty</a></p>
```

Leonor GROELL, 2026-05-06, the tightest and most-copied shape:

```html
<p>Hello <span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="0">[Run]</span>&nbsp;<span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="1">Engine</span>&nbsp;<span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="2">merge</span>&nbsp;<span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="3">requests</span></p>
<p>&nbsp;</p>
<p>Please review this <a href="https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/486" title="…">MR</a> concerning the retrial of Conduent login when authentication endpoint returns empty / no token.&nbsp;</p>
<p><a href="https://linear.app/heka-internal/issue/STMN-3032/conduent-login-retry-3-times-if-empty-token-received" title="…">Issue</a></p>
```

### Verbatim HTML — Clément BOSLE's own signature (4/4 consistent)

`[helm] atomic rollback for stratumn upgrades`, 2026-07-28:

```html
<p>Hello <span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="0">[Run]</span>&nbsp;<span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="1">Engine</span>&nbsp;<span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="2">merge</span>&nbsp;<span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="3">requests</span>&nbsp;!&nbsp;</p>
<p>&nbsp;</p>
<p><a href="https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/588" itemtype="http://schema.skype.com/HyperLink" rel="noreferrer noopener" title="…" target="_blank" itemid="8b558ebd-…">This MR</a> aims to activate the atomic feature of helm so that if an apply fails, it will automatically rollback on the last good helm revision. Following <a href="https://linear.app/heka-internal/issue/STMN-3368/make-helm-upgrades-atomic-atomic-cleanuponfail-wait-so-failed-releases" itemtype="http://schema.skype.com/HyperLink" rel="noreferrer noopener" title="…" target="_blank" itemid="d9747019-…">this linear ticket</a></p>
```

`[account-api] increase token from 15 to 30 mins`, 2026-07-24 — the `<ul>`-with-bare-URL shape he uses most:

```html
<p>Wassup <span … itemid="0">[Run]</span>&nbsp;<span … itemid="1">Engine</span>&nbsp;<span … itemid="2">merge</span>&nbsp;<span … itemid="3">requests</span>&nbsp;!</p>
<p>&nbsp;</p>
<p>Follow this <a href="https://linear.app/heka-internal/issue/STMN-3379/us-change-stratumn-token-expiration-time-to-30-min" …>ticket</a>, here is the MR to increase the token from 15 mins to 30 mins (1800 seconds) :</p>
<ul>
<li><a href="https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/585" …>https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/585</a></li></ul>
```

`[grafana] alerting base + removal of dead code`, 2026-07-23 — two body paragraphs with no spacer between them, a separate `Related linear ticket : ` line, and a Teams channel deeplink inside the prose. Reactions: ❤️ ×1.

```html
<p>Yo&nbsp;<span … itemid="0">[Run]</span>&nbsp;…&nbsp;<span … itemid="3">requests</span>&nbsp;!&nbsp;</p>
<p>&nbsp;</p>
<p>Here is a little MR to recreate the alerting service for Grafana towards our Teams Channel <a href="https://teams.cloud.microsoft/l/channel/19%3A4a8ad1c1d15847f5826a75328438b6ec%40thread.tacv2/…">Alerting</a>.&nbsp;</p>
<p>The old way of doing it through webhooks is not expired. This updated version is just sending a mail through Sendgrid to the channel.</p>
<p>&nbsp;</p>
<p>Related linear ticket : <a href="https://linear.app/heka-internal/issue/STMN-3338/implement-grafana-alerting-for-stmn-3276-signals-rulegroups-contact" …>https://linear.app/heka-internal/issue/STMN-3338/implement-grafana-alerting-for-stmn-3276-signals-r…</a></p>
<p>&nbsp;</p>
<ul>
<li><a href="https://git.sia.partners/k8s/cetautomatix/helmfiles/-/merge_requests/55" …>https://git.sia.partners/k8s/cetautomatix/helmfiles/-/merge_requests/55</a></li></ul>
```

`[helm] readiness and liveliness probes `, 2026-07-15 — the only one of his four with a **person mention** mid-body (itemids continue at 4/5) and the only one with **no Linear link**. Note the trailing space in the subject:

```html
<p>Hello <span … itemid="0">[Run]</span>&nbsp;…&nbsp;<span … itemid="3">requests</span>&nbsp;!</p>
<p>&nbsp;</p>
<p>Little MR to put back the probes on the generic stratumn chart. <span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="4">Théophile</span>&nbsp;<span itemtype="http://schema.skype.com/Mention" itemscope="" itemid="5">WALLEZ</span>&nbsp;gave some feedback but it's still open for anyone who wants to take a look at it.</p>
<p>&nbsp;</p>
<ul>
<li><a href="https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/571" …>https://git.sia.partners/stratumn/platform/stratumn/-/merge_requests/571</a></li></ul>
```

**His four subjects, verbatim** — all `[<lowercase component>] <lowercase description>`, against the channel's capitalised `[Engine]`/`[Conduent]`/`[Hotfix]`:

| Date | Subject |
|---|---|
| 2026-07-15 | `[helm] readiness and liveliness probes ` (trailing space) |
| 2026-07-23 | `[grafana] alerting base + removal of dead code` |
| 2026-07-24 | `[account-api] increase token from 15 to 30 mins` |
| 2026-07-28 | `[helm] atomic rollback for stratumn upgrades` |

**What is distinctive about his style, against the channel norm:**

1. Varied casual greeting — `Hello` ×2, `Yo`, `Wassup`. Nobody else uses `Yo`/`Wassup`.
2. **`&nbsp;!` after the mention block, never a comma.** Nobody else does this. Sometimes a further trailing `&nbsp;` after the `!` (2 of 4).
3. `<p>&nbsp;</p>` spacer, then body — 4/4.
4. MR link most often a bare pasted URL inside `<ul><li>` (3/4); once inline as `<a>This MR</a>`.
5. **No trailing "Thanks", no emoji, no sign-off** — 0/4, against 14/33 and 13/33 for the channel.
6. Linear link in 3/4, phrased `Related linear ticket : `, `Follow this ticket, `, `Following `. Never a `[Linear]`/`[Issue]` anchor like Leonor's.
7. Lowercase subject component tag (see table above).
8. Space before `!` and `:` throughout, English and French alike — `(1800 seconds) :`, `Related linear ticket : `, `just updated !`.
9. Follow-ups in French, lowercase, terse: `yes, just updated !`, `j'ai changé ! c'est vers master mtn`, `ah oui je peux check`, `c'est fixed (même mr) et testé en staging`, `c'est merged en master`.
10. Body downplays scope: `Little MR to …`, `Here is a little MR to …`, `here is the MR to …`, `This MR aims to …`.

Reactions his posts drew: ❤️ ×1 on the 2026-07-23 MR, ❤️ ×2 on `c'est merged en master`. The other seven drew none.

### Reply and approval convention

22 approval replies, 0 approvals expressed as a reaction only. Exact vocabulary: `Approved` ×4 (Clément DELBARRE ×3, Théophile WALLEZ ×1) · `Approve` ×3 · `Approved` + a person mention ×2 · `Reviewed` ×2 · `approved ✅` · `Approved and merged` · `Approve + merged` · `I approved both` · `C'est approved` · `C'est review` + mention · `C'est merged` / `c'est merge!` ×3. **No "LGTM" anywhere.**

Claim-taking first: `Je prends`, `Je check !`, `je regarde`, `Hello je regarde`, `I'll take a look`, `Merci je check ça dans l'aprem !`. Author bumps with a bare `up`.

Reactions are orthogonal to approval (47/198 messages carry one): ❤️ 26, 👍 18, `ok` 3, `rofl` 2, `skull`, `surprised`, `2728_sparkles`, `1f389_partypopper`. 15 of the 26 hearts sit on approval replies — the author hearting the reviewer. 10 of 33 MR posts got a reaction, meaning "seen/taken", not "approved".

---

## [Run] 🔄 Config Merge Requests

60 primary MR requests in 200 messages. 9 senders (Matthieu GAUCHER 43, Apurva SANAP 40, Ananya GOSWAMI 28, Ibrahima DIALLO 22, Amol NAGOTKAR 22, Leonor GROELL 19, Théophile WALLEZ 18, Clément DELBARRE 4, Swarina PALKAR 4), zero bots. **English only** — 0 of 60 request bodies contain French.

Channel mention is **mandatory here: 60/60**. Note the name tokenises to **five** mention spans (`[Run]` `🔄` `Config` `Merge` `Requests`).

**Subject convention:** `[<Client or Feature>] - <what>`, or `<Type>: <what> [CONFIG-nnn]`. Client brackets seen: `[Conduent Hotfix]`, `[Retro TA]`, `[AXA]`, `[Mastercom]`, `[Renewal-Reterms]`. The ticket id frequently rides in the subject. 58/60 have a subject.

**MR anchor text:** GitLab's auto-unfurled page title dominates (29), then bare URL (17), then the word `MR` (11).

**Linear link:** only 8/60 as a URL — the id normally travels inside the MR title (`[CONFIG-398]`).

**Body:** the longest of the three channels. 13/60 carry an explicit numbered "changes made" list, sometimes file-by-file. 4/60 name the env it was verified on (`tested on staging env`, `tested on pre-prod env`), and there's a convention of naming the test trace (`I tested workflow -> [Deposit Premiums] trace -> [DEP-622]`).

**Closing:** 20/60 sign off, usually `Thank you.` or `Thanks!`.

Representative, Amol NAGOTKAR 2026-08-03, subject `[Conduent Hotfix] - removed reason dropdown based on condition`:

> Hi @[Run] @🔄 @Config @Merge @Requests
> Please review below MR.
> removed reason dropdown based on condition (tested on pre-prod env)  -> [Hotfix: removed reason dropdown based on condition [CONFIG-398] (!313) · Merge requests · Stratumn …]
> Thank you.

**Project paths:** `stratumn/configuration/conduent/claims-assignments` ×43, `stratumn/configuration/agre-retrocession-ta-ff-generator` ×13, `stratumn/configuration/agre-renewal-generator` ×7, `stratumn/configuration/agre-cc-ta-ff-pp-generator` ×1.

---

## ⏮ Reviews

80 primary MR requests in 200 messages — the highest density of the three. 7 senders (**Clément BOSLE 47**, Benjamin GONZVA 47, Narendra KUMAR 43, Nathan CAPIAUX 33, Matthieu SAJOT 20, Deepak YADAV 9, Nicolas DOUCHIN 1). Mixed language, 20/80 request bodies French.

The terse channel:

- **Channel mention optional — 42/80 (53%).** Name tokenises to two spans (`⏮` `Reviews`).
- **Bare GitLab URL as the last line**, 87 anchors are the raw URL.
- **No sign-off — 4/80 (5%).** The message just ends on the URL.
- **The ask includes the apply step:** `Could you please review and apply it?` — this is IaC, the reviewer runs terraform.
- **Linear as a URL: 1/80.** The `CORE-nnnn` id goes in the subject as bare text.
- Subject: `[<Platform or cluster>] CORE-nnnn <what>` — e.g. `[Asterix-prod] CORE-5470 Install KEDA [env/dev --> env/prod]`, `[aws siem] guarduty module`, `[Databricks] - SCP policies`. 78/80 have one.

Representative, Narendra KUMAR 2026-07-31, subject `[CORE-5439] Verify heka.ai domain to enable SES (NWC Chatbot Authentication and Password Reset)`:

> Hello @⏮ @Reviews,
> Here is the MR to update the CNAME records in heka.ai to enable AWS SES for the NWC Chatbot. Authentication is configured using Cognito, and SES is required to send emails for password reset and other authentication-related emails.
> could someone please review and apply it?
> https://git.sia-partners.com/cloud/aws/dns-hostedzones/-/merge_requests/122

French variant, Benjamin GONZVA 2026-01-22, subject `[Prolix] - Refacto (débile) de crossplane`:

> Yo @⏮ @Reviews, on l'avait jamais fait avant, mais j'allais bosser sur crossplane et c'était impossible de le faire sans ce refacto : j'ai rebougé tous les fichiers pour qu'ils soient comme on le fait partout (au niveau des values). Ça prend 5 mn à review, et rien ne change dans le diff de helmfiles, hormis le screen que je vous met en dessous.
> https://git.sia-partners.com/k8s/prolix/helmfiles/-/merge_requests/103
> _Chaud que vous regardiez assez vite (c'est rapide); j'en ai beosin pour mes MR suivantes_

**Top project paths:** `cloud/aws/dns-hostedzones` 11 · `k8s/prefix/tf-main` 9 · `k8s/obelix/helmfiles` 8 · `k8s/obelix/tf-main` 8 · `k8s/prolix/helmfiles` 6 · `k8s/prefix/tf-platforms` 5 · `k8s/asterix/tf-platforms/risk-control` 5 · `cloud/aws/security` 4 · `iac-projects/code-assist` 4 · `k8s/prefix/helmfiles` 4 — then a long tail across 48 distinct projects.

---

## Wrong venues, ruled out with evidence

| Channel | Why never |
|---|---|
| **Heka.core - Update Alerts** `19:b22a4db9472040859f5efac89f522316@thread.tacv2` | **0 MR links and 0 GitLab links in 62 messages.** Outbound announcement broadcast to a consumer audience — maintenance windows, breaking changes ("We will do an update on the prod cluster (obelix - AWS) on thursday morning… / update is starting / update is finished"). The reviewers aren't the audience. Writable, but only for that purpose. |
| **📣 Alerting 📣** `19:4a8ad1c1d15847f5826a75328438b6ec@thread.tacv2` | Bot feed. 176 of the last 200 raw messages are undisplayable bot cards; the readable ones are `grafana@sia.partners` `[FIRING:n]`/`[RESOLVED]` MJML emails. **Last human message: 2025-03-13.** 0 MR links ever. |
| **Heka Core - Chat room** `19:244a4a040e314ca084ae179aee91b868@thread.v2` | `thread.v2` group chat — **0/199 messages have a subject**, so it cannot carry a titled post at all. 3 senders. 1 GitLab link in 199 messages, a bare diff-line deep link. |
| **Heka Core** `19:99a52bbe7b5f468383a41791dc852742@thread.v2` | The grey area, still no. 6 MR links in 170 messages, all mid-thread nudges ("Raised an MR for this, if anyone could review, as we have to deliver it today itself 🙂"). **0/170 have a subject.** The same people file properly in ⏮ Reviews and only nudge here. |

**Structural rule behind all of this:** `thread.tacv2` = a real Teams channel, supports a titled post. `thread.v2` = a group chat, no titles. Every valid MR venue is `tacv2`, and in all three the `subject` field is load-bearing.

---

## What `teams chat-send` cannot reproduce — and the tool that can

**Use `tools/teams_post.py` for titled, mentioning channel posts.** The limits below are `chat-send`'s, and they are why that tool exists. The mention payload it emits, read back off a real post in the channel:

```json
[{"@type":"http://schema.skype.com/Mention","itemid":0,
  "mri":"19:yf2-R9Z4M9-ba9--x4Qrsah6Y0-mW4v3GQ159M-Dogs1@thread.tacv2",
  "mentionType":"channel","displayName":"[Run]"},
 … itemid 1/2/3 for "Engine" / "merge" / "requests", same mri …]
```

One object per whitespace-separated word, each bound to the `<span itemid="N">` of the same index, `properties.mentions` carrying it as a **JSON string**. **The MRI is the channel's own conversation id** — not the `groupId` in the channel deeplink, not the channel's `…@fr.teams.ms` SMTP address. `properties.subject` is a plain string alongside it. Confirmed live: a message sent that way reads back with `subject` set; a `chat-send` message reads back `None`.

### The `chat-send` limits themselves

Verified in `/home/claude/.local/share/pipx/venvs/microsoft-teams-cli/lib/python3.12/site-packages/teams_cli/client.py`:

- **`send_message` (lines 284-322) has no `subject` key at all**, and `"mentions": "[]"` is hardcoded at line 313. The file-send path hardcodes both (`"subject": ""` at 1018, `"mentions": "[]"` at 1022). `grep -rn 'mentions' teams_cli/` returns only those two lines — no flag, no helper, no MRI resolution anywhere.
- So: **no titled post, and no channel mention, therefore no notification.** Hand-writing the `<span itemtype="http://schema.skype.com/Mention" itemid="0">` markup renders as inert text — the itemid→MRI binding lives in `properties.mentions`, which is never populated.
- **Raw HTML does pass through verbatim.** `client.py:292` only wraps content that doesn't start with `<`. So `<p>`, `<p>&nbsp;</p>`, `<a href title>`, `<ul>/<ol>/<li>`, `<code>` and Unicode emoji all work.
- Plain text with `\n` → one `<p>` per non-blank line (`client.py:293-295`); **blank lines are dropped**, so plain-text mode can't produce the `<p>&nbsp;</p>` spacer every real post has.
- A raw channel id works as the target — `_resolve_chat_id` (`client.py:1231-1241`) returns the argument unchanged when it contains a `:` plus either an `@`, a `48:`/`28:` prefix, or a length over 50 characters.
- Teams' own client-side auto-linkification (the `itemtype="http://schema.skype.com/HyperLink"` + `itemid=<uuid>` form) can't be reproduced. A bare URL sent via the CLI still renders clickable, just without that markup; `<a href="URL">URL</a>` is the closest faithful copy.

Net: a CLI-sent MR request has the right words, no title, and pings nobody. Offer the user the draft-and-paste path when the ping matters.
