"""The watchdog's decisions, with the chat, memory and the memory guard's record faked."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import requests

from reel_maker import reels, watchdog
from reel_maker.fake_chat import FakeChat, wait_until

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


# ---- more cases ----


def test_a_chat_with_queued_messages_or_connecting_counts_as_busy(tmp_path: Path) -> None:
    busy_agents = ({"agent_id": CHAT, "queued_messages": 1}, {"agent_id": CHAT, "is_connecting": True}, {"agent_id": CHAT, "activity_state": "COMPACTING"})
    for number, agent in enumerate(busy_agents):
        data_dir = tmp_path / str(number)
        make_reel(data_dir)
        fakes = Fakes(agent, activity=START)
        watchdog.check_reel(data_dir, REEL, START + 3 * watchdog.IDLE_GRACE_SECONDS, fakes.probes())
        assert fakes.sent == [] and fakes.stopped == []


def test_a_quiet_chat_that_wakes_up_is_no_longer_flagged(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    fakes = Fakes(BUSY, activity=START)
    watchdog.check_reel(tmp_path, REEL, START + watchdog.QUIET_WARN_SECONDS, fakes.probes())
    assert health(folder)["condition"] == "quiet" and "15 minutes" in health(folder)["message"]
    fakes.last = START + watchdog.QUIET_WARN_SECONDS
    watchdog.check_reel(tmp_path, REEL, START + watchdog.QUIET_WARN_SECONDS + 60, fakes.probes())
    assert health(folder)["condition"] == "working" and health(folder)["message"] == ""


def test_a_restart_repair_is_not_repeated_until_another_quiet_period_has_passed(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    fakes = Fakes(BUSY, activity=START)
    watchdog.check_reel(tmp_path, REEL, START + watchdog.QUIET_RESTART_SECONDS, fakes.probes())
    assert fakes.stopped == [CHAT]
    watchdog.check_reel(tmp_path, REEL, START + watchdog.QUIET_RESTART_SECONDS + 60, fakes.probes())
    assert fakes.stopped == [CHAT] and len(fakes.sent) == 1
    assert health(folder)["condition"] == "quiet"
    watchdog.check_reel(tmp_path, REEL, START + 2 * watchdog.QUIET_RESTART_SECONDS, fakes.probes())
    assert fakes.stopped == [CHAT, CHAT] and health(folder)["repairs"] == 2


def test_idle_time_counts_from_when_the_chat_was_first_seen_idle(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    fakes = Fakes(BUSY, activity=START + 1000)
    watchdog.check_reel(tmp_path, REEL, START + 1000, fakes.probes())
    fakes.agent = IDLE
    watchdog.check_reel(tmp_path, REEL, START + 1100, fakes.probes())
    # Busy until 1000 s in, idle only for the last 100 s: still inside the grace.
    watchdog.check_reel(tmp_path, REEL, START + 1100 + watchdog.IDLE_GRACE_SECONDS - 1, fakes.probes())
    assert fakes.sent == [] and health(folder)["idle_since"] == START + 1100
    watchdog.check_reel(tmp_path, REEL, START + 1100 + watchdog.IDLE_GRACE_SECONDS, fakes.probes())
    assert len(fakes.sent) == 1


def test_a_busy_chat_resets_the_idle_clock(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    fakes = Fakes(IDLE)
    watchdog.check_reel(tmp_path, REEL, START + 10, fakes.probes())
    assert health(folder)["idle_since"] == START + 10
    fakes.agent, fakes.last = BUSY, START + 20
    watchdog.check_reel(tmp_path, REEL, START + 30, fakes.probes())
    assert health(folder)["idle_since"] is None


def test_an_unreachable_chat_app_changes_nothing(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)

    def unreachable(chat_id: str) -> dict[str, Any] | None:
        raise requests.ConnectionError("no chat app")

    fakes = Fakes(IDLE)
    probes = fakes.probes()
    probes.snapshot = unreachable
    watchdog.check_reel(tmp_path, REEL, START + 3600, probes)
    assert health(folder) is None and fakes.sent == [] and reels.read_json(folder, "status.json")["state"] == "working"


def test_a_repair_goes_ahead_when_memory_is_not_known(tmp_path: Path) -> None:
    make_reel(tmp_path)
    fakes = Fakes(IDLE, memory=None)
    watchdog.check_reel(tmp_path, REEL, START, fakes.probes())
    watchdog.check_reel(tmp_path, REEL, START + watchdog.IDLE_GRACE_SECONDS, fakes.probes())
    assert len(fakes.sent) == 1


def test_a_repair_that_waited_for_memory_goes_ahead_the_moment_memory_returns(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    fakes = Fakes(IDLE, memory=100 * 1024 * 1024)
    watchdog.check_reel(tmp_path, REEL, START, fakes.probes())
    later = START + watchdog.IDLE_GRACE_SECONDS
    watchdog.check_reel(tmp_path, REEL, later, fakes.probes())
    assert health(folder)["condition"] == "waiting_memory" and "low on memory" in health(folder)["message"]
    fakes.free = 4 * GIB
    watchdog.check_reel(tmp_path, REEL, later + 30, fakes.probes())
    assert health(folder)["condition"] == "repairing" and len(fakes.sent) == 1


def test_a_repair_keeps_the_original_request_time_and_marks_a_failed_stage_working_again(tmp_path: Path) -> None:
    folder = make_reel(tmp_path, state="failed", error="boom")
    fakes = Fakes(IDLE)
    watchdog.check_reel(tmp_path, REEL, START, fakes.probes())
    watchdog.check_reel(tmp_path, REEL, START + watchdog.IDLE_GRACE_SECONDS, fakes.probes())
    assert reels.read_json(folder, "status.json") == {"stage": "footage", "state": "working", "requested_at": START}


def test_a_new_request_starts_a_fresh_health_record(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    fakes = Fakes(IDLE)
    watchdog.check_reel(tmp_path, REEL, START, fakes.probes())
    watchdog.check_reel(tmp_path, REEL, START + watchdog.IDLE_GRACE_SECONDS, fakes.probes())
    assert health(folder)["repairs"] == 1
    reels.write_json(folder, "status.json", {"stage": "edit", "state": "working", "requested_at": START + 5000})
    watchdog.check_reel(tmp_path, REEL, START + 5001, fakes.probes())
    assert health(folder)["stage"] == "edit" and health(folder)["repairs"] == 0 and health(folder)["history"] == []


def test_a_reel_that_gave_up_is_left_alone_until_the_creator_asks_again(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    reels.write_json(folder, "health.json", {"stage": "footage", "requested_at": START, "repairs": 3, "condition": "gave_up", "message": "stuck"})
    fakes = Fakes(IDLE)
    watchdog.check_reel(tmp_path, REEL, START + 10 * 3600, fakes.probes())
    assert fakes.sent == [] and health(folder)["message"] == "stuck"


def test_reels_that_are_not_waiting_on_a_chat_are_ignored(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    fakes = Fakes(IDLE)
    for status in ({"stage": "nonsense", "state": "working"}, {"stage": "edit", "state": "done"}, {}):
        reels.write_json(folder, "status.json", status)
        watchdog.check_reel(tmp_path, REEL, START + 3600, fakes.probes())
    reels.write_json(folder, "status.json", {"stage": "edit", "state": "working", "requested_at": START})
    reels.write_json(folder, "state.json", {"app": "x", "chat_id": "", "created_at": START})
    watchdog.check_reel(tmp_path, REEL, START + 3600, fakes.probes())
    assert health(folder) is None and fakes.sent == []


def test_the_story_of_what_happened_keeps_only_the_latest_entries(tmp_path: Path) -> None:
    health_record: dict[str, Any] = {}
    for number in range(watchdog.HISTORY_LIMIT + 5):
        watchdog.note(health_record, float(number), f"entry {number}")
    assert len(health_record["history"]) == watchdog.HISTORY_LIMIT
    assert health_record["history"][0]["text"] == "entry 5" and health_record["history"][-1]["text"] == f"entry {watchdog.HISTORY_LIMIT + 4}"


def test_one_unreadable_reel_does_not_stop_the_others_being_checked(tmp_path: Path) -> None:
    broken = reels.reels_dir(tmp_path) / "bbbbbbbbbbbb"
    reels.write_json(broken, "state.json", {"app": "x", "chat_id": "chat-b", "created_at": START + 1})
    reels.write_json(broken, "status.json", {"stage": "edit", "state": "working", "requested_at": "not a number"})
    folder = make_reel(tmp_path)
    watchdog.check_all(tmp_path, Fakes(None).probes())
    assert health(folder)["condition"] == "gave_up"


def test_the_background_watch_checks_every_reel(tmp_path: Path) -> None:
    folder = make_reel(tmp_path)
    watchdog.start(tmp_path, Fakes(None).probes())
    assert wait_until(lambda: health(folder) and health(folder)["condition"] == "gave_up")


def test_the_time_a_chat_last_did_anything_covers_its_files_and_its_transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = make_reel(tmp_path)
    agents = tmp_path / "agents"
    monkeypatch.setattr(watchdog, "AGENTS_DIR", agents)
    (folder / "footage").mkdir()
    old, newer, newest = 1_000.0, 2_000.0, 3_000.0
    for path in folder.glob("*"):
        os.utime(path, (old, old))
    clip = folder / "footage" / "clip.mp4"
    clip.write_bytes(b"x")
    os.utime(clip, (newer, newer))
    os.utime(folder / "footage", (old, old))
    assert watchdog.last_activity(folder, "agent-1") == newer
    transcript = agents / "agent-1" / "events" / "claude" / "common_transcript" / "events.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("{}")
    os.utime(transcript, (newest, newest))
    assert watchdog.last_activity(folder, "agent-1") == newest
    assert watchdog.last_activity(folder, "another-agent") == newer
    assert watchdog.last_activity(tmp_path / "nothing-here", "another-agent") == 0.0


def test_memory_guard_stops_are_counted_from_the_time_the_stage_started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / "shed.jsonl"
    lines = [
        {"type": "process_shed", "timestamp": "2026-11-17T10:00:00Z"},
        {"type": "process_shed", "timestamp": "2026-11-17T12:00:00+00:00"},
        {"type": "process_shed", "timestamp": "2026-11-17T13:00:00Z"},
        {"type": "process_shed"},
    ]
    ledger.write_text("\n".join([*(json.dumps(line) for line in lines), "not json", ""]))
    monkeypatch.setattr(watchdog, "SHED_LEDGER", ledger)
    noon = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc).timestamp()
    assert watchdog.sheds_since(noon) == 2
    assert watchdog.sheds_since(noon + 7200) == 0
    monkeypatch.setattr(watchdog, "SHED_LEDGER", tmp_path / "missing.jsonl")
    assert watchdog.sheds_since(0) == 0


def test_free_memory_is_read_from_the_first_report_that_has_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    unreadable = tmp_path / "none"
    odd = tmp_path / "odd"
    odd.write_text("MemTotal: 1 kB\nMemAvailable: lots kB\n")
    good = tmp_path / "good"
    good.write_text("MemTotal: 8000000 kB\nMemAvailable: 2048 kB\n")
    monkeypatch.setattr(watchdog, "MEMINFO_FILES", (unreadable, odd, good))
    assert watchdog.memory_available() == 2048 * 1024
    monkeypatch.setattr(watchdog, "MEMINFO_FILES", (unreadable, odd))
    assert watchdog.memory_available() is None


def test_minutes_are_said_in_whole_minutes_and_never_zero() -> None:
    assert watchdog.minutes(5) == "1 minute" and watchdog.minutes(90) == "2 minutes" and watchdog.minutes(15 * 60) == "15 minutes"


def test_the_chat_apps_view_of_a_chat_is_read_and_a_chat_can_be_stopped(fake_chat: FakeChat, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reels, "CHAT_URL", fake_chat.url)
    fake_chat.created.append({})
    assert watchdog.chat_snapshot("chat-1") == fake_chat.agent_state
    assert watchdog.chat_snapshot("chat-77") is None
    fake_chat.agent_state = None
    assert watchdog.chat_snapshot("chat-1") is None
    watchdog.stop_chat("chat-1")
    assert fake_chat.stopped == ["chat-1"]
    monkeypatch.setattr(reels, "CHAT_URL", "http://127.0.0.1:9")
    with pytest.raises(requests.RequestException):
        watchdog.chat_snapshot("chat-1")
    watchdog.stop_chat("chat-1")  # an unreachable chat app is logged, not raised


def test_a_stage_that_finishes_while_the_check_is_running_is_not_reopened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = make_reel(tmp_path)
    fakes = Fakes(IDLE)
    watchdog.check_reel(tmp_path, REEL, START, fakes.probes())
    original = reels.read_json
    reads = {"status": 0}

    def read_json(read_folder: Path, name: str) -> Any:
        # The check reads "working"; the agent then writes "done" before the repair is made.
        if name == "status.json":
            reads["status"] += 1
            if reads["status"] == 2:
                reels.write_json(folder, "status.json", {"stage": "footage", "state": "done"})
        return original(read_folder, name)

    monkeypatch.setattr(reels, "read_json", read_json)
    watchdog.check_reel(tmp_path, REEL, START + watchdog.IDLE_GRACE_SECONDS, fakes.probes())
    assert fakes.sent == [] and original(folder, "status.json")["state"] == "done"
    assert health(folder)["repairs"] == 0
