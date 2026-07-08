# Contributing

Thanks for hacking on this. It's a small, deliberately dependency-light project
(one `bridge.py` runtime, `urllib` over `requests`, regex over an HTML parser for
the fixed Teams markup) — keep changes in that spirit.

## Dev setup

You don't need Teams/Telegram credentials to work on the routing logic — the
test suite stubs all network + subprocess calls.

```sh
git clone https://github.com/Cyberoiide/teams-telegram-bridge
cd teams-telegram-bridge
pip install -r requirements.txt pytest

export TELEGRAM_BOT_TOKEN=test:token TELEGRAM_GROUP_ID=-100999
python -m pytest -q                 # full suite
python -m pytest tests/test_reactions.py -q     # one file
python -m py_compile bridge.py token_mint.py    # what CI syntax-checks
```

Running it for real (against your own account) needs the full auth setup — see
[docs/SETUP.md](docs/SETUP.md).

## How it fits together

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before touching auth or the
poll/state code. Short version: three threads in `main()` — inbound poll,
outbound Telegram long-poll, token refresh — sharing a locked `state` dict.
`render_text` turns Teams HTML into Telegram HTML.

## Sending a change

1. Branch off `main`: `fix/<name>`, `feat/<name>`, or `chore/<name>`.
2. Keep the diff small and the solution boring. Reuse the existing helpers/maps
   before adding new ones. This repo has **zero runtime deps beyond playwright** —
   don't add one for what a few lines of stdlib can do.
3. Non-trivial logic (a branch, a parser, a state change) leaves **one runnable
   test** (`tests/test_*.py`, mocked — no fixtures/frameworks beyond pytest).
4. Deliberate shortcut with a known ceiling? Mark it with a `# ponytail:` comment
   naming the limit and the upgrade path, so it reads as intent, not an accident.
5. Open a PR. CI runs the suite on Python 3.10–3.12; it must be green.

## Conventions

- **Correctness before cleverness.** Every feature here has had a bug that only
  showed up against the live bridge — mocked tests don't prove it works, so
  describe how you exercised it for real in the PR.
- No new dependencies without a clear reason it can't be stdlib.
- Match the surrounding style (comment density, naming). No AI-assistant
  attribution in commits, PR titles/bodies, or release notes.

## Reporting bugs / ideas

Open an issue. For anything touching auth/tokens, **never paste a real token,
PRT cookie, or `~/*.jwt` contents** — they're live bearer credentials.
