# Rich formatting Teams → Telegram

**Branch:** `feat/rich-formatting` (off main / v0.3.0)
**Date:** 2026-07-08

## Goal

Teams sends rich HTML; today `render_text()` strips every tag, so bold, italic,
code, and @mentions arrive in Telegram as flat text. Replicate the common Teams
formatting in Telegram, which accepts a whitelist HTML subset via
`parse_mode=HTML`.

## Scope (A)

bold, italic, underline, strikethrough, inline code, code blocks, @mentions.

Out of scope: lists (Telegram has no list tags), tables, colours, headings.

## Constraint

Blazing fast, no over-parsing. One linear pass of regex substitutions — **no**
`HTMLParser`, no state machine, no DOM. Fits the file's existing regex idiom.
No new imports.

## Conversion map

| Teams HTML | Telegram HTML |
|---|---|
| `<strong>`, `<b>` | `<b>` |
| `<em>`, `<i>` | `<i>` |
| `<u>` | `<u>` |
| `<s>`, `<strike>`, `<del>` | `<s>` |
| `<code>` | `<code>` |
| `<pre>` | `<pre>` |
| `<span itemtype=".../Mention">Alice</span>` | `<b>@Alice</b>` |
| everything else | tag dropped, text kept |

Mentions render `@<display name>` (Teams gives the display name, not a handle).
No live link — Telegram can't ping Teams users.

## Escaping — placeholder-swap (the one hazard)

Output now contains real tags, so we can't `html.escape` the whole string (would
break `<b>`) nor leave it unescaped (injection). Solution — sentinel swap:

1. emoji `<img>` → `alt=""`  *(unchanged)*
2. Mention span → `\x00b\x00@` + name + `\x00/b\x00`
3. known format tags → sentinels (`<strong>`→`\x00b\x00`, `</strong>`→`\x00/b\x00`, …)
   via one dict-backed `re.sub`
4. block-break tags (`<br> </p> </div> </li>`) → `\n`; strip all remaining tags
5. `html.unescape` then `html.escape` the whole string once — text now safe
6. swap sentinels back to real Telegram tags

`\x00` cannot appear in Teams HTML text, so it's a safe sentinel. Injection-safe:
step 5 escapes everything that is not a sentinel. Linear, ~6 substitutions.

## Caller change

`render_text()` now returns final Telegram-ready HTML. `deliver_message`
(bridge.py:~540) must **stop** `html.escape`-ing this branch:
`f"{header}: {render_text(...)}"` instead of escaping `text`. The raw
`text_content` fallback (when content render is empty) still gets escaped.

## Untouched

Reply-quotes (`format_reply` already emits its own escaped HTML), emoji, inline
images, attachments, reactions.

## Tests (`tests/test_formatting.py`)

- each tag maps correctly (bold/italic/underline/strike/code/pre)
- `<strong>`/`<em>` aliases map same as `<b>`/`<i>`
- Mention span → `<b>@Name</b>`
- injection: `<script>`, stray `&` and `<` in text are escaped
- unknown tag dropped, its text kept
- emoji + formatting in one message both survive
