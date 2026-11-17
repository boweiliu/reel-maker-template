# Reel maker

An Imbue Studio template. To install it on a workspace, ask your agent: "Install Reel maker from
https://github.com/boweiliu/reel-maker-template" (it follows `skills/import-reel-maker/SKILL.md`). MIT licensed; the
`make-app-reel` skill in `skills/` is Lauren's, shipped unchanged.

A Studio app that walks you through making a short vertical reel (Reels / TikTok / Shorts) about an app you built in
Studio. It is the app around Lauren's `make-app-reel` skill (shipped unchanged in `skills/make-app-reel/`): you answer
the interview as a survey, see the script play as a storyboard, film your take on your phone from a QR code, and get
the finished reel with save and share buttons.

**Status: working.** Picking an app starts a Studio chat for the reel (the reel agent), which follows Lauren's skill,
read from the copy in `skills/make-app-reel/` and left unchanged. The app adds only a short agreement on where to put
the work (`docs/agent-contract.md`, about 30 lines). The app watches each chat and repairs a stall itself
(`src/reel_maker/watchdog.py`). Run end to end with a real chat on 2026-11-17 on the Deck List app.

## What you can try

- **Example run** (`/?example=1`, or "See an example run first" on the welcome screen): the whole flow filled in with
  the Deck List reel. Every step in the list can be clicked to jump straight to it. Nothing is saved.
- **The walkthrough** (`/`): seven steps (pick your app, answer questions, pick a tone, see your script, check the
  footage, film your take, watch your reel), with a waiting screen whenever Studio is working.
- **The phone page** (`/phone`, reached from the QR code or the link on "Film your take"): the script in large type, a
  big button that opens the phone's camera, every take kept with "Use this take", and the finished reel with save and
  share buttons.

## How it works

One Flask server (`src/reel_maker/runner.py`) serves two pages and their scripts:

| Part | Where |
| --- | --- |
| Server: pages, QR codes, example videos, the app's public address, the reel API | `src/reel_maker/runner.py` |
| Reels on disk and their Studio chats | `src/reel_maker/reels.py`, `docs/agent-contract.md` |
| Noticing a stalled chat, telling the creator, repairing it | `src/reel_maker/watchdog.py` |
| Walkthrough (computer and phone layouts) | `src/reel_maker/assets/wizard.html`, `wizard.js` |
| Phone page: script and record button | `src/reel_maker/assets/phone.html`, `phone.js` |
| Save and share the finished reel | `src/reel_maker/assets/share.js` |
| Styles | `src/reel_maker/assets/style.css` |
| Example run's videos | `examples/deck-list-reel/` |
| Lauren's reel instructions (what the real version will run) | `skills/make-app-reel/` |
| Install on a workspace | `deploy/install.py`, `workspace/supervisord/reel-maker.conf` |

The QR code points at the app's address on the workspace's shared domain, which the server asks the workspace shell
for (`/api/inventory`), so a phone signed in to the workspace can open it.

## Install, run, test

From the workspace root, with this repo cloned at `.external_worktrees/reel-maker`:

```bash
python3 .external_worktrees/reel-maker/deploy/install.py      # install or update, start, check /health
```

Tests (from the repo folder):

```bash
uv run --no-sync --project . pytest -q src test_reel_maker_ratchets.py
```

More in `docs/`: `setup.md`, `operations.md`, `design.md`, `agent-contract.md`, `tests.md`.
