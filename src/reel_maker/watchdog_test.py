"""The watchdog's decisions, with the chat, memory and the memory guard's record faked."""

from pathlib import Path
from typing import Any

from reel_maker import reels, watchdog

REEL = "abcdef123456"
CHAT = "agent-chat"
START = 1_000_000.0
GIB = 1024 * 1024 * 1024


class Fakes:
    def __init__(self, agent: dict[str, Any] | None, memory: int | None = 4 * GIB, sheds: int = 0, activity: float = START) -> None:
        self.agent = agent
        self.free = memory
        self.shed_count = sheds
        self.last = activity
        self.sent: list[tuple[str, str]] = []
        self.stopped: list[str] = []

    def probes(self) -> watchdog.Probes:
        return watchdog.Probes(
            snapshot=lambda chat_id: self.agent,
            send=lambda chat_id, text: self.sent.append((chat_id, text)),
            stop=self.stopped.append,
            memory=lambda: self.free,
            sheds=lambda since: self.shed_count,
            activity=lambda folder, agent_id: self.last,
        )


def make_reel(data_dir: Path, state: str = "working", error: str = "") -> Path:
    folder = reels.reels_dir(data_dir) / REEL
    folder.mkdir(parents=True)
    reels.write_json(folder, "state.json", {"app": "deck-list", "chat_id": CHAT, "created_at": START})
    status: dict[str, Any] = {"stage": "footage", "state": state, "requested_at": START}
    if error:
        status["error"] = error
    reels.write_json(folder, "status.json", status)
    return folder


def health(folder: Path) -> dict[str, Any]:
    return reels.read_json(folder, "health.json")


IDLE = {"agent_id": CHAT, "is_busy": False, "activity_state": "IDLE"}
BUSY = {"agent_id": CHAT, "is_busy": True, "activity_state": "TOOL_RUNNING"}


def test_a_chat_that_stopped_mid_stage_is_asked_to_carry_on_after_the_grace(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    fakes = Fakes(IDLE, sheds=2)
    watchdog.check_reel(tmp_path, REEL, START + 10, fakes.probes())
    assert health(folder)["condition"] == "working" and fakes.sent == []
    watchdog.check_reel(tmp_path, REEL, START + 10 + watchdog.IDLE_GRACE_SECONDS, fakes.probes())
    assert fakes.sent == [(CHAT, reels.stage_message(folder, "footage"))]
    assert health(folder)["condition"] == "repairing"
    assert "low on memory" in health(folder)["message"]
    assert reels.read_json(folder, "status.json")["state"] == "working"


def test_a_repair_waits_for_memory_but_not_forever(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    fakes = Fakes(IDLE, memory=100 * 1024 * 1024)
    watchdog.check_reel(tmp_path, REEL, START, fakes.probes())
    later = START + watchdog.IDLE_GRACE_SECONDS
    watchdog.check_reel(tmp_path, REEL, later, fakes.probes())
    assert health(folder)["condition"] == "waiting_memory" and fakes.sent == []
    watchdog.check_reel(tmp_path, REEL, later + watchdog.MEMORY_WAIT_LIMIT_SECONDS, fakes.probes())
    assert health(folder)["condition"] == "repairing" and len(fakes.sent) == 1


def test_a_quiet_busy_chat_is_flagged_then_restarted(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    fakes = Fakes(BUSY, activity=START)
    watchdog.check_reel(tmp_path, REEL, START + watchdog.QUIET_WARN_SECONDS, fakes.probes())
    assert health(folder)["condition"] == "quiet" and fakes.sent == []
    watchdog.check_reel(tmp_path, REEL, START + watchdog.QUIET_RESTART_SECONDS, fakes.probes())
    assert fakes.stopped == [CHAT] and len(fakes.sent) == 1
    assert "restarted it" in health(folder)["message"]


def test_a_reported_failure_is_retried(tmp_path: Path) -> None:
    folder = make_reel(tmp_path, state="failed", error="ran out of memory")
    fakes = Fakes(IDLE)
    watchdog.check_reel(tmp_path, REEL, START, fakes.probes())
    watchdog.check_reel(tmp_path, REEL, START + watchdog.IDLE_GRACE_SECONDS, fakes.probes())
    assert len(fakes.sent) == 1 and "ran out of memory" in health(folder)["message"]


def test_after_the_last_repair_it_gives_up_and_try_again_starts_over(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    fakes = Fakes(IDLE)
    now = START
    for _ in range(watchdog.MAX_REPAIRS + 1):
        watchdog.check_reel(tmp_path, REEL, now, fakes.probes())
        now += watchdog.IDLE_GRACE_SECONDS
        watchdog.check_reel(tmp_path, REEL, now, fakes.probes())
        now += watchdog.IDLE_GRACE_SECONDS
    assert len(fakes.sent) == watchdog.MAX_REPAIRS
    assert health(folder)["condition"] == "gave_up"
    watchdog.retry(tmp_path, REEL, lambda chat_id, text: fakes.sent.append((chat_id, text)))
    assert health(folder)["condition"] == "working" and health(folder)["repairs"] == 0
    assert len(fakes.sent) == watchdog.MAX_REPAIRS + 1


def test_a_finished_stage_and_a_busy_active_chat_are_left_alone(tmp_path: Path) -> None:
    folder = make_reel(tmp_path, state="done")
    fakes = Fakes(IDLE)
    watchdog.check_reel(tmp_path, REEL, START + 3600, fakes.probes())
    assert health(folder) is None and fakes.sent == []
    reels.write_json(folder, "status.json", {"stage": "footage", "state": "working", "requested_at": START})
    fakes.agent = BUSY
    fakes.last = START + 3500
    watchdog.check_reel(tmp_path, REEL, START + 3600, fakes.probes())
    assert health(folder)["condition"] == "working" and fakes.sent == []


def test_a_deleted_chat_is_reported(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    watchdog.check_reel(tmp_path, REEL, START, Fakes(None).probes())
    assert health(folder)["condition"] == "gave_up" and "gone" in health(folder)["message"]
