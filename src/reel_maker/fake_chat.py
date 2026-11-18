"""Test doubles: a stand-in for Studio's chat app, and a stand-in for the reel agent that answers its messages.

``FakeChat`` serves the few routes the app uses (create a chat, message it, list chats, stop one, the shell's
inventory) on a local port and records everything it receives. ``StandInAgent`` does what the reel agent's
agreement says (``docs/agent-contract.md``): reads a stage's inputs from the reel folder, writes that stage's
outputs, then ``status.json``. Its outputs quote the inputs it read, so a test can see that an input travelled the
whole way round.
"""

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from werkzeug.serving import make_server

from reel_maker import reels

QUESTIONS = [
    {"q": "What is it for?", "help": "One sentence.", "guess": "Tracking decks."},
    {"q": "What is different now?", "help": "After-picture.", "guess": "Everything is tagged.",
     "quote": "make me a deck list"},
]


def parse_message(text: str) -> tuple[str, Path]:
    """The stage and reel folder a message from the app names."""
    stage = folder = ""
    for line in text.splitlines():
        if line.startswith("REEL STAGE: "):
            stage = line.removeprefix("REEL STAGE: ").strip()
        if line.startswith("Reel folder: "):
            folder = line.removeprefix("Reel folder: ").strip()
    return stage, Path(folder)


class StandInAgent:
    """Answers each stage message the way the real reel agent's files would look."""

    def __init__(self, delay: float = 0.1) -> None:
        self.delay = delay
        # Stages it never answers (to look like a stalled chat), and stages it reports as failed.
        self.silent: set[str] = set()
        self.failing: dict[str, str] = {}
        self.handled: list[str] = []

    def respond(self, text: str) -> None:
        stage, folder = parse_message(text)
        self.handled.append(stage)
        if stage in self.silent:
            return
        if self.delay:
            threading.Event().wait(self.delay)
        if stage in self.failing:
            reels.write_json(folder, "status.json", {"stage": stage, "state": "failed", "error": self.failing[stage],
                                                     "requested_at": (reels.read_json(folder, "status.json") or {}).get("requested_at")})
            return
        getattr(self, f"do_{stage}")(folder)
        status = reels.read_json(folder, "status.json") or {}
        reels.write_json(folder, "status.json", {**status, "stage": stage, "state": "done"})

    def do_research(self, folder: Path) -> None:
        app = (reels.read_json(folder, "request.json") or {})["app"]
        reels.write_json(folder, "interview.json", {"app": app["display_name"], "questions": QUESTIONS})

    def do_story(self, folder: Path) -> None:
        answers = (reels.read_json(folder, "answers.json") or {}).get("answers", [])
        reels.write_json(folder, "tones.json", {
            "story": f"You said: {' / '.join(answers)}",
            "tones": [
                {"key": "calm", "name": "Calm", "hook": "A calm hook.", "recommended": True},
                {"key": "dry", "name": "Dry", "hook": "A dry hook."},
            ],
            "directions": [
                {"key": "before-after", "name": "Before and after", "summary": "A chore, then ease.", "recommended": True},
                {"key": "tour", "name": "Tour", "summary": "Plain."},
            ],
        })

    def do_script(self, folder: Path) -> None:
        choice = reels.read_json(folder, "choice.json") or {}
        change = reels.read_json(folder, "change.json") or {}
        lines = [
            {"say": f"A {choice.get('tone')} opening line.", "screen": "Your face", "shot": "face"},
            {"say": "Then the app does its thing.", "screen": "The app", "shot": "app"},
            {"say": "Made with Studio.", "screen": "End card", "shot": "end"},
        ]
        if change.get("text"):
            lines.insert(1, {"say": f"Changed: {change['text']}", "screen": "The chat", "shot": "chat"})
        reels.write_json(folder, "script.json", {"tone": choice.get("tone"), "direction": choice.get("direction"),
                                                 "seconds": 30, "lines": lines})

    def do_footage(self, folder: Path) -> None:
        (folder / "footage").mkdir(exist_ok=True)
        (folder / "footage" / "clip-1.mp4").write_bytes(b"not really a video")
        reels.write_json(folder, "footage.json", {"clips": [{"file": "footage/clip-1.mp4", "caption": "1. The app"}],
                                                  "privacy": ["Everything shown is made up."]})

    def do_edit(self, folder: Path) -> None:
        choice = reels.read_json(folder, "choice.json") or {}
        change = reels.read_json(folder, "change.json") or {}
        temporary = folder / "reel.mp4.tmp"
        temporary.write_bytes(b"not really a reel")
        temporary.replace(folder / "reel.mp4")
        reels.write_json(folder, "reel.json", {
            "caption": f"Cut from {choice.get('take')}" + (f" with: {change['text']}" if change.get("text") else ""),
            "checks": ["Every word kept"], "notes": ["Watch it with sound on."],
        })


class FakeChat:
    """A local stand-in for the chat app (and the shell's inventory), serving on a free port until stopped."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.messages: list[tuple[str, str]] = []
        self.stopped: list[str] = []
        self.refuse_create = False
        # How many messages to the chat it answers with a failure before accepting them.
        self.refuse_messages = 0
        self.agent_state: dict[str, Any] | None = {"agent_id": "agent-1", "is_busy": False, "activity_state": "IDLE"}
        self.on_message: Callable[[str], None] | None = None
        self.inventory: list[dict[str, Any]] = []
        self.app = Flask("fake_chat")
        self._routes()
        self._server = make_server("127.0.0.1", 0, self.app, threaded=True)
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)

    def _routes(self) -> None:
        @self.app.post("/api/chats/create")
        def create() -> Any:
            if self.refuse_create:
                return jsonify({"detail": "no"}), 500
            body = request.get_json()
            self.created.append(body)
            chat_id = f"chat-{len(self.created)}"
            self.messages.append((chat_id, body["message"]))
            self._deliver(body["message"])
            return jsonify({"chat_id": chat_id}), 201

        @self.app.post("/api/chats/<chat_id>/message")
        def message(chat_id: str) -> Any:
            text = request.get_json()["message"]
            if self.refuse_messages > 0:
                self.refuse_messages -= 1
                return jsonify({"detail": "busy"}), 503
            self.messages.append((chat_id, text))
            self._deliver(text)
            return jsonify({"ok": True})

        @self.app.post("/api/chats/<chat_id>/stop")
        def stop(chat_id: str) -> Any:
            self.stopped.append(chat_id)
            return jsonify({"ok": True})

        @self.app.get("/api/chats")
        def chats() -> Any:
            if self.agent_state is None:
                return jsonify({"chats": []})
            return jsonify({"chats": [{"chat_id": f"chat-{i + 1}", "active_agent": self.agent_state} for i in range(len(self.created))]})

        @self.app.get("/api/inventory")
        def inventory() -> Any:
            return jsonify({"apps": self.inventory})

    def _deliver(self, text: str) -> None:
        # Like the real chat, answer after the request has returned.
        if self.on_message is not None:
            handler = self.on_message
            threading.Thread(target=handler, args=(text,), daemon=True).start()

    def start(self) -> "FakeChat":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)


def wait_until(condition: Callable[[], Any], timeout: float = 10.0) -> Any:
    """The condition's first truthy answer, polling until the timeout (then the last answer, which is falsy)."""
    deadline = time.monotonic() + timeout
    answer = condition()
    while not answer and time.monotonic() < deadline:
        threading.Event().wait(0.05)
        answer = condition()
    return answer


def write_reel(folder: Path, **files: Any) -> None:
    """Put the named JSON files in a reel folder (for tests that need a reel in a given state)."""
    for name, value in files.items():
        reels.write_json(folder, f"{name}.json", value)


def dump(value: Any) -> str:
    return json.dumps(value, indent=2)
