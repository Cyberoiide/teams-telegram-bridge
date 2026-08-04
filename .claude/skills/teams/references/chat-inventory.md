# Chat inventory and send verdicts

Surveyed 2026-08-04: **218 unique chats** from `teams chats` plus `48:notes` (never listed) = **219 addressable**.

Buckets: 77 meeting side-channels · 56 one-to-one DMs · 45 ad-hoc group chats · 33 team channels · 3 bot feeds · 1 self chat.
Verdicts: **1 free to write · 4 purpose-bound · 112 ask-first · 102 never.**

Pagination notes: `teams chats --offset` works in pages of 60 up to ~240 entries (`--offset 240` → HTTP 400), **but pages overlap** — 240 raw entries contained 22 duplicates. Always dedupe by `id`. Two passes minutes apart gave the same 218 ids with zero difference, so the set is stable. There may be older chats the API won't paginate to at all.

---

## Free to write

| id | what |
|---|---|
| `48:notes` | **Notes to self** — the user's own chat. Verified: every message is from Clément BOSLE, contents are bridge test artifacts. The only safe target for tests, scratch messages and self-driven end-to-end checks. Never appears in `teams chats`; addressed by this fixed id. |

## Purpose-bound — the drafted text and the target both need the user's confirmation

| id | channel | may carry, and nothing else |
|---|---|---|
| `19:yf2-R9Z4M9-ba9--x4Qrsah6Y0-mW4v3GQ159M-Dogs1@thread.tacv2` | **[Run] Engine merge requests** | MR review requests for `git.sia.partners/stratumn/platform/*`. `topic` is `null` in the listing (private channel) — findable only by this id. |
| `19:f4b2e5764ffd4762b1f05697045eb35f@thread.tacv2` | **[Run] 🔄 Config Merge Requests** | MR review requests for `git.sia.partners/stratumn/configuration/*` |
| `19:8c31731328ee49e09e055dba5f9055a7@thread.tacv2` | **⏮ Reviews** | MR review requests for `git.sia-partners.com/**`. The user's busiest channel (47 of the last 200 messages). |
| `19:b22a4db9472040859f5efac89f522316@thread.tacv2` | **Heka.core - Update Alerts** | Planned-maintenance and incident notices only. 0 MR links in 62 messages — never file an MR here. |

Why only these four: they are the channels the user demonstrably posts to himself, and where essentially all traffic is a single message shape. Anything off-shape is visible to the whole Heka.core / Run team.

See `mr-message-format.md` for the per-channel format and the routing rule.

---

## Never write

### Every meeting side-channel — 77 of them

Any id matching `19:meeting_...`. Transient, tied to a calendar event, wrong venue for everything. Examples: `[Stratumn] Daily`, `📅 Sprint Planning`, `URGENT ISO 27001`, `Titularisation Faustin & Clément` (HR), `Onboarding - Introduction to Data Science`.

### Bot and alerting feeds — posting here pages people

| id | what |
|---|---|
| `19:4a8ad1c1d15847f5826a75328438b6ec@thread.tacv2` | **📣 Alerting 📣** — Grafana webhook (`grafana@sia.partners`, identity `28:integration:9e7ylk7fa5`) + a Power Automate `Workflows` connector. Last human message 2025-03-13. |
| `19:AOt-7oJPjyaZ5NkNd313SjJS-ndWEiMxh3BPOuNZ-dY1@thread.tacv2` | Prod alerting channel, bot `prolix`, CrashLoopBackOff alerts. |
| `19:5f5e928f-4aa0-4efa-a680-e3c9abb77439_a0ae26dd-6597-42db-9382-309fb7a270b3@unq.gbl.spaces` | **HEKA-SOS** support bot. Replies are automated, but it plausibly files real SOS/ops tickets — treat as never. |

### Firm-wide and leadership audiences

| id | what |
|---|---|
| `19:eIyR8uPENYpGFze3c1dUjRgdexp7AtU-g9tY1OTE_CY1@thread.tacv2` | **Sia Group** — whole company. CEO Matthieu COURTECUISSE posts here. |
| `19:83n42Zrf_A1t2xzWf58SKB0jGu7GXDWCwJiRTOkbDBs1@thread.tacv2` | **FIM** business unit. CEO participates. |
| `19:b8b73df873ec487d90342e5f6e5a9582@thread.tacv2` | **Sia AI Ecosystem** — 35 distinct senders in 50 messages. |
| `19:275b3a023316442eb7466b30f5456a87@thread.tacv2` | **Squad Race for $ia Tok€ns** — 27 senders across BE/NL/FR, marketing. |
| `19:a7d38c5846934d4dbfbf9af43856feef@thread.tacv2` | **Sia Sport** — 23 senders, company-wide, contains bank details. |
| `19:6JVcMNAfcl3vWGotv8aIfwGg3LAn2Aea8qxkmVA2Y3c1@thread.tacv2` | **Paris** office channel — lost-and-found, office notices. |
| `19:gQhqUe3gdm-0km7aithBdYsnx0uSkjcB9emqfPm16fg1@thread.tacv2` | Sentier office, explicitly for "informations de hautes importances". |
| `19:cNYF6-h3uRMw9Q1g4MLAoO9Nw1JZmc3urA31Bf2SV5w1@thread.tacv2` | **AD&Q** (General) — department-wide. |
| `19:_t5QsS-wuqzE76OembSGD_xVL1SR4BnPv4R2xfW3suU1@thread.tacv2` | **AD&Q_AIF** (General) — org-unit broadcast. |
| `19:cHtOZzcT2pDoGn2VIPS89acRplA4QG__Vrs26RaO7Fs1@thread.tacv2` | **AD&Q_LAB_ENG** — 11 senders, 8 channel-wide pings. |
| `19:uPWGdS1lAvoUS_rpoICZ5y96I8wMMmRku0VU1l6Zho41@thread.tacv2` | **AD&Q_LAB_GEN** — lab-wide announcements. |
| `19:OT3-CcXUEOlujV9i5Lyd8AGRL0LyOPsU8YtgQoAu8K41@thread.tacv2` | **AD&Q_LABS** — all labs. |
| `19:3a966a990ad44998a66badeba58654ea@thread.tacv2` | **Bot Family 🥐** — 21 senders, 9 channel-wide pings. |
| `19:96bfc4df825945cb9485540e6d8f0081@thread.v2` | **La nouvelle vague des stages** — one organiser broadcasting to the whole intern cohort. |

### Client-facing / cross-tenant — external people are in the room

| id | what |
|---|---|
| `19:NcXo1CZ7h4gcGfKooiHz0rbyF1bxK-tkAYIJ6D1Vhdk1@thread.tacv2` | Stratumn client defect triage (Jeremy MEYERSON, Swarina PALKAR, James BASSE). |
| `19:xmY4_k-kYN7uMPSd2QGINBjJYL3JVU-48FPsZW-TmWg1@thread.tacv2` | SPEN/PRAE client platform incidents (Gavin CONNOLLY, Joel RICHARDS, Sebastien GERBER). |
| `19:4_eEzNwqHkkUPGUdhWxyuVH6f65YgooJNuD6_YkvcBc1@thread.tacv2` | Solutions & IP / Teams Square — cross-geo US/APAC. |

### Large support queues — a post creates real work for named engineers

| id | what |
|---|---|
| `19:7953d5539ca143ae974936607d72ef1b@thread.tacv2` | **Claude - Support Center** — 26 distinct senders in 50 messages, US/UK/FR/IN. |
| `19:475ed233586e4edfa77544ead11d5157@thread.tacv2` | **🚨 SiaGPT - Support Centre** — 18 senders, US/UK/IT/PL. |
| `19:f7947d3118284ba7a7e709f41520624e@thread.v2` | **Claude Certified Architect** — 8 senders in 10 messages, broad cross-BU cohort. |

### Unidentifiable — thin evidence means never

| id | why |
|---|---|
| `19:km3NugRD3v5phmqbCx4aV2VKauQFVxXlYy3PC1nx8HU1@thread.tacv2` | read returns 403 Forbidden |
| `19:5UiLrSMRVLdz6e5LigUvHRcQNqOx6oJd5wxJW1GSVAU1@thread.tacv2` | 0 readable messages at `-n 50` |
| `19:a8b352608e0e4c5d9f5a3211e82de974@thread.v2` | 0 readable messages at `-n 50` |

---

## Ask first — everything else (~112 chats)

Real human venues. Sending needs the user's explicit confirmation naming *that* chat; approval for one never carries to another.

**Deliberately not listed by id here.** Hand-copying 56 DM GUIDs into a doc invites a transcription error that would send a message to the wrong colleague, and the roster changes as people join and leave. Resolve the id at read time instead:

```sh
teams chats -n 60 --json > /tmp/chats.json          # add --offset 60/120/180 and dedupe by id
python3 - <<'EOF'
import json, subprocess
seen = {}
for off in (0, 60, 120, 180):
    r = subprocess.run(["teams","chats","-n","60","--offset",str(off),"--json"],
                       capture_output=True, text=True)
    for c in json.loads(r.stdout).get("data", []):
        seen.setdefault(c["id"], c)
for cid, c in seen.items():
    if c["id"].startswith("19:meeting_"):
        continue
    name = c.get("topic") or ""
    if not name:                                    # unnamed: identify by who talks in it
        m = subprocess.run(["teams","chat",cid,"-n","5","--json"],
                           capture_output=True, text=True)
        try:
            msgs = json.loads(m.stdout).get("data", [])
        except Exception:
            msgs = []
        others = {x["sender"] for x in msgs if not x.get("is_from_me")}
        name = "DM/group with " + (", ".join(sorted(others)) or "?")
    print(f'{c["chat_type"]:8} {cid}\n         {name}')
EOF
```

Then read a few messages of the candidate chat and check it against the verdicts above before proposing a send.

### Notable ask-first chats worth knowing about

**Sensitive enough to treat as near-deny** — technically ask-first, but push back before sending:

| id | why |
|---|---|
| `19:c0cfbad9c4924860a5cc4caea6d58651@thread.v2` | Active compliance escalation — contains "JE N'AUTORISE AUCUN TEST SUR VERCEL !" |
| `19:808e706e7e5145fd9f48114fd0688d90@thread.v2` | **CYB x ISO 27k** — audit evidence collection |
| `19:16420d4ed5cc43ee966bfcb4b01f6ede@thread.v2` | Production DB credentials / access help |
| `19:5f5e928f-4aa0-4efa-a680-e3c9abb77439_78fb0520-8881-4a97-b859-7743bb3f1983@unq.gbl.spaces` | **IT Servicedesk** — a shared service queue; a message here files a real ticket |

**Team channels the user works in day to day:**

| id | channel |
|---|---|
| `19:fd3bd1cd00654c208943ffa370971066@thread.tacv2` | 💠 General (Heka.core) — 7 senders |
| `19:653a674ea48d402a9d9da6734b348590@thread.tacv2` | 🤔 Questions and Help (Heka.core) — 6 senders |
| `19:d4281eab227742a5becb3b1fcd3c2a04@thread.tacv2` | 🖥️ HEKA Core - SiaGPT — ops/incidents |
| `19:vh8DT4eodOrSdUzlGgXmhGJv9H8jnTXpuaNigv1ipOc1@thread.tacv2` | 🖥️ HEKA Core — infra debugging |
| `19:fb9105cfa1da4bf3a69fdc52cc39e605@thread.tacv2` | [Run] 👨‍💻 Devs — Stratumn run team, 6 senders |
| `19:TUUHtNIyGzgjpAlZz6bhEsFsBRrn9GQhzTU3Ez7w4p41@thread.tacv2` | Stratumn/Run — Général, 10 senders |
| `19:xccCYlZezi4-gc25Y4U_71Goisbj0-cGRKVIxpKXY0E1@thread.tacv2` | Heka.core leave/HR planning |
| `19:efa7cdbbff3a48008a49765e7aac9759@thread.tacv2` | 📚 Literature — link sharing, 10 senders |
| `19:gS5OBv338u6hnLZEcXEZfKcB2CGTp3LRG1Bhy71K6CQ1@thread.tacv2` | Lab Eng tech links / watercooler, 13 senders |
| `19:b328fbc936ca4833b6c6b34824d628b8@thread.tacv2` | 🤔 Questions (AD&Q_LAB_ENG) — 15 senders |

**Group chats seen most often:**

| id | chat |
|---|---|
| `19:21d2695ae8ff4e25ace9c662e5c326cb@thread.v2` | **St🐀umn Core** — already contains `@claude` agent invocations |
| `19:244a4a040e314ca084ae179aee91b868@thread.v2` | Heka Core - Chat room — 3 senders, French banter |
| `19:99a52bbe7b5f468383a41791dc852742@thread.v2` | Heka Core — ops/incident working chat |
| `19:155129b3244d46f9a9918f09b192706a@thread.v2` | Anthropic COE @ Sia — cross-geo HK/US/FR |
| `19:dc136de7ceb9490cad3167df8b6ac6b9@thread.v2` | US - Claude Workshop Prep |
| `19:eb8ace1c29d84b89a7ce879fa2bce60d@thread.v2` | Claude Code Training |
| `19:904beff8565a4066b535b432b1c2ff31@thread.v2` | 🗿 — private banter |

**One-to-one DMs — 56 named colleagues.** Resolve ids with the snippet above. Counterparts seen: Clément DELBARRE, Matthieu GAUCHER, Théophile WALLEZ, Benjamin GONZVA, Matthieu SAJOT, Narendra KUMAR, Nathan CAPIAUX, Deepak YADAV, Ghiles CHERFAOUI, Simran DUBEY, Oussama MIFDAL, Gwenaelle LEFEUVRE, Amayas ALLAM, Matthias PICARD, Mathieu PERAN, Walid GUEMIL, Youssef SOUANE, Alix SIMIER, Simon BAYLE, Ariel GUIDI, Antonin LEMENAGER, Benjamin CHANSAVANG, Srikar GIRIDHAR, Maxime BROUILLARD, Romy HO, Mélanie LESCHER, Sébastien YUNG, Adrien CHAILLOUT MORLOT, Paul PLANCHON, Pierre PHU, Zachari AHRIPOU, Jean VAN HECKE, Jakub KARASINSKI, Carlos FABBRI GARCIA, Saad SHEIKH ARSHAD, Gauthier SIMON, Clément CALOIN, Dereck MEYAM EWANE, Chloé COURSIMAULT, Flora CHATARD-LHERM, Faustin MOUNIER, Nicolas JOW, Dewone MORCHOISNE, Jan KUNNEN, Nicolas WATTELLE, Abdessalam ZAIMI, Pierre MICHIELIN, Arthur PHAN, Diwakar JHA, Thomas AUBLE, Nicolas LEFORT, Fabien ADOKPO MIGAN, Gwenaëlle SAN-JUAN, plus two unresolved (the user is the sole sender; one greets "Hello Yasmine !").

---

## Refreshing this inventory

It will drift — people join, channels get created, chats fall out of the 240-entry window. Re-derive it with the snippet above rather than trusting these names indefinitely. The four purpose-bound ids and `48:notes` are the stable part; treat the rest as a snapshot.

`teams user-search` cannot help resolve counterparts — it needs a `substrate` token that isn't in the cache (`"Auto re-login failed"`). Only `ic3` and `graph` are minted.
