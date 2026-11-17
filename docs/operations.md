# Operations

- **Restart after a code change:** `python3 .external_worktrees/reel-maker/deploy/install.py` (it restarts the program
  when the entry is unchanged), or `uv run --no-sync system/scripts/workspace_scripts/verify_app.py reel-maker --restart
  --marker "Make a reel" --refresh` to restart and refresh open windows.
- **Logs:** `/var/log/supervisor/reel-maker-stderr.log` (requests, errors, content-policy blocks).
- **Data:** none yet. The mock stores nothing; the example videos ship in `examples/`. Real state will live under
  `data/.apps/reel-maker/` (`REEL_MAKER_DATA_DIR` overrides it).
- **Stopped when unused:** `stop_when_no_windows = true`, so the shell stops it a minute after its last window closes
  and starts it on the next request. A phone visit wakes it too.

## Stalled reels

The app checks every reel with a step in progress every 30 seconds (`src/reel_maker/watchdog.py`), from outside the
chat: the chat app's view of the chat, when it or the reel folder last changed, free memory, and the memory guard's
record of what it stopped. It does this with no window open (`stop_when_no_windows = false`).

| What it sees | What it does |
| --- | --- |
| The chat's turn ended, or it reported a failure, with the step not done, for 2 minutes | Sends the same step again (a stopped chat is started by the send), up to 3 times |
| Under 700 MB free when it would repair | Waits up to 10 minutes for memory, then repairs anyway |
| The chat mid-turn but silent for 15 minutes | Says so on the waiting screen |
| ... for 30 minutes | Stops the chat and sends the step again |
| 3 repairs used up, or the chat deleted | Stops; the waiting screen offers "Try again" and the link to the chat |

Everything it notices and does goes to the reel's `health.json` and shows on the waiting screen.

## When something looks wrong

| What you see | Cause and fix |
| --- | --- |
| Phone shows "Starting up..." forever, the app works on the computer | The workspace's sharing router is sending the visit somewhere else. Check the app's registered address matches the port it listens on (`grep -A2 'name = "reel-maker"' data/.state/apps.toml`), and look for leftover routers: `ps -o pid,ppid,lstart,args -C caddy,frpc`. Any caddy or frpc with parent pid 1 is a leftover from a sharing-service crash; stop it. This is a known Studio bug (reported to Imbue 2026-11-11 and 2026-11-17). |
| Videos on the footage or reel screens are blank | `curl -s -o /dev/null -w "%{http_code}" localhost:8100/_media/deck-list-reel/deck-list-reel.mp4` should be 200; otherwise `examples/` is missing from the clone. |
| No QR code, or it points at `localhost` | The workspace is not shared, so there is no address a phone can open. Turn sharing on. |
| Share button missing on a computer | Expected: only devices that can share a video file (mostly phones) show it. The platform buttons save the video, copy the caption and open the upload page instead. |
