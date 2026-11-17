# Setup

Reel maker needs no account, key or outside connection. It runs on a Studio workspace from a clone of this repo.

1. **Clone** into the workspace (from `/home/user/workspace`):
   `git clone <repo url> .external_worktrees/reel-maker`. A private repo is cloned through the workspace's GitHub
   connection.
   Check: `ls .external_worktrees/reel-maker/app.toml` exists.
2. **Check the port.** The app listens on 8100. `grep -l "8100" system/supervisord.conf.d/*.conf` must name nothing
   else. If it does, change 8100 in `workspace/supervisord/reel-maker.conf`, in `deploy/install.py` (`HEALTH_URL`)
   and the default `PORT` in `src/reel_maker/runner.py`. Never use 8091: the Screen's video server needs it.
3. **Install and start:** `python3 .external_worktrees/reel-maker/deploy/install.py`.
   Check: it ends with `reel-maker is answering at http://127.0.0.1:8100/health`.
4. **Open it:** `uv run --no-sync workspace-layout open reel-maker --beside`.
   Check: the welcome screen reads "Make a reel about an app you built".
5. **Phone (optional):** the QR code on "Film your take" only works once the workspace is shared (the `use-from-phone`
   skill). Check: `uv run --no-sync workspace-layout list` prints a `link` for reel-maker on the shared domain, and the
   link shown under the QR code starts with it.
6. **Save the wiring:** commit `system/supervisord.conf.d/reel-maker.conf` in the workspace.

The app depends on the workspace's shared `system/libs/app_schema` (the API document every app serves), found by
relative path from the clone, so the clone must sit at `.external_worktrees/reel-maker/`.
