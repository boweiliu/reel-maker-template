---
name: import-reel-maker
description: Install Reel maker (an app that walks you through making a short vertical reel about an app you built in Studio) on a Studio workspace from its repository, or update an existing install. Use when someone asks for Reel maker, a reel or promo-video walkthrough app, or gives this repo's URL.
---

# Install or update Reel maker

The app lives in its own repository and runs from a clone at `.external_worktrees/reel-maker/`. It needs no account,
key or connection. Run everything from the workspace root (`/home/user/workspace`).

1. **Get the code.** New install: `git clone <repo url> .external_worktrees/reel-maker`. Update:
   `git -C .external_worktrees/reel-maker pull --ff-only`.
2. **Check the port.** The app uses 8100. If `grep -l 8100 system/supervisord.conf.d/*.conf` names another program,
   follow `docs/setup.md` step 2 to pick another.
3. **Install and start:** `python3 .external_worktrees/reel-maker/deploy/install.py`. It must end with
   `reel-maker is answering at http://127.0.0.1:8100/health`; if not, read `/var/log/supervisor/reel-maker-stderr.log`.
4. **Install the reel skill** the app is built around, if the workspace lacks it:
   `cp -r .external_worktrees/reel-maker/skills/make-app-reel .agents/skills/`.
5. **Show it:** `uv run --no-sync workspace-layout open reel-maker --beside`.
6. **Save the wiring:** commit `system/supervisord.conf.d/reel-maker.conf` (and `.agents/skills/make-app-reel/` if you
   copied it) in the workspace.

The phone page needs the workspace shared (the `use-from-phone` skill); without it the QR code has no address a phone
can open.

## Keep the app in its own history

The installed copy is its own repository; keep it that way:

1. The app stays at `.external_worktrees/reel-maker/` (gitignored by the workspace), never under `system/apps/`.
2. To start your own history instead of tracking this one: `rm -rf .external_worktrees/reel-maker/.git` then
   `git -C .external_worktrees/reel-maker init && git -C .external_worktrees/reel-maker add -A && git -C
   .external_worktrees/reel-maker commit -m "Reel maker"`.
3. Optionally push it to a private repo of your own.
4. The workspace refers to it by config alone: `system/supervisord.conf.d/reel-maker.conf`.
5. Never copy the app's files into the workspace's own tree.
6. Check: `git -C .external_worktrees/reel-maker log --oneline -1` shows the app's history, and `git status` in the
   workspace shows no app files.
