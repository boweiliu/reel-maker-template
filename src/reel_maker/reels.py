"""Reels on disk, and the Studio chat (the reel agent) that does the work for each one.

A reel is a folder under ``<data dir>/reels/<reel id>/``. The app writes the creator's inputs there and sends the
reel agent one chat message per request; the agent writes its outputs and a ``status.json`` there
(``docs/agent-contract.md``). Nothing here interprets the agent's outputs beyond reading them as JSON.
"""

import json
import os
import re
import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests
from loguru import logger

# The chat app on this workspace, which creates chats and delivers messages to them.
CHAT_URL = os.environ.get("REEL_MAKER_CHAT_URL", "http://127.0.0.1:8010").rstrip("/")
CREATE_TIMEOUT_SECONDS = 180
SEND_ATTEMPTS = 30
SEND_RETRY_SECONDS = 10
# The stages the agent runs, in order, and the file each one leaves behind.
STAGE_OUTPUTS = {
    "research": "interview.json",
    "story": "tones.json",
    "script": "script.json",
    "footage": "footage.json",
    "edit": "reel.json",
}
# Stages a change request can be sent with (a new script, a new cut).
CHANGEABLE_STAGES = {"script", "edit"}
# What the agent's outputs and the creator's inputs are called in a reel's folder.
JSON_FILES = (
    "request.json", "interview.json", "answers.json", "tones.json", "choice.json", "script.json",
    "footage.json", "reel.json", "change.json", "status.json", "state.json", "health.json",
)
# The files only the app writes; a stage's inputs can never overwrite them.
APP_ONLY_FILES = ("status", "state", "health")
REEL_ID_PATTERN = re.compile(r"^[a-z0-9]{12}$")
TAKE_PATTERN = re.compile(r"^take-(\d+)\.(mp4|mov|webm|m4v|3gp)$")
VIDEO_SUFFIXES = {"video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm", "video/x-m4v": "m4v", "video/3gpp": "3gp"}

REPO = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO / "docs" / "agent-contract.md"
# Lauren's skill, shipped with the app unchanged: the reel agent reads it from here, not from the workspace's skills.
SKILL_PATH = REPO / "skills" / "make-app-reel" / "SKILL.md"


class ReelError(Exception):
    """A request about a reel that cannot be done; the message is shown to the creator."""


def reels_dir(data_dir: Path) -> Path:
    return data_dir / "reels"


def reel_dir(data_dir: Path, reel_id: str) -> Path:
    if not REEL_ID_PATTERN.match(reel_id):
        raise ReelError("There is no reel with that id.")
    folder = reels_dir(data_dir) / reel_id
    if not folder.is_dir():
        raise ReelError("There is no reel with that id.")
    return folder


def read_json(folder: Path, name: str) -> Any:
    path = folder / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        # The agent writes atomically, so a bad file is a mistake of its own; the app shows it as missing.
        logger.warning("Could not read {} as JSON", path)
        return None


def write_json(folder: Path, name: str, value: Any) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f"{name}.tmp"
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(folder / name)


def reel_snapshot(data_dir: Path, reel_id: str) -> dict[str, Any]:
    """Everything the pages need about one reel: the app's record, every JSON file, the takes and the reel video."""
    folder = reel_dir(data_dir, reel_id)
    snapshot: dict[str, Any] = {name.removesuffix(".json"): read_json(folder, name) for name in JSON_FILES}
    snapshot["id"] = reel_id
    snapshot["takes"] = list_takes(folder)
    snapshot["has_reel_video"] = (folder / "reel.mp4").is_file()
    return snapshot


def list_reels(data_dir: Path) -> list[dict[str, Any]]:
    folder = reels_dir(data_dir)
    if not folder.is_dir():
        return []
    found = []
    for entry in folder.iterdir():
        state = read_json(entry, "state.json") if entry.is_dir() else None
        if state:
            found.append({"id": entry.name, **state})
    return sorted(found, key=lambda reel: reel.get("created_at", 0), reverse=True)


def list_takes(folder: Path) -> list[dict[str, Any]]:
    takes_folder = folder / "takes"
    if not takes_folder.is_dir():
        return []
    takes = []
    for path in takes_folder.iterdir():
        match = TAKE_PATTERN.match(path.name)
        if match:
            takes.append({"name": path.name, "number": int(match.group(1)), "bytes": path.stat().st_size})
    return sorted(takes, key=lambda take: take["number"])


def save_take(data_dir: Path, reel_id: str, content_type: str, stream: Any) -> dict[str, Any]:
    """Store a take uploaded from the phone as the next ``take-<n>`` and make it the chosen one."""
    folder = reel_dir(data_dir, reel_id)
    suffix = VIDEO_SUFFIXES.get((content_type or "").split(";")[0].strip().lower(), "mp4")
    takes_folder = folder / "takes"
    takes_folder.mkdir(parents=True, exist_ok=True)
    number = max((take["number"] for take in list_takes(folder)), default=0) + 1
    target = takes_folder / f"take-{number}.{suffix}"
    temporary = takes_folder / f".upload-{number}.part"
    with temporary.open("wb") as handle:
        while chunk := stream.read(1024 * 1024):
            handle.write(chunk)
    if temporary.stat().st_size == 0:
        temporary.unlink()
        raise ReelError("The video arrived empty. Try recording it again.")
    temporary.replace(target)
    choice = read_json(folder, "choice.json") or {}
    write_json(folder, "choice.json", {**choice, "take": target.name})
    return {"name": target.name, "number": number, "bytes": target.stat().st_size}


def choose_take(data_dir: Path, reel_id: str, take_name: str) -> None:
    folder = reel_dir(data_dir, reel_id)
    if take_name not in {take["name"] for take in list_takes(folder)}:
        raise ReelError("That take is not in this reel.")
    choice = read_json(folder, "choice.json") or {}
    write_json(folder, "choice.json", {**choice, "take": take_name})


def kickoff_message(folder: Path, app_name: str) -> str:
    return f"Make a reel about \"{app_name}\" with {SKILL_PATH}. Hand it over as {CONTRACT_PATH} says.\n\n" + stage_message(
        folder, "research"
    )


def stage_message(folder: Path, stage: str) -> str:
    return f"REEL STAGE: {stage}\nReel folder: {folder.resolve()}"


def mark_working(folder: Path, stage: str) -> None:
    write_json(folder, "status.json", {"stage": stage, "state": "working", "items": [], "requested_at": time.time()})


def create_reel(data_dir: Path, app: dict[str, str], start_agent: Callable[[Path, str], str]) -> str:
    """Make the reel's folder and start its agent on the research stage; returns the reel id."""
    reel_id = secrets.token_hex(6)
    folder = reels_dir(data_dir) / reel_id
    folder.mkdir(parents=True)
    write_json(folder, "request.json", {"app": app})
    write_json(folder, "state.json", {"app": app.get("name", ""), "created_at": time.time(), "chat_id": ""})
    mark_working(folder, "research")
    chat_id = start_agent(folder, app.get("display_name") or app.get("name", ""))
    state = read_json(folder, "state.json") or {}
    write_json(folder, "state.json", {**state, "chat_id": chat_id})
    return reel_id


def advance(data_dir: Path, reel_id: str, stage: str, inputs: dict[str, Any], send: Callable[[str, str], None]) -> None:
    """Write the creator's inputs for a stage and ask the reel agent to do it."""
    if stage not in STAGE_OUTPUTS or stage == "research" or (stage not in CHANGEABLE_STAGES and "change" in inputs):
        raise ReelError("Studio can't do that step.")
    folder = reel_dir(data_dir, reel_id)
    state = read_json(folder, "state.json") or {}
    if not state.get("chat_id"):
        raise ReelError("This reel's Studio chat isn't running.")
    status = read_json(folder, "status.json") or {}
    if status.get("state") == "working":
        raise ReelError("Studio is still working on the last step. Wait for it to finish.")
    for name, value in inputs.items():
        if f"{name}.json" not in JSON_FILES or name in APP_ONLY_FILES:
            raise ReelError(f"Unknown input {name}.")
        if name == "choice":
            value = {**(read_json(folder, "choice.json") or {}), **value}
        write_json(folder, f"{name}.json", value)
    # A change request belongs to the one request it came with.
    if "change" not in inputs:
        (folder / "change.json").unlink(missing_ok=True)
    if stage == "edit":
        # Which cut this is, for the "Version" label and so browsers fetch the new video.
        write_json(folder, "state.json", {**state, "cuts": int(state.get("cuts", 0)) + 1})
    mark_working(folder, stage)
    send(state["chat_id"], stage_message(folder, stage))


def start_agent_through_chat_app(folder: Path, app_name: str) -> str:
    """Create the reel's Studio chat with its first instructions; returns the chat id."""
    try:
        answer = requests.post(
            f"{CHAT_URL}/api/chats/create",
            json={"name": f"Reel: {app_name}"[:60], "message": kickoff_message(folder, app_name)},
            timeout=CREATE_TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        raise ReelError("Couldn't reach Studio's chats to start the reel.") from error
    if answer.status_code >= 300:
        logger.error("Chat create refused ({}): {}", answer.status_code, answer.text[:500])
        raise ReelError("Studio couldn't start a chat for this reel.")
    return str(answer.json()["chat_id"])


def send_through_chat_app(chat_id: str, text: str) -> None:
    """Deliver a message to the reel's chat in the background, retrying while the chat is busy or starting."""

    def deliver() -> None:
        for _ in range(SEND_ATTEMPTS):
            try:
                answer = requests.post(
                    f"{CHAT_URL}/api/chats/{chat_id}/message",
                    json={"message": text, "message_id": secrets.token_hex(8)},
                    timeout=CREATE_TIMEOUT_SECONDS,
                )
            except requests.RequestException as error:
                logger.warning("Message to reel chat {} failed: {}", chat_id, error)
            else:
                if answer.status_code < 300:
                    return
                logger.warning("Reel chat {} refused a message ({}): {}", chat_id, answer.status_code, answer.text[:300])
            threading.Event().wait(SEND_RETRY_SECONDS)
        logger.error("Gave up messaging reel chat {}", chat_id)

    threading.Thread(target=deliver, name=f"reel-message-{chat_id}", daemon=True).start()
