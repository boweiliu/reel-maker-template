"""Fixtures for the app's tests: a data folder, a fake chat app, the app served on a free port, and the browser."""

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from flask.testing import FlaskClient
from playwright.sync_api import Browser, sync_playwright
from werkzeug.serving import make_server

from reel_maker import reels, runner
from reel_maker.fake_chat import FakeChat, StandInAgent

# The workspace's browser engine (a stealth-patched Chromium fork); Playwright's own cache lookup does not find it.
FORTRESS_CHROMIUM_PATH = "/opt/fortress/tilion-fortress/tilion"

APPS_TOML = """
[[apps]]
name = "deck-list"
display_name = "Deck List"
description = "Magic deck builder"
icon = "<svg xmlns='http://www.w3.org/2000/svg'/>"
priority = "user"

[[apps]]
name = "reel-maker"
display_name = "Reel maker"
priority = "user"

[[apps]]
name = "chat"
display_name = "Chat"
priority = "system"

[[apps]]
name = "hidden-thing"
display_name = "Hidden"
priority = "user"
internal = true
"""


@pytest.fixture
def fake_chat() -> Iterator[FakeChat]:
    chat = FakeChat().start()
    yield chat
    chat.stop()


@pytest.fixture
def agent(fake_chat: FakeChat) -> StandInAgent:
    stand_in = StandInAgent()
    fake_chat.on_message = stand_in.respond
    return stand_in


@pytest.fixture
def isolated_app(tmp_path: Path, fake_chat: FakeChat, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points the app at a scratch data folder, a registry of apps and the fake chat app; returns the data folder."""
    data_dir = tmp_path / "data"
    registry = tmp_path / "apps.toml"
    registry.write_text(APPS_TOML)
    monkeypatch.setattr(runner, "DATA_DIR", data_dir)
    monkeypatch.setattr(runner, "APPS_REGISTRY", registry)
    monkeypatch.setattr(runner, "SHELL_URL", fake_chat.url)
    monkeypatch.setattr(reels, "CHAT_URL", fake_chat.url)
    monkeypatch.setattr(reels, "SEND_RETRY_SECONDS", 0.05)
    monkeypatch.setitem(runner._public_address_cache, "asked_at", 0.0)
    return data_dir


@pytest.fixture
def client(isolated_app: Path) -> FlaskClient:
    return runner.app.test_client()


@pytest.fixture
def server(isolated_app: Path) -> Iterator[str]:
    """The app served over HTTP on a free port, for the browser and for streamed uploads."""
    http_server = make_server("127.0.0.1", 0, runner.app, threaded=True)
    thread = threading.Thread(target=http_server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{http_server.server_port}"
    http_server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    # One browser per test module, closed afterwards: the workspace is short of memory.
    with sync_playwright() as playwright:
        launched = playwright.chromium.launch(executable_path=FORTRESS_CHROMIUM_PATH)
        yield launched
        launched.close()


