"""The pages in a real browser: the example run, a real reel driven through every screen by a stand-in agent, the
phone page, and the waiting screen's stall messages. The chat app is faked; nothing leaves the machine."""

import io
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Dialog, FilePayload, Page, expect

from reel_maker import reels
from reel_maker.fake_chat import FakeChat, StandInAgent, wait_until, write_reel

pytestmark = [pytest.mark.browser, pytest.mark.timeout(240, func_only=False)]

REEL = "abcdef123456"
# The wait for something Studio is doing: the page polls every 2.5 seconds.
STUDIO_WAIT = 20_000
TAKE: FilePayload = {"name": "take.mp4", "mimeType": "video/mp4", "buffer": b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2000}


@pytest.fixture
def dialogs() -> list[str]:
    """The alerts the page showed, which a test that expects one clears."""
    return []


@pytest.fixture
def page(browser: Browser, dialogs: list[str]) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    opened = context.new_page()
    errors: list[str] = []
    opened.on("pageerror", lambda error: errors.append(str(error)))

    def note_dialog(dialog: Dialog) -> None:
        dialogs.append(dialog.message)
        dialog.dismiss()

    opened.on("dialog", note_dialog)
    yield opened
    context.close()
    assert errors == []
    assert dialogs == []


@pytest.fixture
def phone(browser: Browser) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 393, "height": 852}, has_touch=True, is_mobile=True)
    opened = context.new_page()
    errors: list[str] = []
    opened.on("pageerror", lambda error: errors.append(str(error)))
    yield opened
    context.close()
    assert errors == []


def visible_step(page: Page, key: str) -> Any:
    return page.locator(f'section[data-step="{key}"]')


def seed_reel(data_dir: Path, stage: str = "footage", state: str = "done", reel_id: str = REEL, **files: Any) -> Path:
    """A reel folder as if the agent had got as far as ``stage``."""
    folder = reels.reels_dir(data_dir) / reel_id
    write_reel(
        folder,
        request={"app": {"name": "deck-list", "display_name": "Deck List", "description": "Magic deck builder"}},
        state={"app": "deck-list", "chat_id": "chat-1", "created_at": time.time()},
        status={"stage": stage, "state": state, "requested_at": time.time() - 30},
        **files,
    )
    return folder


EMPTY_TAKE: FilePayload = {"name": "empty.mp4", "mimeType": "video/mp4", "buffer": b""}
SCRIPT = {"lines": [{"say": "First line to read.", "screen": "face", "shot": "face"}, {"say": "Second line to read.", "screen": "app", "shot": "app"}]}


# ---- the example run ----


def test_every_step_of_the_example_run_can_be_reached_from_the_step_list(server: str, page: Page) -> None:
    page.goto(f"{server}/?example=1")
    expect(page.locator("#example-banner")).to_be_visible()
    expect(page.locator("#welcome")).to_be_hidden()
    buttons = page.locator("#stepper button")
    expect(buttons).to_have_count(7)
    expect(buttons).to_have_text([re.compile(title) for title in (
        "Pick your app", "Answer a few questions", "Pick a tone", "See your script", "Check the footage", "Film your take", "Watch your reel")])
    for key, index in (("edit", 6), ("film", 5), ("footage", 4), ("script", 3), ("tone", 2), ("interview", 1), ("app", 0)):
        buttons.nth(index).click()
        expect(visible_step(page, key)).to_be_visible()
        assert [step for step in ("app", "interview", "tone", "script", "footage", "film", "edit") if visible_step(page, step).is_visible()] == [key]

    expect(visible_step(page, "app")).to_contain_text("Deck List")
    page.locator("#stepper button").nth(1).click()
    expect(page.locator("#q-count")).to_have_text("Question 1 of 7")
    expect(page.locator("#question-host h1")).to_contain_text("most interesting thing about Deck List")
    page.locator("#stepper button").nth(2).click()
    expect(page.locator("#tones .tone")).to_have_count(3)
    expect(page.locator("#story-line")).to_contain_text("Before and after")
    page.locator("#stepper button").nth(3).click()
    expect(page.locator("#script-lines li")).to_have_count(8)
    expect(page.locator("#animatic-caption")).to_have_text("Putting one card in three categories on Archidekt? That's a lot of clicking.")
    page.locator("#stepper button").nth(4).click()
    expect(page.locator("#clips figure")).to_have_count(6)
    expect(page.locator("#clips video").first).to_have_attribute("src", "/_media/deck-list-reel/shots/2-first-prompt.mp4")
    expect(page.locator("#privacy-list li")).to_have_count(2)
    page.locator("#stepper button").nth(5).click()
    expect(page.locator("#qr")).to_have_attribute("src", re.compile(r"^/qr\.svg\?data=.*phone%3Fexample%3D1$"))
    expect(page.locator("#desk-takes .take-row.got")).to_have_count(2)
    expect(page.locator("#desk-takes .chosen")).to_contain_text("Take 2")
    page.locator("#stepper button").nth(6).click()
    expect(page.locator("#edit-version")).to_have_text("Version 1")
    expect(page.locator("#final-video")).to_have_attribute("src", "/_media/deck-list-reel/deck-list-reel.mp4")
    expect(page.locator("#reel-checks li")).to_have_count(4)
    expect(page.locator("#desk-share textarea")).to_have_value(re.compile("Archidekt made me click through menus"))
    expect(page.locator("#desk-share .platform")).to_have_count(5)
    expect(page.locator('#desk-share a[data-role="save"]')).to_have_attribute("download", "deck-list-reel.mp4")
    assert page.request.get(f"{server}/_media/deck-list-reel/deck-list-reel.mp4").status == 200


def test_the_example_run_waits_between_steps_and_skips_ahead(server: str, page: Page) -> None:
    page.goto(f"{server}/?example=1")
    page.locator("#next").click()
    expect(visible_step(page, "pending")).to_be_visible()
    expect(page.locator("#pending-title")).to_have_text("Studio is reading up on Deck List")
    expect(page.locator("#pending-list li")).to_have_count(3)
    expect(page.locator("#skip-wait")).to_have_text("Skip ahead")
    page.locator("#skip-wait").click()
    expect(visible_step(page, "interview")).to_be_visible()
    for _ in range(6):
        page.locator("#q-next").click()
    expect(page.locator("#q-next")).to_have_text("Done with questions")
    page.locator("#q-next").click()
    expect(page.locator("#pending-title")).to_have_text("Studio is finding your story")
    page.locator("#skip-wait").click()
    expect(visible_step(page, "tone")).to_be_visible()


def test_the_example_run_changes_the_script_and_the_cut(server: str, page: Page) -> None:
    page.goto(f"{server}/?example=1")
    page.locator("#stepper button").nth(3).click()
    page.locator("#script-ask").fill("make line 3 sound more like me")
    page.locator("#script-ask-send").click()
    expect(page.locator("#pending-title")).to_have_text("Studio is rewriting your script")
    page.locator("#skip-wait").click()
    expect(visible_step(page, "script")).to_be_visible()
    page.locator("#stepper button").nth(6).click()
    page.locator("#edit-ask").fill("music too busy")
    page.locator("#edit-ask-send").click()
    expect(page.locator("#pending-title")).to_have_text("Studio is making your changes")
    page.locator("#skip-wait").click()
    expect(page.locator("#edit-version")).to_have_text("Version 2")


def test_the_example_phone_page_shows_the_finished_reel_and_sends_nothing(server: str, phone: Page) -> None:
    phone.goto(f"{server}/phone?example=1")
    expect(phone.locator("#example-banner")).to_be_visible()
    expect(phone.locator("#phone-ready")).to_be_visible()
    expect(phone.locator("#ready-video")).to_have_attribute("src", "/_media/deck-list-reel/deck-list-reel.mp4")
    expect(phone.locator("#prompter p")).to_have_count(8)
    expect(phone.locator("#phone-share textarea")).to_have_value(re.compile("Archidekt"))
    phone.locator("#record-input").set_input_files(TAKE)
    expect(phone.locator("#phone-message")).to_contain_text("example run")
    expect(phone.locator("#phone-takes")).to_be_hidden()


# ---- a real reel, every screen ----


def test_a_real_reel_goes_through_every_screen_with_a_stand_in_agent(
    server: str, page: Page, agent: StandInAgent, fake_chat: FakeChat, isolated_app: Path
) -> None:
    fake_chat.inventory = [{"name": "chat", "share_url": "https://chat.example.test/"}]
    page.goto(f"{server}/")
    expect(page.locator("#welcome")).to_be_visible()
    expect(page.locator("#layout")).to_be_hidden()
    page.locator("#start-own").click()

    # 1. Pick the app.
    expect(visible_step(page, "app")).to_be_visible()
    expect(page.locator("#app-grid .app-tile")).to_have_count(1)
    expect(page.locator("#app-grid .app-tile")).to_contain_text("Magic deck builder")
    expect(page.locator("#next")).to_be_disabled()
    page.locator("#app-grid .app-tile").click()
    expect(page.locator("#next")).to_be_enabled()
    page.locator("#next").click()
    expect(page.locator("#pending-title")).to_have_text("Studio is reading up on Deck List")
    expect(page.locator("#stepper button.current")).to_have_text(re.compile("Answer a few questions"))
    expect(page.locator("#stepper button.current")).to_be_disabled()
    expect(page.locator("#stepper button").nth(0)).to_contain_text("\u2713")
    expect(page.locator("#stepper button").nth(2)).to_be_disabled()
    reel_id = page.url.split("reel=")[1]
    assert re.fullmatch(r"[a-z0-9]{12}", reel_id)
    expect(page.locator("#pending-chat")).to_have_attribute("href", "https://chat.example.test/?chat=chat-1")

    # 2. The interview, with Studio's guesses.
    expect(visible_step(page, "interview")).to_be_visible(timeout=STUDIO_WAIT)
    expect(page.locator("#q-count")).to_have_text("Question 1 of 2")
    expect(page.locator("#question-host h1")).to_have_text("What is it for?")
    expect(page.locator("#question-host textarea")).to_have_value("")
    page.locator("#use-guess").click()
    expect(page.locator("#question-host textarea")).to_have_value("Tracking decks.")
    page.locator("#q-next").click()
    expect(page.locator("#q-count")).to_have_text("Question 2 of 2")
    expect(page.locator("blockquote")).to_have_text("make me a deck list")
    page.locator("#answer").fill("my own words")
    page.locator("#q-prev").click()
    expect(page.locator("#question-host textarea")).to_have_value("Tracking decks.")
    page.locator("#q-next").click()
    expect(page.locator("#question-host textarea")).to_have_value("my own words")
    expect(page.locator("#q-next")).to_have_text("Done with questions")
    page.locator("#q-next").click()

    # 3. Tones come back knowing the answers.
    expect(page.locator("#pending-title")).to_have_text("Studio is finding your story")
    expect(visible_step(page, "tone")).to_be_visible(timeout=STUDIO_WAIT)
    expect(page.locator("#story-line")).to_have_text("The story: You said: Tracking decks. / my own words")
    expect(page.locator("#tones .tone")).to_have_count(2)
    expect(page.locator('input[name="tone"]:checked')).to_have_value("calm")
    page.locator('input[name="tone"][value="dry"]').check()
    page.locator("#next").click()

    # 4. The script follows the chosen tone, and a change comes back to the same screen.
    expect(page.locator("#pending-title")).to_have_text("Studio is writing your script")
    expect(visible_step(page, "script")).to_be_visible(timeout=STUDIO_WAIT)
    expect(page.locator("#script-lines li .say")).to_have_text(["A dry opening line.", "Then the app does its thing.", "Made with Studio."])
    expect(page.locator("#direction-text")).to_contain_text("Before and after")
    page.locator("#animatic-play").click()
    expect(page.locator("#animatic-caption")).to_have_text("A dry opening line.")
    page.locator("#script-ask").fill("make it punchier")
    page.locator("#script-ask-send").click()
    expect(page.locator("#pending-title")).to_have_text("Studio is rewriting your script")
    expect(visible_step(page, "script")).to_be_visible(timeout=STUDIO_WAIT)
    expect(page.locator("#script-lines li .say").nth(1)).to_have_text("Changed: make it punchier")
    page.locator("#next").click()

    # 5. Footage.
    expect(page.locator("#pending-title")).to_have_text("Studio is filming Deck List")
    expect(visible_step(page, "footage")).to_be_visible(timeout=STUDIO_WAIT)
    expect(page.locator("#clips video")).to_have_attribute("src", f"/api/reels/{reel_id}/files/footage/clip-1.mp4")
    expect(page.locator("#clips figcaption")).to_have_text("1. The app")
    expect(page.locator("#privacy-list li")).to_have_text("Everything shown is made up.")
    assert page.request.get(f"{server}/api/reels/{reel_id}/files/footage/clip-1.mp4").status == 200
    page.locator("#next").click()

    # 6. Film the take: the phone page sends it, this screen notices.
    expect(visible_step(page, "film")).to_be_visible()
    expect(page.locator("#next")).to_have_text("Edit my reel")
    expect(page.locator("#next")).to_be_disabled()
    expect(page.locator("#desk-takes .take-row.waiting")).to_be_visible()
    expect(page.locator("#phone-url")).to_have_text(f"{server}/phone?reel={reel_id}")
    expect(page.locator("#qr")).to_have_attribute("src", re.compile("^/qr.svg"))
    phone_page = page.context.new_page()
    phone_page.goto(f"{server}/phone?reel={reel_id}")
    expect(phone_page.locator("#prompter p")).to_have_count(4)
    phone_page.locator("#record-input").set_input_files(TAKE)
    expect(phone_page.locator("#phone-takes .phone-take")).to_have_count(1)
    phone_page.close()
    expect(page.locator("#desk-takes .take-row.got")).to_have_count(1, timeout=10_000)
    expect(page.locator("#desk-takes .chosen")).to_contain_text("Using this one")
    expect(page.locator("#next")).to_be_enabled()
    page.locator("#next").click()

    # 7. The reel, then a change to it.
    expect(page.locator("#pending-title")).to_have_text("Studio is editing your reel")
    expect(visible_step(page, "edit")).to_be_visible(timeout=STUDIO_WAIT)
    expect(page.locator("#edit-version")).to_have_text("Version 1")
    expect(page.locator("#final-video")).to_have_attribute("src", f"/api/reels/{reel_id}/files/reel.mp4?v=1")
    expect(page.locator("#reel-checks li")).to_have_text("Every word kept")
    expect(page.locator("#reel-notes li")).to_have_text("Watch it with sound on.")
    expect(page.locator("#desk-share textarea")).to_have_value("Cut from take-1.mp4")
    expect(page.locator('#desk-share a[data-role="save"]')).to_have_attribute("download", "deck-list-reel.mp4")
    assert page.request.get(f"{server}/api/reels/{reel_id}/files/reel.mp4?v=1").body() == b"not really a reel"
    page.locator("#edit-ask").fill("quieter music")
    page.locator("#edit-ask-send").click()
    expect(page.locator("#pending-title")).to_have_text("Studio is making your changes")
    expect(visible_step(page, "edit")).to_be_visible(timeout=STUDIO_WAIT)
    expect(page.locator("#edit-version")).to_have_text("Version 2")
    expect(page.locator("#final-video")).to_have_attribute("src", f"/api/reels/{reel_id}/files/reel.mp4?v=2")
    expect(page.locator("#desk-share textarea")).to_have_value("Cut from take-1.mp4 with: quieter music")

    assert agent.handled == ["research", "story", "script", "script", "footage", "edit", "edit"]

    # Coming back to the reel later lands on its last screen, and the reel is listed on the first.
    page.goto(f"{server}/?reel={reel_id}")
    expect(visible_step(page, "edit")).to_be_visible()
    expect(page.locator("#edit-version")).to_have_text("Version 2")
    page.goto(f"{server}/")
    page.locator("#start-own").click()
    expect(page.locator("#past-reel-list a")).to_have_attribute("href", f"/?reel={reel_id}")


def test_a_chat_that_refuses_to_start_shows_a_message_and_lets_the_creator_try_again(
    server: str, page: Page, dialogs: list[str], fake_chat: FakeChat, isolated_app: Path
) -> None:
    fake_chat.refuse_create = True
    page.goto(f"{server}/")
    page.locator("#start-own").click()
    page.locator("#app-grid .app-tile").click()
    page.locator("#next").click()
    assert wait_until(lambda: dialogs) and "couldn't start a chat" in dialogs[0]
    dialogs.clear()
    expect(visible_step(page, "app")).to_be_visible()
    expect(page.locator("#next")).to_be_enabled()
    assert list(reels.reels_dir(isolated_app).iterdir()) == []


def test_a_reel_id_that_does_not_exist_falls_back_to_the_welcome_screen(server: str, page: Page) -> None:
    page.goto(f"{server}/?reel=abcdefabcdef")
    expect(page.locator("#welcome")).to_be_visible()
    assert page.url.endswith("/")


@pytest.mark.parametrize(
    ("stage", "files", "lands_on"),
    [
        ("research", {"interview": {"questions": [{"q": "Q one", "help": "h", "guess": "g"}]}}, "interview"),
        ("story", {"interview": {"questions": [{"q": "Q one", "help": "h", "guess": "g"}]}, "tones": {"tones": [{"key": "a", "name": "A", "hook": "h"}], "directions": []}}, "tone"),
        ("script", {"tones": {"tones": [], "directions": []}, "script": SCRIPT}, "script"),
        ("footage", {"footage": {"clips": [], "privacy": []}}, "footage"),
        ("edit", {"reel": {"caption": "cap", "checks": []}}, "edit"),
    ],
)
def test_a_reel_opened_again_lands_on_the_screen_its_last_finished_stage_leads_to(
    server: str, page: Page, isolated_app: Path, stage: str, files: dict[str, Any], lands_on: str
) -> None:
    seed_reel(isolated_app, stage=stage, **files)
    page.goto(f"{server}/?reel={REEL}")
    expect(visible_step(page, lands_on)).to_be_visible()


def test_a_reel_with_a_take_already_filmed_opens_on_the_film_screen(server: str, page: Page, isolated_app: Path) -> None:
    folder = seed_reel(isolated_app, stage="footage", script=SCRIPT, footage={"clips": [], "privacy": []})
    reels.save_take(isolated_app, REEL, "video/mp4", io.BytesIO(b"take"))
    page.goto(f"{server}/?reel={REEL}")
    expect(visible_step(page, "film")).to_be_visible()
    expect(page.locator("#desk-takes .take-row.got")).to_have_count(1)
    expect(page.locator("#next")).to_be_enabled()
    assert (folder / "takes" / "take-1.mp4").exists()


# ---- the waiting screen when Studio stalls ----


def test_a_stalled_chat_shows_what_happened_and_try_again_asks_for_the_step_again(
    server: str, page: Page, fake_chat: FakeChat, agent: StandInAgent, isolated_app: Path
) -> None:
    folder = seed_reel(isolated_app, stage="footage", state="working", script=SCRIPT)
    status = reels.read_json(folder, "status.json")
    fake_chat.created.append({})
    stuck = "Studio's chat stopped before finishing this step. It has been asked to carry on 3 times. Try again, or open its chat to see what happened."
    reels.write_json(folder, "health.json", {
        "stage": "footage", "requested_at": status["requested_at"], "repairs": 3, "condition": "gave_up", "message": stuck,
        "last_activity_at": time.time() - 600,
        "history": [{"at": time.time() - 300, "text": "Studio's chat stopped before finishing this step. The app asked it to carry on (1 of 3)."}],
    })
    page.goto(f"{server}/?reel={REEL}")
    expect(page.locator("#pending-title")).to_have_text("Studio is filming Deck List")
    expect(page.locator("#pending-health")).to_be_visible()
    expect(page.locator("#pending-health-text")).to_have_text(stuck)
    expect(page.locator("#pending-health")).to_have_class(re.compile("stuck"))
    expect(page.locator("#pending-retry")).to_be_visible()
    expect(page.locator("#pending-live")).to_contain_text("Working on this for")
    expect(page.locator("#pending-live")).to_contain_text("last did something 10 min ago")
    expect(page.locator("#pending-history li")).to_have_count(1)
    expect(page.locator("#pending-history li")).to_contain_text("asked it to carry on (1 of 3)")
    expect(page.locator("#pending-list li")).to_have_count(5)
    assert fake_chat.messages == []

    page.locator("#pending-retry").click()
    expect(visible_step(page, "footage")).to_be_visible(timeout=STUDIO_WAIT)
    assert wait_until(lambda: [text for _, text in fake_chat.messages if "REEL STAGE: footage" in text])
    assert agent.handled == ["footage"]
    assert reels.read_json(folder, "health.json")["repairs"] == 0


def test_the_waiting_screen_tells_a_repair_in_progress_without_offering_try_again(server: str, page: Page, isolated_app: Path) -> None:
    folder = seed_reel(isolated_app, stage="edit", state="working", script=SCRIPT)
    status = reels.read_json(folder, "status.json")
    message = "Studio's chat went quiet for 31 minutes. The app restarted it and asked it to carry on (1 of 3)."
    reels.write_json(folder, "health.json", {"stage": "edit", "requested_at": status["requested_at"], "repairs": 1, "condition": "repairing", "message": message, "history": []})
    page.goto(f"{server}/?reel={REEL}")
    expect(page.locator("#pending-title")).to_have_text("Studio is editing your reel")
    expect(page.locator("#pending-health-text")).to_have_text(message)
    expect(page.locator("#pending-health")).not_to_have_class(re.compile("stuck"))
    expect(page.locator("#pending-retry")).to_be_hidden()


def test_a_message_about_an_earlier_request_is_not_shown_for_a_new_one(server: str, page: Page, isolated_app: Path) -> None:
    folder = seed_reel(isolated_app, stage="edit", state="working", script=SCRIPT)
    reels.write_json(folder, "health.json", {"stage": "edit", "requested_at": 1.0, "repairs": 3, "condition": "gave_up", "message": "old trouble", "history": []})
    page.goto(f"{server}/?reel={REEL}")
    expect(page.locator("#pending-title")).to_have_text("Studio is editing your reel")
    expect(page.locator("#pending-live")).to_contain_text("Working on this for")
    expect(page.locator("#pending-health")).to_be_hidden()
    expect(page.locator("#pending-retry")).to_be_hidden()


def test_a_stage_the_agent_reports_as_failed_keeps_the_waiting_screen_and_the_reason(server: str, page: Page, isolated_app: Path) -> None:
    folder = seed_reel(isolated_app, stage="footage", state="failed", script=SCRIPT)
    status = {**reels.read_json(folder, "status.json"), "error": "ran out of memory"}
    reels.write_json(folder, "status.json", status)
    reels.write_json(folder, "health.json", {"stage": "footage", "requested_at": status["requested_at"], "repairs": 1, "condition": "repairing",
                                             "message": "Studio's chat couldn't finish: ran out of memory. The app asked it to carry on (1 of 3).", "history": []})
    page.goto(f"{server}/?reel={REEL}")
    expect(page.locator("#pending-title")).to_have_text("Studio is filming Deck List")
    expect(page.locator("#pending-health-text")).to_contain_text("ran out of memory")


def test_the_waiting_screen_moves_on_by_itself_when_the_stage_finishes(server: str, page: Page, isolated_app: Path) -> None:
    folder = seed_reel(isolated_app, stage="script", state="working", tones={"tones": [], "directions": []})
    page.goto(f"{server}/?reel={REEL}")
    expect(page.locator("#pending-title")).to_have_text("Studio is writing your script")
    expect(page.locator("#skip-wait")).to_be_hidden()
    write_reel(folder, script=SCRIPT)
    reels.write_json(folder, "status.json", {"stage": "script", "state": "done"})
    expect(visible_step(page, "script")).to_be_visible(timeout=STUDIO_WAIT)
    expect(page.locator("#script-lines li")).to_have_count(2)


# ---- the phone page ----


def test_the_phone_page_without_a_reel_says_where_to_start(server: str, phone: Page) -> None:
    phone.goto(f"{server}/phone")
    expect(phone.locator("#phone-message")).to_contain_text("QR code on your computer")
    expect(phone.locator("#record-label")).to_be_hidden()
    phone.goto(f"{server}/phone?reel=abcdefabcdef")
    expect(phone.locator("#phone-message")).to_contain_text("couldn't be found")


def test_the_phone_page_waits_for_a_script_and_then_shows_it_in_order(server: str, phone: Page, isolated_app: Path) -> None:
    seed_reel(isolated_app, stage="script", state="working")
    phone.goto(f"{server}/phone?reel={REEL}")
    expect(phone.locator("#phone-title")).to_have_text("Deck List reel")
    expect(phone.locator("#phone-message")).to_contain_text("hasn't written your script yet")
    expect(phone.locator("#phone-takes")).to_be_hidden()
    expect(phone.locator("#phone-ready")).to_be_hidden()
    expect(phone.locator("#record-text")).to_have_text("Record your take")
    seed_reel(isolated_app, stage="script", script=SCRIPT)
    phone.goto(f"{server}/phone?reel={REEL}")
    expect(phone.locator("#prompter p")).to_have_text(["1First line to read.", "2Second line to read."])
    expect(phone.locator("#phone-message")).to_be_hidden()


UPLOAD_SPY = """
(() => {
  window.__progress = [];
  window.__texts = [];
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (body) {
    this.upload.addEventListener("progress", (e) => window.__progress.push(Math.round((e.loaded / e.total) * 100)));
    // Hold the upload for a moment so the screen while sending can be seen.
    setTimeout(() => send.call(this, body), 600);
  };
})();
"""


def test_a_take_is_sent_with_progress_and_listed_as_the_one_in_use(server: str, phone: Page, isolated_app: Path) -> None:
    seed_reel(isolated_app, stage="script", script=SCRIPT)
    phone.add_init_script(UPLOAD_SPY)
    phone.goto(f"{server}/phone?reel={REEL}")
    expect(phone.locator("#prompter p")).to_have_count(2)
    video: FilePayload = {"name": "clip.mov", "mimeType": "video/quicktime", "buffer": b"\x00" * (6 * 1024 * 1024)}
    phone.locator("#record-input").set_input_files(video)
    expect(phone.locator("#upload-progress")).to_be_visible()
    expect(phone.locator("#upload-text")).to_have_text("Sending your take to Studio...")
    expect(phone.locator("#phone-takes .phone-take")).to_have_count(1, timeout=15_000)
    expect(phone.locator("#upload-progress")).to_be_hidden()
    assert phone.evaluate("window.__progress.at(-1)") == 100
    expect(phone.locator(".phone-take .badge")).to_have_text("Using this one")
    expect(phone.locator(".phone-take .sent")).to_have_text("Sent to Studio")
    expect(phone.locator("#record-text")).to_have_text("Record another take")
    expect(phone.locator(".phone-take video")).to_have_attribute("src", f"/api/reels/{REEL}/files/takes/take-1.mov")
    stored = reels.reels_dir(isolated_app) / REEL / "takes" / "take-1.mov"
    assert stored.stat().st_size == 6 * 1024 * 1024
    assert reels.read_json(reels.reels_dir(isolated_app) / REEL, "choice.json") == {"take": "take-1.mov"}


def test_a_take_that_cannot_be_sent_says_so_and_nothing_is_kept(server: str, phone: Page, isolated_app: Path) -> None:
    seed_reel(isolated_app, stage="script", script=SCRIPT)
    phone.goto(f"{server}/phone?reel={REEL}")
    phone.locator("#record-input").set_input_files(EMPTY_TAKE)
    expect(phone.locator("#upload-text")).to_have_text("Couldn't send that take. Check your connection and record it again.")
    expect(phone.locator("#phone-takes")).to_be_hidden()
    assert reels.list_takes(reels.reels_dir(isolated_app) / REEL) == []
    phone.route("**/takes", lambda route: route.abort())
    phone.locator("#record-input").set_input_files(TAKE)
    expect(phone.locator("#upload-text")).to_have_text("Couldn't send that take. Check your connection and record it again.")
    assert reels.list_takes(reels.reels_dir(isolated_app) / REEL) == []


def test_any_take_can_be_chosen_again_from_the_phone(server: str, phone: Page, isolated_app: Path) -> None:
    folder = seed_reel(isolated_app, stage="script", script=SCRIPT)
    reels.save_take(isolated_app, REEL, "video/mp4", io.BytesIO(b"one"))
    reels.save_take(isolated_app, REEL, "video/mp4", io.BytesIO(b"two"))
    phone.goto(f"{server}/phone?reel={REEL}")
    cards = phone.locator(".phone-take")
    expect(cards).to_have_count(2)
    expect(cards.first.locator("b")).to_have_text("Take 2")
    expect(cards.first.locator(".badge")).to_have_text("Using this one")
    expect(cards.nth(1).locator("b")).to_have_text("Take 1")
    cards.nth(1).get_by_role("button", name="Use this take").click()
    expect(phone.locator(".phone-take.chosen b")).to_have_text("Take 1")
    expect(phone.locator(".phone-take .badge")).to_have_count(1)
    assert reels.read_json(folder, "choice.json") == {"take": "take-1.mp4"}


def test_takes_being_watched_are_not_reset_while_the_page_checks_for_news(server: str, phone: Page, isolated_app: Path) -> None:
    seed_reel(isolated_app, stage="script", script=SCRIPT)
    reels.save_take(isolated_app, REEL, "video/mp4", io.BytesIO(b"one"))
    phone.goto(f"{server}/phone?reel={REEL}")
    expect(phone.locator(".phone-take video")).to_have_count(1)
    phone.evaluate("document.querySelector('.phone-take video').dataset.mark = 'kept'")
    # The page checks every 5 seconds; wait out a check.
    phone.wait_for_timeout(5600)
    assert phone.evaluate("document.querySelector('.phone-take video')?.dataset.mark") == "kept"


def test_the_finished_reel_appears_on_the_phone_only_once_the_edit_is_done(server: str, phone: Page, isolated_app: Path) -> None:
    folder = seed_reel(isolated_app, stage="edit", state="working", script=SCRIPT)
    (folder / "reel.mp4").write_bytes(b"half written")
    write_reel(folder, reel={"caption": "Final caption", "checks": []})
    phone.goto(f"{server}/phone?reel={REEL}")
    expect(phone.locator("#prompter p")).to_have_count(2)
    expect(phone.locator("#phone-ready")).to_be_hidden()
    reels.write_json(folder, "status.json", {"stage": "edit", "state": "done"})
    expect(phone.locator("#phone-ready")).to_be_visible(timeout=10_000)
    expect(phone.locator("#ready-video")).to_have_attribute("src", f"/api/reels/{REEL}/files/reel.mp4?v=1")
    expect(phone.locator("#phone-share textarea")).to_have_value("Final caption")
    expect(phone.locator('#phone-share a[data-role="save"]')).to_have_attribute("download", "deck-list-reel.mp4")
    expect(phone.locator('#phone-share a[data-role="save"]')).to_have_attribute("href", f"/api/reels/{REEL}/files/reel.mp4?v=1")
    expect(phone.locator("#phone-share .platform")).to_have_count(5)


def test_a_reel_that_is_already_finished_shows_straight_away_and_a_new_cut_replaces_it(server: str, phone: Page, isolated_app: Path) -> None:
    folder = seed_reel(isolated_app, stage="edit", script=SCRIPT)
    (folder / "reel.mp4").write_bytes(b"cut one")
    write_reel(folder, reel={"caption": "One", "checks": []})
    phone.goto(f"{server}/phone?reel={REEL}")
    expect(phone.locator("#ready-video")).to_have_attribute("src", f"/api/reels/{REEL}/files/reel.mp4?v=1")
    state = reels.read_json(folder, "state.json")
    reels.write_json(folder, "state.json", {**state, "cuts": 2})
    write_reel(folder, reel={"caption": "Two", "checks": []})
    expect(phone.locator("#ready-video")).to_have_attribute("src", f"/api/reels/{REEL}/files/reel.mp4?v=2", timeout=10_000)


def test_a_caption_with_markup_in_it_is_shown_as_text_not_run(server: str, page: Page, isolated_app: Path) -> None:
    caption = '</textarea><img src=x onerror="window.pwned=1"> & more'
    folder = seed_reel(isolated_app, stage="edit", script=SCRIPT)
    (folder / "reel.mp4").write_bytes(b"cut")
    write_reel(folder, reel={"caption": caption, "checks": ["<b>bold</b> check"], "notes": ["a <i>note</i>"]})
    page.goto(f"{server}/?reel={REEL}")
    expect(visible_step(page, "edit")).to_be_visible()
    expect(page.locator("#desk-share textarea")).to_have_value(caption)
    expect(page.locator("#reel-checks li")).to_have_text("<b>bold</b> check")
    expect(page.locator("#reel-notes li")).to_have_text("a <i>note</i>")
    assert page.evaluate("window.pwned") is None
