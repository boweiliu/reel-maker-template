"""Notice a reel's Studio chat that stopped, failed or went quiet in the middle of a stage, say so, and repair it.

Everything here is read from outside the chat: the chat app's view of the chat (running, mid-turn, idle), when the
chat or the reel folder last changed, the workspace's memory and its memory guard's record of what it stopped. A
repair is the same stage message sent again (a stopped chat is started by the send), after a restart when the chat
hung; the agent gets no extra instructions. What happened goes to ``health.json``, which the waiting screen shows.
"""

import itertools
import json
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from reel_maker import reels

CHECK_EVERY_SECONDS = 30
# A chat whose turn ended (or that reported a failure) with the stage not done, for this long, is stalled.
IDLE_GRACE_SECONDS = 120
# A chat mid-turn that has written nothing for this long is flagged, and restarted after the second limit.
QUIET_WARN_SECONDS = 15 * 60
QUIET_RESTART_SECONDS = 30 * 60
MAX_REPAIRS = 3
# Below this much free memory a repair waits (it would be stopped again), but not for longer than the limit.
MIN_MEMORY_BYTES = 700 * 1024 * 1024
MEMORY_WAIT_LIMIT_SECONDS = 10 * 60
# The machine the workspace shares with others reports its memory here; the container's own view is the fallback.
MEMINFO_FILES = (Path("/mngr-vol/.host-meminfo"), Path("/proc/meminfo"))
SHED_LEDGER = Path("data/.state/oom_priority/events/shed.jsonl")
AGENTS_DIR = Path("/home/user/.mngr/agents")
BUSY_ACTIVITY = {"THINKING", "TOOL_RUNNING", "COMPACTING"}
HISTORY_LIMIT = 20


def chat_snapshot(chat_id: str) -> dict[str, Any] | None:
    """The chat app's view of the chat's active agent, or None when the chat is gone. Raises when unreachable."""
    answer = requests.get(f"{reels.CHAT_URL}/api/chats", timeout=10)
    answer.raise_for_status()
    for chat in answer.json().get("chats", []):
        if chat.get("chat_id") == chat_id:
            return chat.get("active_agent") or {}
    return None


def stop_chat(chat_id: str) -> None:
    try:
        requests.post(f"{reels.CHAT_URL}/api/chats/{chat_id}/stop", timeout=60)
    except requests.RequestException as error:
        logger.warning("Could not stop reel chat {}: {}", chat_id, error)


def memory_available() -> int | None:
    for path in MEMINFO_FILES:
        try:
            for line in path.read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            continue
    return None


def sheds_since(started_at: float) -> int:
    """How many programs the memory guard stopped since the stage started."""
    try:
        lines = SHED_LEDGER.read_text().splitlines()[-500:]
    except OSError:
        return 0
    count = 0
    for line in lines:
        try:
            stamp = datetime.fromisoformat(json.loads(line)["timestamp"].replace("Z", "+00:00")).timestamp()
        except (ValueError, KeyError, TypeError):
            continue
        if stamp >= started_at:
            count += 1
    return count


def last_activity(folder: Path, agent_id: str) -> float:
    """When the chat last did something: its transcript, or anything it wrote in the reel folder."""
    paths = [*folder.glob("*"), *folder.glob("footage/*"), *AGENTS_DIR.glob(f"{agent_id}/events/*/common_transcript/events.jsonl")]
    stamps = []
    for path in paths:
        try:
            stamps.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(stamps, default=0.0)


def minutes(seconds: float) -> str:
    whole = max(1, round(seconds / 60))
    return f"{whole} minute{'s' if whole != 1 else ''}"


class Probes:
    """What the watchdog reads and does outside the reel folder, replaceable in tests."""

    def __init__(
        self,
        snapshot: Callable[[str], dict[str, Any] | None] = chat_snapshot,
        send: Callable[[str, str], None] = reels.send_through_chat_app,
        stop: Callable[[str], None] = stop_chat,
        memory: Callable[[], int | None] = memory_available,
        sheds: Callable[[float], int] = sheds_since,
        activity: Callable[[Path, str], float] = last_activity,
    ) -> None:
        self.snapshot = snapshot
        self.send = send
        self.stop = stop
        self.memory = memory
        self.sheds = sheds
        self.activity = activity


def note(health: dict[str, Any], now: float, text: str) -> None:
    health["history"] = [*health.get("history", []), {"at": now, "text": text}][-HISTORY_LIMIT:]


def check_reel(data_dir: Path, reel_id: str, now: float, probes: Probes) -> None:
    """Look at one reel whose stage is not done, and record (and act on) what its chat is doing."""
    folder = reels.reel_dir(data_dir, reel_id)
    status = reels.read_json(folder, "status.json") or {}
    state = reels.read_json(folder, "state.json") or {}
    stage = status.get("stage", "")
    if status.get("state") not in ("working", "failed") or stage not in reels.STAGE_OUTPUTS or not state.get("chat_id"):
        return
    requested_at = float(status.get("requested_at") or now)
    health: dict[str, Any] = reels.read_json(folder, "health.json") or {}
    if health.get("stage") != stage or health.get("requested_at") != requested_at:
        health = {"stage": stage, "requested_at": requested_at, "repairs": 0, "history": []}
    if health.get("condition") == "gave_up":
        return
    try:
        agent = probes.snapshot(state["chat_id"])
    except (requests.RequestException, ValueError) as error:
        logger.warning("Could not check reel chat {}: {}", state["chat_id"], error)
        return
    if agent is None:
        health.update(condition="gave_up", message="Studio's chat for this reel is gone. Start a new reel.")
        reels.write_json(folder, "health.json", health)
        return

    busy = bool(
        agent.get("is_busy") or agent.get("is_connecting") or agent.get("queued_messages")
        or agent.get("activity_state") in BUSY_ACTIVITY
    )
    activity = probes.activity(folder, str(agent.get("agent_id") or state["chat_id"]))
    shed_count = probes.sheds(requested_at)
    cause = " The workspace ran low on memory while it worked." if shed_count else ""
    since_repair = now - float(health.get("last_repair_at") or requested_at)
    health.update(checked_at=now, last_activity_at=activity, sheds=shed_count)

    failed = status.get("state") == "failed"
    if busy and not failed:
        health["idle_since"] = None
        quiet = now - max(activity, requested_at)
        if quiet >= QUIET_RESTART_SECONDS and since_repair >= QUIET_RESTART_SECONDS:
            repair(folder, health, status, state, now, probes, f"went quiet for {minutes(quiet)}.{cause}", restart=True)
        elif quiet >= QUIET_WARN_SECONDS:
            health.update(
                condition="quiet",
                message=f"Studio hasn't done anything for {minutes(quiet)}. If it stays quiet, the app restarts its chat.",
            )
        else:
            health.update(condition="working", message="")
    else:
        idle_since = float(health.get("idle_since") or now)
        health["idle_since"] = idle_since
        if now - idle_since < IDLE_GRACE_SECONDS or since_repair < IDLE_GRACE_SECONDS:
            health.update(condition="working", message="")
        elif failed:
            repair(folder, health, status, state, now, probes, f"couldn't finish: {status.get('error') or 'it gave no reason'}.", restart=False)
        else:
            repair(folder, health, status, state, now, probes, f"stopped before finishing this step.{cause}", restart=False)
    reels.write_json(folder, "health.json", health)


def repair(
    folder: Path, health: dict[str, Any], status: dict[str, Any], state: dict[str, Any], now: float, probes: Probes,
    reason: str, restart: bool,
) -> None:
    # The agent may have finished since this check read the status; never reopen a finished stage.
    if (reels.read_json(folder, "status.json") or {}).get("state") == "done":
        health.update(condition="working", message="")
        return
    if health.get("repairs", 0) >= MAX_REPAIRS:
        health.update(
            condition="gave_up",
            message=f"Studio's chat {reason} It has been asked to carry on {MAX_REPAIRS} times. Try again, or open its chat to see what happened.",
        )
        note(health, now, f"Stopped trying after {MAX_REPAIRS} attempts.")
        return
    free = probes.memory()
    waiting_since = float(health.get("memory_wait_since") or now)
    if free is not None and free < MIN_MEMORY_BYTES and now - waiting_since < MEMORY_WAIT_LIMIT_SECONDS:
        if not health.get("memory_wait_since"):
            note(health, now, f"Studio's chat {reason} Waiting for memory to free up.")
        health.update(
            condition="waiting_memory", memory_wait_since=waiting_since,
            message=f"Studio's chat {reason} The workspace is low on memory, so the app is waiting for some to free up before asking it to carry on.",
        )
        return
    if restart:
        probes.stop(state["chat_id"])
    # The same request again, marked as still in progress; a stopped chat is started by the send.
    reels.write_json(folder, "status.json", {"stage": status["stage"], "state": "working", "requested_at": health["requested_at"]})
    probes.send(state["chat_id"], reels.stage_message(folder, status["stage"]))
    health["repairs"] = health.get("repairs", 0) + 1
    health.update(
        condition="repairing", last_repair_at=now, idle_since=None, memory_wait_since=None,
        message=f"Studio's chat {reason} The app {'restarted it and ' if restart else ''}asked it to carry on ({health['repairs']} of {MAX_REPAIRS}).",
    )
    note(health, now, health["message"])


def retry(data_dir: Path, reel_id: str, send: Callable[[str, str], None]) -> None:
    """The creator's "Try again": the current stage asked for afresh, with the repair count reset."""
    with reels.REEL_LOCK:
        folder = reels.reel_dir(data_dir, reel_id)
        status = reels.read_json(folder, "status.json") or {}
        state = reels.read_json(folder, "state.json") or {}
        if status.get("stage") not in reels.STAGE_OUTPUTS or status.get("state") == "done" or not state.get("chat_id"):
            raise reels.ReelError("There is nothing to try again.")
        reels.mark_working(folder, status["stage"])
        restarted = reels.read_json(folder, "status.json") or {}
        health = reels.read_json(folder, "health.json") or {}
        fresh: dict[str, Any] = {"stage": status["stage"], "requested_at": restarted.get("requested_at"), "repairs": 0, "condition": "working",
                 "message": "", "history": health.get("history", [])}
        note(fresh, time.time(), "You asked Studio to try again.")
        reels.write_json(folder, "health.json", fresh)
        send(state["chat_id"], reels.stage_message(folder, status["stage"]))


def check_all(data_dir: Path, probes: Probes) -> None:
    for reel in reels.list_reels(data_dir):
        try:
            check_reel(data_dir, reel["id"], time.time(), probes)
        except (reels.ReelError, OSError, KeyError, ValueError, TypeError) as error:
            logger.warning("Could not check reel {}: {}", reel["id"], error)


def start(data_dir: Path, probes: Probes | None = None) -> threading.Thread:
    """Check every reel in the background, for as long as the app runs."""
    chosen = probes or Probes()
    wake = threading.Event()

    def loop() -> None:
        for _ in itertools.count():
            check_all(data_dir, chosen)
            wake.wait(CHECK_EVERY_SECONDS)

    thread = threading.Thread(target=loop, name="reel-watchdog", daemon=True)
    thread.start()
    return thread
