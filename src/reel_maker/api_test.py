"""The reel API, with the chat app faked and a stand-in agent that writes the agent's files."""

import io
import os
import resource
import threading
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import requests
from flask.testing import FlaskClient

from reel_maker import reels, runner
from reel_maker.fake_chat import FakeChat, StandInAgent, parse_message, wait_until, write_reel


def create(client: FlaskClient, app: str = "deck-list") -> dict[str, Any]:
    answer = client.post("/api/reels", json={"app": app})
    assert answer.status_code == 201, answer.get_json()
    return answer.get_json()["reel"]


def get(client: FlaskClient, reel_id: str) -> dict[str, Any]:
    return client.get(f"/api/reels/{reel_id}").get_json()["reel"]


def folder_of(data_dir: Path, reel_id: str) -> Path:
    return reels.reels_dir(data_dir) / reel_id


def settle(client: FlaskClient, reel_id: str, stage: str) -> dict[str, Any]:
    """Wait for the stand-in agent to finish a stage; returns the reel."""
    done = wait_until(lambda: get(client, reel_id)["status"].get("stage") == stage and get(client, reel_id)["status"].get("state") == "done")
    assert done, get(client, reel_id)["status"]
    return get(client, reel_id)


def advance(client: FlaskClient, reel_id: str, stage: str, **inputs: Any) -> Any:
    return client.post(f"/api/reels/{reel_id}/advance", json={"stage": stage, "inputs": inputs})


def make_take(client: FlaskClient, reel_id: str, data: bytes = b"video-bytes", mime: str = "video/mp4") -> Any:
    return client.post(f"/api/reels/{reel_id}/takes", data=data, content_type=mime)


@pytest.fixture
def reel(client: FlaskClient, agent: StandInAgent) -> dict[str, Any]:
    """A reel whose research stage the stand-in agent has finished."""
    started = create(client)
    return settle(client, started["id"], "research")


# ---- apps and creating a reel ----


def test_only_the_apps_the_creator_built_are_offered(client: FlaskClient) -> None:
    apps = client.get("/api/apps").get_json()["apps"]
    assert [app["name"] for app in apps] == ["deck-list"]
    assert apps[0]["display_name"] == "Deck List" and apps[0]["description"] == "Magic deck builder"
    assert apps[0]["icon"].startswith("<svg")


def test_no_registry_means_no_apps(client: FlaskClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "APPS_REGISTRY", tmp_path / "missing.toml")
    assert client.get("/api/apps").get_json() == {"apps": []}


def test_creating_a_reel_starts_its_chat_with_the_skill_and_the_agreement(
    client: FlaskClient, fake_chat: FakeChat, isolated_app: Path
) -> None:
    reel = create(client)
    folder = folder_of(isolated_app, reel["id"])
    assert len(reel["id"]) == 12
    assert reel["request"]["app"] == {"name": "deck-list", "display_name": "Deck List", "description": "Magic deck builder"}
    assert reel["status"]["stage"] == "research" and reel["status"]["state"] == "working"
    assert reel["state"]["chat_id"] == "chat-1" and reel["state"]["app"] == "deck-list"
    assert reel["takes"] == [] and reel["has_reel_video"] is False
    (created,) = fake_chat.created
    assert created["name"] == "Reel: Deck List"
    message = created["message"]
    assert str(reels.SKILL_PATH) in message and str(reels.CONTRACT_PATH) in message
    assert reels.SKILL_PATH.is_file() and reels.CONTRACT_PATH.is_file()
    stage, named_folder = parse_message(message)
    assert stage == "research" and named_folder == folder.resolve()


def test_the_research_stage_leaves_the_interview_for_the_page(client: FlaskClient, reel: dict[str, Any]) -> None:
    assert [q["q"] for q in reel["interview"]["questions"]] == ["What is it for?", "What is different now?"]
    assert reel["interview"]["app"] == "Deck List"


def test_an_app_the_creator_did_not_build_is_refused(client: FlaskClient, fake_chat: FakeChat, isolated_app: Path) -> None:
    for name in ("chat", "reel-maker", "hidden-thing", "nope"):
        answer = client.post("/api/reels", json={"app": name})
        assert answer.status_code == 400
    assert fake_chat.created == [] and client.get("/api/reels").get_json() == {"reels": []}


def test_a_malformed_create_body_is_refused(client: FlaskClient) -> None:
    assert client.post("/api/reels", data="not json").status_code == 400
    assert client.post("/api/reels", json={"app": 3}).status_code == 400
    assert client.post("/api/reels", json={}).status_code == 400


def test_a_chat_that_refuses_leaves_no_reel_behind(client: FlaskClient, fake_chat: FakeChat, isolated_app: Path) -> None:
    fake_chat.refuse_create = True
    answer = client.post("/api/reels", json={"app": "deck-list"})
    assert answer.status_code == 502 and "couldn't start a chat" in answer.get_json()["detail"]
    assert client.get("/api/reels").get_json() == {"reels": []}
    assert list(reels.reels_dir(isolated_app).iterdir()) == []


def test_an_unreachable_chat_app_is_reported_and_leaves_no_reel(
    client: FlaskClient, isolated_app: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reels, "CHAT_URL", "http://127.0.0.1:9")
    answer = client.post("/api/reels", json={"app": "deck-list"})
    assert answer.status_code == 502 and "Couldn't reach" in answer.get_json()["detail"]
    assert list(reels.reels_dir(isolated_app).iterdir()) == []


def test_reels_are_listed_newest_first_and_stray_folders_are_ignored(client: FlaskClient, agent: StandInAgent, isolated_app: Path) -> None:
    first = create(client)["id"]
    second = create(client)["id"]
    (reels.reels_dir(isolated_app) / "strayfolder12").mkdir()
    (reels.reels_dir(isolated_app) / "note.txt").write_text("x")
    listed = client.get("/api/reels").get_json()["reels"]
    assert [item["id"] for item in listed] == [second, first]
    assert listed[0]["app"] == "deck-list" and listed[0]["chat_id"] == "chat-2"


def test_an_unknown_or_malformed_reel_id_is_a_404(client: FlaskClient) -> None:
    for bad in ("abcdefabcdef", "short", "..", "ABCDEFABCDEF"):
        assert client.get(f"/api/reels/{bad}").status_code == 404


def test_a_damaged_agent_file_shows_as_missing_not_as_a_crash(client: FlaskClient, reel: dict[str, Any], isolated_app: Path) -> None:
    (folder_of(isolated_app, reel["id"]) / "interview.json").write_text("{not json")
    assert get(client, reel["id"])["interview"] is None


# ---- stages and their inputs ----


def test_every_stage_runs_in_order_and_each_input_reaches_the_agent(client: FlaskClient, reel: dict[str, Any], isolated_app: Path) -> None:
    reel_id = reel["id"]
    assert advance(client, reel_id, "story", answers={"answers": ["tag cards", "it is all tagged"]}).status_code == 200
    story = settle(client, reel_id, "story")
    assert story["answers"] == {"answers": ["tag cards", "it is all tagged"]}
    assert story["tones"]["story"] == "You said: tag cards / it is all tagged"

    assert advance(client, reel_id, "script", choice={"tone": "dry", "direction": "tour"}).status_code == 200
    script = settle(client, reel_id, "script")
    assert script["choice"] == {"tone": "dry", "direction": "tour"}
    assert script["script"]["lines"][0]["say"] == "A dry opening line."

    assert advance(client, reel_id, "footage").status_code == 200
    footage = settle(client, reel_id, "footage")
    assert footage["footage"]["clips"][0]["file"] == "footage/clip-1.mp4"
    assert client.get(f"/api/reels/{reel_id}/files/footage/clip-1.mp4").data == b"not really a video"

    assert make_take(client, reel_id).status_code == 201
    assert advance(client, reel_id, "edit", choice={"take": "take-1.mp4"}).status_code == 200
    edited = settle(client, reel_id, "edit")
    assert edited["reel"]["caption"] == "Cut from take-1.mp4" and edited["has_reel_video"] is True
    assert edited["state"]["cuts"] == 1
    assert client.get(f"/api/reels/{reel_id}/files/reel.mp4").data == b"not really a reel"


def test_each_stage_is_messaged_to_the_reels_chat_with_its_folder(client: FlaskClient, reel: dict[str, Any], fake_chat: FakeChat, isolated_app: Path) -> None:
    advance(client, reel["id"], "story", answers={"answers": ["a"]})
    wait_until(lambda: len(fake_chat.messages) == 2)
    chat_id, text = fake_chat.messages[-1]
    assert chat_id == "chat-1"
    assert text == f"REEL STAGE: story\nReel folder: {folder_of(isolated_app, reel['id']).resolve()}"


def test_a_stage_is_refused_while_the_last_one_is_still_running(client: FlaskClient, reel: dict[str, Any], agent: StandInAgent, fake_chat: FakeChat) -> None:
    agent.silent.add("story")
    assert advance(client, reel["id"], "story", answers={"answers": ["a"]}).status_code == 200
    again = advance(client, reel["id"], "story", answers={"answers": ["b"]})
    assert again.status_code == 409 and "still working" in again.get_json()["detail"]
    assert get(client, reel["id"])["answers"] == {"answers": ["a"]}


def test_stages_that_are_not_the_agents_are_refused(client: FlaskClient, reel: dict[str, Any], isolated_app: Path) -> None:
    for stage in ("research", "nonsense", ""):
        assert advance(client, reel["id"], stage).status_code == 409
    assert get(client, reel["id"])["status"]["state"] == "done"


@pytest.mark.parametrize(
    ("stage", "inputs"),
    [
        ("story", {"change": {"text": "hi"}}),
        ("story", {"status": {"stage": "edit", "state": "done"}}),
        ("story", {"interview": {"questions": []}}),
        ("story", {"state": {"chat_id": "elsewhere"}}),
        ("story", {"health": {"condition": "gave_up"}}),
        ("story", {"answers": ["not", "an", "object"]}),
        ("script", {"reel": {"caption": "forged"}}),
        ("script", {"answers": {"answers": []}}),
        ("footage", {"change": {"text": "hi"}}),
        ("footage", {"choice": {"tone": "x"}}),
        ("edit", {"script": {"lines": []}}),
        ("script", {"change": {"text": "   "}}),
        ("script", {"change": {}}),
    ],
)
def test_an_input_a_stage_does_not_take_is_refused_and_nothing_is_written(
    client: FlaskClient, reel: dict[str, Any], isolated_app: Path, stage: str, inputs: dict[str, Any]
) -> None:
    folder = folder_of(isolated_app, reel["id"])
    before = {path.name: path.read_bytes() for path in folder.iterdir()}
    answer = advance(client, reel["id"], stage, **inputs)
    assert answer.status_code == 409
    assert {path.name: path.read_bytes() for path in folder.iterdir()} == before


def test_a_change_request_is_for_one_request_only(client: FlaskClient, reel: dict[str, Any], isolated_app: Path) -> None:
    reel_id = reel["id"]
    advance(client, reel_id, "story", answers={"answers": ["a"]})
    settle(client, reel_id, "story")
    advance(client, reel_id, "script", choice={"tone": "calm", "direction": "before-after"})
    settle(client, reel_id, "script")
    assert advance(client, reel_id, "script", change={"text": "more punch in line 2"}).status_code == 200
    changed = settle(client, reel_id, "script")
    assert changed["change"] == {"text": "more punch in line 2"}
    assert [line["say"] for line in changed["script"]["lines"]][1] == "Changed: more punch in line 2"
    # The choice from before is kept when a change is asked for on its own.
    assert changed["choice"] == {"tone": "calm", "direction": "before-after"}
    advance(client, reel_id, "footage")
    after = settle(client, reel_id, "footage")
    assert after["change"] is None and not (folder_of(isolated_app, reel_id) / "change.json").exists()


def test_a_choice_adds_to_the_earlier_one_instead_of_replacing_it(client: FlaskClient, reel: dict[str, Any]) -> None:
    advance(client, reel["id"], "story", answers={"answers": ["a"]})
    settle(client, reel["id"], "story")
    advance(client, reel["id"], "script", choice={"tone": "calm"})
    settle(client, reel["id"], "script")
    advance(client, reel["id"], "script", choice={"direction": "tour"})
    assert settle(client, reel["id"], "script")["choice"] == {"tone": "calm", "direction": "tour"}


def test_the_edit_needs_a_take_and_only_one_that_exists(client: FlaskClient, reel: dict[str, Any]) -> None:
    reel_id = reel["id"]
    assert advance(client, reel_id, "edit", choice={"take": "take-1.mp4"}).status_code == 409
    assert advance(client, reel_id, "edit").status_code == 409
    make_take(client, reel_id)
    refused = advance(client, reel_id, "edit", choice={"take": "take-9.mp4"})
    assert refused.status_code == 409 and "Film a take" in refused.get_json()["detail"]
    assert get(client, reel_id)["choice"]["take"] == "take-1.mp4"
    assert get(client, reel_id)["status"]["state"] == "done"


def test_each_cut_is_numbered_and_a_change_to_the_edit_recuts_the_chosen_take(client: FlaskClient, reel: dict[str, Any]) -> None:
    reel_id = reel["id"]
    make_take(client, reel_id)
    advance(client, reel_id, "edit", choice={"take": "take-1.mp4"})
    assert settle(client, reel_id, "edit")["state"]["cuts"] == 1
    assert advance(client, reel_id, "edit", change={"text": "quieter music"}).status_code == 200
    second = settle(client, reel_id, "edit")
    assert second["state"]["cuts"] == 2
    assert second["reel"]["caption"] == "Cut from take-1.mp4 with: quieter music"


def test_a_reel_whose_chat_never_started_cannot_advance(client: FlaskClient, isolated_app: Path) -> None:
    folder = folder_of(isolated_app, "abcdefabcdef")
    write_reel(folder, state={"app": "deck-list", "chat_id": "", "created_at": 1}, status={"stage": "research", "state": "done"})
    answer = advance(client, "abcdefabcdef", "story", answers={"answers": []})
    assert answer.status_code == 409 and "isn't running" in answer.get_json()["detail"]


def test_a_failed_stage_can_be_asked_for_again(client: FlaskClient, reel: dict[str, Any], agent: StandInAgent) -> None:
    agent.failing["story"] = "ran out of memory"
    advance(client, reel["id"], "story", answers={"answers": ["a"]})
    failed = wait_until(lambda: get(client, reel["id"])["status"]["state"] == "failed")
    assert failed and get(client, reel["id"])["status"]["error"] == "ran out of memory"
    agent.failing.clear()
    assert advance(client, reel["id"], "story", answers={"answers": ["a"]}).status_code == 200
    assert settle(client, reel["id"], "story")["tones"] is not None


def test_a_message_the_chat_refuses_is_sent_again_until_it_is_taken(client: FlaskClient, reel: dict[str, Any], fake_chat: FakeChat) -> None:
    fake_chat.refuse_messages = 2
    advance(client, reel["id"], "story", answers={"answers": ["a"]})
    settle(client, reel["id"], "story")
    assert fake_chat.refuse_messages == 0


# ---- takes ----


def test_takes_are_stored_numbered_and_the_newest_is_chosen(client: FlaskClient, reel: dict[str, Any], isolated_app: Path) -> None:
    first = make_take(client, reel["id"], b"a" * 10)
    assert first.status_code == 201 and first.get_json() == {"name": "take-1.mp4", "number": 1, "bytes": 10}
    second = make_take(client, reel["id"], b"b" * 20, mime="video/quicktime; codecs=hevc")
    assert second.get_json() == {"name": "take-2.mov", "number": 2, "bytes": 20}
    snapshot = get(client, reel["id"])
    assert [(t["name"], t["bytes"]) for t in snapshot["takes"]] == [("take-1.mp4", 10), ("take-2.mov", 20)]
    assert snapshot["choice"]["take"] == "take-2.mov"
    assert (folder_of(isolated_app, reel["id"]) / "takes" / "take-2.mov").read_bytes() == b"b" * 20


def test_an_unknown_video_type_is_kept_as_mp4(client: FlaskClient, reel: dict[str, Any]) -> None:
    assert make_take(client, reel["id"], mime="video/x-weird").get_json()["name"] == "take-1.mp4"


def test_an_empty_take_is_refused_and_leaves_nothing_behind(client: FlaskClient, reel: dict[str, Any], isolated_app: Path) -> None:
    make_take(client, reel["id"], b"first")
    answer = make_take(client, reel["id"], b"")
    assert answer.status_code == 400 and "empty" in answer.get_json()["detail"]
    snapshot = get(client, reel["id"])
    assert [t["name"] for t in snapshot["takes"]] == ["take-1.mp4"] and snapshot["choice"]["take"] == "take-1.mp4"
    assert sorted(p.name for p in (folder_of(isolated_app, reel["id"]) / "takes").iterdir()) == ["take-1.mp4"]


def test_a_body_that_is_not_a_video_is_refused(client: FlaskClient, reel: dict[str, Any]) -> None:
    for mime in ("application/json", "text/plain", "multipart/form-data; boundary=x"):
        assert make_take(client, reel["id"], b"hello", mime=mime).status_code == 400
    assert get(client, reel["id"])["takes"] == []


def test_a_take_for_a_reel_that_does_not_exist_is_refused(client: FlaskClient) -> None:
    assert make_take(client, "abcdefabcdef").status_code == 400


class DroppedStream:
    """A phone that loses its connection part way through an upload."""

    def __init__(self) -> None:
        self.sent = False

    def read(self, size: int) -> bytes:
        if self.sent:
            raise ConnectionError("phone went away")
        self.sent = True
        return b"x" * 1000


def test_an_upload_that_drops_leaves_no_partial_file_and_no_new_take(reel: dict[str, Any], isolated_app: Path) -> None:
    with pytest.raises(ConnectionError):
        reels.save_take(isolated_app, reel["id"], "video/mp4", DroppedStream())
    takes_folder = folder_of(isolated_app, reel["id"]) / "takes"
    assert list(takes_folder.iterdir()) == []
    assert reels.list_takes(folder_of(isolated_app, reel["id"])) == []
    assert (reels.read_json(folder_of(isolated_app, reel["id"]), "choice.json") or {}).get("take") is None


def test_take_numbers_continue_after_a_gap(reel: dict[str, Any], isolated_app: Path) -> None:
    reels.save_take(isolated_app, reel["id"], "video/mp4", io.BytesIO(b"1"))
    reels.save_take(isolated_app, reel["id"], "video/mp4", io.BytesIO(b"2"))
    (folder_of(isolated_app, reel["id"]) / "takes" / "take-1.mp4").unlink()
    assert reels.save_take(isolated_app, reel["id"], "video/mp4", io.BytesIO(b"3"))["number"] == 3


def peak_memory_megabytes() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def test_a_large_take_streams_to_disk_without_being_held_in_memory(
    server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On disk, not in /tmp (a small RAM disk that counts against the workspace's memory).
    with tempfile.TemporaryDirectory(dir="/var/tmp") as scratch:
        data_dir = Path(scratch)
        monkeypatch.setattr(runner, "DATA_DIR", data_dir)
        write_reel(folder_of(data_dir, "abcdefabcdef"), state={"app": "deck-list", "chat_id": "chat-1", "created_at": 1})
        chunk = os.urandom(1024 * 1024)
        total_megabytes = 100

        def body() -> Iterator[bytes]:
            for _ in range(total_megabytes):
                yield chunk

        before = peak_memory_megabytes()
        answer = requests.post(f"{server}/api/reels/abcdefabcdef/takes", data=body(), headers={"Content-Type": "video/mp4"}, timeout=120)
        assert answer.status_code == 201 and answer.json()["bytes"] == total_megabytes * 1024 * 1024
        stored = folder_of(data_dir, "abcdefabcdef") / "takes" / "take-1.mp4"
        assert stored.stat().st_size == total_megabytes * 1024 * 1024
        with stored.open("rb") as handle:
            assert handle.read(1024 * 1024) == chunk
        # Held whole it would add the full 100 MB to the process's high-water mark.
        assert peak_memory_megabytes() - before < total_megabytes / 2
        assert not list(stored.parent.glob(".upload-*"))


def test_choosing_a_take_changes_which_one_the_edit_uses(client: FlaskClient, reel: dict[str, Any]) -> None:
    make_take(client, reel["id"], b"1")
    make_take(client, reel["id"], b"2")
    assert get(client, reel["id"])["choice"]["take"] == "take-2.mp4"
    chosen = client.post(f"/api/reels/{reel['id']}/choose-take", json={"take": "take-1.mp4"})
    assert chosen.status_code == 200 and chosen.get_json()["reel"]["choice"]["take"] == "take-1.mp4"
    advance(client, reel["id"], "edit")
    assert settle(client, reel["id"], "edit")["reel"]["caption"] == "Cut from take-1.mp4"


@pytest.mark.parametrize("take", ["take-7.mp4", "../choice.json", "../../etc/passwd", "", "take-1.mp4/../take-1.mp4"])
def test_a_take_that_is_not_in_the_reel_cannot_be_chosen(client: FlaskClient, reel: dict[str, Any], take: str) -> None:
    make_take(client, reel["id"], b"1")
    answer = client.post(f"/api/reels/{reel['id']}/choose-take", json={"take": take})
    assert answer.status_code == 400 and answer.get_json()["detail"] == "That take is not in this reel."
    assert get(client, reel["id"])["choice"]["take"] == "take-1.mp4"


# ---- files ----


def test_a_take_is_served_with_range_support_and_can_be_downloaded(client: FlaskClient, reel: dict[str, Any]) -> None:
    make_take(client, reel["id"], b"0123456789")
    whole = client.get(f"/api/reels/{reel['id']}/files/takes/take-1.mp4")
    assert whole.status_code == 200 and whole.data == b"0123456789" and whole.mimetype == "video/mp4"
    part = client.get(f"/api/reels/{reel['id']}/files/takes/take-1.mp4", headers={"Range": "bytes=2-4"})
    assert part.status_code == 206 and part.data == b"234" and part.headers["Content-Range"] == "bytes 2-4/10"
    download = client.get(f"/api/reels/{reel['id']}/files/takes/take-1.mp4?download=1")
    assert "attachment" in download.headers["Content-Disposition"] and "take-1.mp4" in download.headers["Content-Disposition"]
    assert "attachment" not in whole.headers.get("Content-Disposition", "")


def test_files_are_only_served_from_inside_the_reels_own_folder(
    client: FlaskClient, agent: StandInAgent, isolated_app: Path, tmp_path: Path
) -> None:
    mine = create(client)["id"]
    other = create(client)["id"]
    make_take(client, other, b"someone else's take")
    secret = tmp_path / "secret.mp4"
    secret.write_bytes(b"outside the reels")
    (folder_of(isolated_app, mine) / "leak.mp4").symlink_to(secret)
    (folder_of(isolated_app, mine) / "linked").symlink_to(tmp_path, target_is_directory=True)
    attempts = [
        f"../{other}/takes/take-1.mp4", f"%2e%2e/{other}/takes/take-1.mp4", f"..%2f{other}%2ftakes%2ftake-1.mp4",
        "../../../../etc/hostname", "leak.mp4", "linked/secret.mp4", f"/{secret}", "state.json", "request.json",
        "takes/take-1.txt", "takes", "", "missing.mp4",
    ]
    for name in attempts:
        answer = client.get(f"/api/reels/{mine}/files/{name}", follow_redirects=True)
        assert answer.status_code == 404, name
        assert b"outside the reels" not in answer.data and b"someone else" not in answer.data
    assert client.get(f"/api/reels/{other}/files/takes/take-1.mp4").data == b"someone else's take"
    assert client.get("/api/reels/abcdefabcdef/files/reel.mp4").status_code == 404
    assert client.get("/api/reels/..%2f..%2fetc/files/hostname").status_code == 404


# ---- retry ----


def test_try_again_asks_for_the_stage_afresh_and_resets_the_repair_count(
    client: FlaskClient, reel: dict[str, Any], agent: StandInAgent, fake_chat: FakeChat, isolated_app: Path
) -> None:
    agent.silent.add("story")
    advance(client, reel["id"], "story", answers={"answers": ["a"]})
    folder = folder_of(isolated_app, reel["id"])
    reels.write_json(folder, "health.json", {"stage": "story", "condition": "gave_up", "repairs": 3, "history": [{"at": 1, "text": "tried"}]})
    agent.silent.clear()
    answer = client.post(f"/api/reels/{reel['id']}/retry")
    assert answer.status_code == 200
    health = answer.get_json()["reel"]["health"]
    assert health["repairs"] == 0 and health["condition"] == "working"
    assert health["history"][0]["text"] == "tried" and health["history"][-1]["text"] == "You asked Studio to try again."
    assert settle(client, reel["id"], "story")["tones"] is not None
    assert [text for _, text in fake_chat.messages if text.startswith("REEL STAGE: story")] == [
        f"REEL STAGE: story\nReel folder: {folder.resolve()}"
    ] * 2


def test_there_is_nothing_to_try_again_on_a_finished_stage_or_a_dead_reel(client: FlaskClient, reel: dict[str, Any], fake_chat: FakeChat) -> None:
    sent = len(fake_chat.messages)
    assert client.post(f"/api/reels/{reel['id']}/retry").status_code == 409
    assert client.post("/api/reels/abcdefabcdef/retry").status_code == 409
    assert len(fake_chat.messages) == sent


# ---- the pages and small routes ----


def test_pages_carry_the_security_policy_and_the_shared_address(client: FlaskClient, fake_chat: FakeChat) -> None:
    fake_chat.inventory = [
        {"name": "reel-maker", "share_url": "https://reel-maker.example.test/"},
        {"name": "chat", "share_url": "https://chat.example.test/"},
    ]
    for path in ("/", "/phone"):
        page = client.get(path)
        assert page.status_code == 200 and page.mimetype == "text/html"
        assert "default-src 'self'" in page.headers["Content-Security-Policy"]
        assert 'data-public-address="https://reel-maker.example.test/"' in page.get_data(as_text=True)
        assert 'data-chat-address="https://chat.example.test/"' in page.get_data(as_text=True)


def test_a_page_opened_while_the_workspace_is_not_shared_has_no_public_address(client: FlaskClient) -> None:
    assert 'data-public-address=""' in client.get("/").get_data(as_text=True)


def test_the_qr_code_is_an_svg_for_the_text_given_and_refuses_nothing_or_too_much(client: FlaskClient) -> None:
    ok = client.get("/qr.svg?data=https://example.test/phone")
    assert ok.status_code == 200 and ok.mimetype == "image/svg+xml" and b"<svg" in ok.data
    assert client.get("/qr.svg").status_code == 400
    assert client.get("/qr.svg?data=" + "x" * (runner.MAX_QR_TEXT_LENGTH + 1)).status_code == 400


def test_only_the_shipped_scripts_and_sample_videos_are_served(client: FlaskClient) -> None:
    for name in ("style.css", "wizard.js", "phone.js", "share.js"):
        assert client.get(f"/_assets/{name}").status_code == 200
    for name in ("wizard.html", "../runner.py", "reels.py", "missing.js"):
        assert client.get(f"/_assets/{name}").status_code == 404
    assert client.get("/_media/deck-list-reel/deck-list-reel.mp4").status_code == 200
    assert client.get("/_media/../../pyproject.toml").status_code == 404
    assert client.get("/_media/deck-list-reel/shots/9-nothing.mp4").status_code == 404
    assert client.get("/_static/nothing.js").status_code == 404
    assert client.get("/icon.svg").mimetype == "image/svg+xml"
    assert client.get("/health").get_json() == {"status": "ok"}


# ---- one request at a time, and a bound on takes ----


def test_two_clicks_at_once_start_the_stage_only_once(client: FlaskClient, reel: dict[str, Any], agent: StandInAgent, fake_chat: FakeChat) -> None:
    agent.silent.add("story")
    results: list[int] = []

    def click() -> None:
        results.append(advance(runner.app.test_client(), reel["id"], "story", answers={"answers": ["a"]}).status_code)

    threads = [threading.Thread(target=click) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [200] + [409] * 7
    assert wait_until(lambda: agent.handled.count("story") == 1)
    assert len([text for _, text in fake_chat.messages if "REEL STAGE: story" in text]) == 1


def test_only_the_newest_takes_are_kept(reel: dict[str, Any], isolated_app: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reels, "MAX_TAKES", 3)
    folder = folder_of(isolated_app, reel["id"])
    for number in range(1, 3):
        reels.save_take(isolated_app, reel["id"], "video/mp4", io.BytesIO(str(number).encode()))
    assert [take["name"] for take in reels.list_takes(folder)] == ["take-1.mp4", "take-2.mp4"]
    for number in range(3, 7):
        reels.save_take(isolated_app, reel["id"], "video/mp4", io.BytesIO(str(number).encode()))
    assert [take["name"] for take in reels.list_takes(folder)] == ["take-4.mp4", "take-5.mp4", "take-6.mp4"]
    assert reels.read_json(folder, "choice.json") == {"take": "take-6.mp4"}
    assert sorted(path.name for path in (folder / "takes").iterdir()) == ["take-4.mp4", "take-5.mp4", "take-6.mp4"]
