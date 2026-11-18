# Tests

From the repo folder, after `deploy/install.py` (or `uv sync --project .`) has built the venv:

```bash
uv run --no-sync --project . pytest -q src test_reel_maker_ratchets.py
```

Nothing calls an outside service: the chat app is a stand-in (`src/reel_maker/fake_chat.py`) and the reel agent is a
stand-in that writes the files `docs/agent-contract.md` describes, quoting the inputs it read so a test can see an
input travel the whole way round. No test creates a real Studio chat.

- `src/reel_maker/runner_test.py`: the app's API document matches its manifest and covers every route.
- `src/reel_maker/api_test.py`: the API through Flask's test client, with the fake chat app and the stand-in agent:
  creating a reel, each stage's inputs and the change-request rules, takes streamed to disk (a 100 MB one, an empty
  one, a dropped one), choosing a take, files served only from inside the reel's folder, retry, double clicks.
- `src/reel_maker/watchdog_test.py`: the stall watcher's decisions with the chat, memory and the memory guard's
  record faked (idle, quiet, failed, gave up, waiting for memory, deleted chat, unreachable chat app).
- `src/reel_maker/browser_test.py` (marked `browser`): the pages in the workspace's browser (Fortress), served by an
  in-process server on a free port: the example run, a real reel through every screen with the stand-in agent, the
  phone page (script, upload with progress, choosing a take, the finished reel only once the edit is done) and the
  waiting screen's stall messages.
- `test_reel_maker_ratchets.py`: code-safety ratchets and the type check over the app's own code (`skills/` is
  excluded: Lauren's reference scripts ship unchanged).

Run only the browser tests with `-m browser`, or leave them out with `-m 'not browser'`. They launch one browser per
test file and close it afterwards; the workspace is short of memory, so run one browser at a time.

Not covered by a test: the share sheet on a real phone (`navigator.share` of a video file), a real phone camera
upload over a mobile connection, the workspace's shared address for the QR code (`/api/inventory` is faked), and the
real chat app (its create and message routes are what `fake_chat.py` imitates).
