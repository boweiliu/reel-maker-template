# Tests

From the repo folder, after `deploy/install.py` (or `uv sync --project .`) has built the venv:

```bash
uv run --no-sync --project . pytest -q src test_reel_maker_ratchets.py
```

- `src/reel_maker/runner_test.py`: the app's API document matches its manifest and covers every route.
- `test_reel_maker_ratchets.py`: code-safety ratchets and the type check over the app's own code (`skills/` is
  excluded: Lauren's reference scripts ship unchanged).

Nothing calls an outside service. The mock pages have no browser tests yet; they were checked by hand at computer and
phone sizes with Playwright screenshots.
