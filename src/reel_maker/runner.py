"""Walks you through making a short vertical reel about an app you built in Studio: interview, script preview, filming your take on your phone, and the edit..

Services run from /home/user/workspace (the repo root). Conventions:

- Persistent state (anything written and read across runs -- cursors,
  caches, snapshots, user records): read and write it under ``DATA_DIR``
  (defined below), never a hardcoded ``data/.apps/reel-maker/`` at the
  call site. ``DATA_DIR`` defaults to ``data/.apps/reel-maker/`` but
  honors the ``REEL_MAKER_DATA_DIR`` env var, so an editing agent can point a
  throwaway instance at a *copy* of the data instead of the live store
  (see the update-app skill). Do NOT use ``Path(__file__)``-based
  paths for state -- the bug to avoid is one process writing to
  ``/home/user/workspace/data/.apps/...`` while another reads from
  ``/home/user/workspace/system/apps/<pkg>/data/...``.
- Static assets shipped alongside this file (templates, default
  configs, bundled JSON): ``Path(__file__).parent / "assets/..."`` is
  fine and is the right pattern.
- Listen port: bind ``PORT`` (defined below), which defaults to this
  app's assigned port but honors the ``REEL_MAKER_PORT`` env var, so
  an editing agent can boot a throwaway instance on a *spare* port
  alongside the live one (see the update-app skill). Never hardcode
  the port at the ``run_simple`` call.

This is a synchronous Flask app served by the threaded Werkzeug server.
The app owns its own browser origin (the forwarder routes
``http://reel-maker.<workspace-host>/`` straight to this port), so it serves
at ``/`` and root-absolute URLs, cookies, and service workers all work
unmodified -- nothing rewrites anything. Use ``flask_sock`` if you need
WebSockets.
"""

import base64
import hashlib
import html
import io
import os
import time
import tomllib
from pathlib import Path
from typing import Any

from app_schema.api_schema import (
    DEFAULT_API_SCHEMA_PATH,
    RouteModels,
    RouteTable,
    SchemalessRoute,
    register_api_schema_route,
)
import requests
import segno
from app_schema.routes import error_response, model_response, parse_request_body
from flask import Flask, Response, abort, request, send_file
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import setup_logging
from loguru import logger
from pydantic import Field
from werkzeug.serving import run_simple

from reel_maker import reels, watchdog

# Persistent state for this app lives under DATA_DIR. It defaults to
# ``data/.apps/reel-maker/`` but is overridable via the ``REEL_MAKER_DATA_DIR`` env var
# so a throwaway instance can run against a *copy* of the data while editing --
# see the update-app skill. Always read/write state through DATA_DIR;
# never hardcode ``data/.apps/reel-maker/`` at a call site, or the override is
# bypassed. A writing call site should ``DATA_DIR.mkdir(parents=True,
# exist_ok=True)`` before writing.
DATA_DIR = Path(os.environ.get("REEL_MAKER_DATA_DIR", "data/.apps/reel-maker"))

# Listen port. Defaults to this app's assigned port but is overridable via
# the ``REEL_MAKER_PORT`` env var so an editing agent can boot a throwaway
# instance on a spare port next to the live one (see the update-app skill).
# Never hardcode the port at the ``run_simple`` call, or the override is bypassed.
PORT = int(os.environ.get("REEL_MAKER_PORT", "8100"))

# The pages, scripts and styles shipped with the app.
ASSETS_DIR = Path(__file__).parent / "assets"
ICON_PATH = Path(__file__).parent.parent.parent / "icon.svg"
APP_NAME = "reel-maker"
# The workspace shell, which knows each app's address on the public domain (the one a phone can open).
SHELL_URL = os.environ.get("MINDS_WORKSPACE_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
PUBLIC_ADDRESS_CACHE_SECONDS = 60
PUBLIC_ADDRESS_TIMEOUT_SECONDS = 3
# The longest text a QR code is made for: a link, which stays far below what a QR code can hold.
MAX_QR_TEXT_LENGTH = 1500
# The example run's videos (Bowei's Deck List reel), shipped with the app under examples/.
EXAMPLE_MEDIA_DIR = Path(__file__).resolve().parents[2] / "examples"
EXAMPLE_MEDIA_FILES = {
    "deck-list-reel/deck-list-reel.mp4",
    "deck-list-reel/shots/2-first-prompt.mp4",
    "deck-list-reel/shots/3-scryfall-count.mp4",
    "deck-list-reel/shots/4-second-prompt.mp4",
    "deck-list-reel/shots/5-search.mp4",
    "deck-list-reel/shots/6-drag-to-tag.mp4",
    "deck-list-reel/shots/8-end-card.mp4",
}

# The browser-side modules the workspace shell builds and every app serves from
# its own origin: the app contract (how a page talks to the shell framing it) and
# the element context menu (the right-click menu whose last rows hand the
# clicked element to a chat). A module import is a fetch without cookies, which
# the forwarder refuses across origins, so they are served here rather than from
# the shell. Relative to the repo root the service runs from, like DATA_DIR.
SHELL_STATIC_MODULES_DIR = Path("system/apps/system_interface/imbue/system_interface/static/_static")
SHELL_STATIC_MODULE_NAMES = ('app_contract.js', 'context_menu.js')

# The script every page serves (keep it on every page): it connects the page to
# the shell, reports where the page is on the handshake so the shell can reopen
# this app's window at the same place, and installs the element context menu.
# A page visited outside the shell runs it harmlessly: nothing arrives, and the
# menu's Explain and Modify rows grey out.
SHELL_PAGE_SCRIPT_BODY = """
  import { connectToShell } from "/_static/app_contract.js";
  import { installElementContextMenu } from "/_static/context_menu.js";
  let handshake = null;
  const connection = connectToShell({
    onHandshake: (received) => {
      handshake = received;
      connection.location(location.pathname + location.search, document.title);
    },
  });
  installElementContextMenu({ connection, handshake: () => handshake });
"""
SHELL_PAGE_SCRIPT = f'<script type="module">{SHELL_PAGE_SCRIPT_BODY}</script>'


def inline_script_source(body: str) -> str:
    """The Content-Security-Policy source admitting one inline <script> whose body is exactly ``body``."""
    return "'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'"


# Every HTML page is served under this policy (the app is reachable from the
# internet once the workspace is shared): scripts only from this origin plus the
# inline blocks listed here by hash, fetches, sockets and images only from this
# origin, inline styles, frames of any http(s) page, no plugins. Anything else a
# page pulls in (a CDN script, Google Fonts, an image hosted elsewhere, a
# third-party API called from the browser) is blocked until its origin is added
# to the matching directive; a new inline <script> needs its
# ``inline_script_source`` added.
# The browser posts every block to ``/_csp-report`` below, which logs it on
# stderr (the supervisor log), so a blocked resource is never silent; the
# ``'report-sample'`` makes the browser include where a blocked inline script
# is and how it starts, since the report otherwise names it only as "inline".
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    f"script-src 'self' 'report-sample' {inline_script_source(SHELL_PAGE_SCRIPT_BODY)}; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; frame-src http: https:; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; "
    "report-uri /_csp-report"
)
BROWSER_EXTENSION_SCHEMES = ("chrome-extension:", "moz-extension:", "safari-web-extension:")


class HealthResponse(FrozenModel):
    """What the health probe answers."""

    status: str = Field(description="Always 'ok'")


# What every route exchanges, which the app's API document publishes and every parse and answer
# is checked against (build-app skill, "The app describes its own API"): a route that reads or
# answers JSON names its pydantic models here and uses ``parse_request_body`` and
# ``model_response``; a page, a file or a stream is declared schemaless with the reason.
class AppChoice(FrozenModel):
    """An app the creator built, which a reel can be about."""

    name: str = Field(description="The app's registered name")
    display_name: str = Field(description="What the creator calls the app")
    description: str = Field(description="One line on what the app is for")
    icon: str = Field(description="The app's icon as an SVG document")


class AppListResponse(FrozenModel):
    """The apps a reel can be about."""

    apps: list[AppChoice] = Field(description="The creator's own apps, in the launcher's order")


class CreateReelRequest(FrozenModel):
    """Start a reel about one app."""

    app: str = Field(description="The registered name of the app the reel is about")


class ReelResponse(FrozenModel):
    """Everything about one reel: the app's record, Studio's outputs so far, the takes."""

    reel: dict[str, Any] = Field(description="The reel's files by name (see docs/agent-contract.md), its takes and id")


class ReelListResponse(FrozenModel):
    """The reels made in this workspace, newest first."""

    reels: list[dict[str, Any]] = Field(description="Each reel's id, app, creation time and chat id")


class AdvanceRequest(FrozenModel):
    """Ask Studio to do the next stage of a reel, with the creator's inputs for it."""

    stage: str = Field(description="story, script, footage or edit; script and edit can carry a change request")
    inputs: dict[str, Any] = Field(
        default_factory=dict, description="Files to write first, by name: answers, choice or change"
    )


class ChooseTakeRequest(FrozenModel):
    """Pick which take the reel is cut from."""

    take: str = Field(description="The take's file name, as listed in the reel's takes")


class TakeResponse(FrozenModel):
    """A take stored from the phone."""

    name: str = Field(description="The take's file name")
    number: int = Field(description="Which take this is, counting from 1")
    bytes: int = Field(description="Its size")


ROUTE_TABLE: RouteTable = {
    ("GET", "/api/apps"): RouteModels(response_model=AppListResponse),
    ("GET", "/api/reels"): RouteModels(response_model=ReelListResponse),
    ("POST", "/api/reels"): RouteModels(request_model=CreateReelRequest, response_model=ReelResponse, success_status=201),
    ("GET", "/api/reels/{reel_id}"): RouteModels(response_model=ReelResponse),
    ("POST", "/api/reels/{reel_id}/advance"): RouteModels(request_model=AdvanceRequest, response_model=ReelResponse),
    ("POST", "/api/reels/{reel_id}/takes"): RouteModels(response_model=TakeResponse, success_status=201),
    ("POST", "/api/reels/{reel_id}/retry"): RouteModels(response_model=ReelResponse),
    ("POST", "/api/reels/{reel_id}/choose-take"): RouteModels(request_model=ChooseTakeRequest, response_model=ReelResponse),
    ("GET", "/api/reels/{reel_id}/files/{name}"): SchemalessRoute(reason="a video from the reel: footage, a take or the reel"),
    ("GET", "/"): SchemalessRoute(reason="the app's page"),
    ("GET", "/phone"): SchemalessRoute(reason="the phone page: the script and the record button"),
    ("GET", "/_assets/{basename}"): SchemalessRoute(reason="a script or style the pages load"),
    ("GET", "/icon.svg"): SchemalessRoute(reason="the app's icon"),
    ("GET", "/qr.svg"): SchemalessRoute(reason="a QR code image"),
    ("GET", "/_media/{name}"): SchemalessRoute(reason="a sample video"),
    ("GET", "/_static/{basename}"): SchemalessRoute(reason="a browser-side module the shell builds"),
    ("GET", "/health"): RouteModels(response_model=HealthResponse),
    ("POST", "/_csp-report"): SchemalessRoute(reason="the browser's report of what the page's policy blocked"),
}

app = Flask("reel_maker", static_folder=None)
# The app describes its own API: an OpenAPI document of every route below, served at the
# manifest's api_schema_path.
register_api_schema_route(
    app, DEFAULT_API_SCHEMA_PATH, title='Reel maker', description='Walks you through making a short vertical reel about an app you built in Studio: interview, script preview, filming your take on your phone, and the edit.', route_table=ROUTE_TABLE
)


@app.after_request
def add_content_security_policy(response: Response) -> Response:
    if response.mimetype == "text/html":
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    return response


# When the shell was last asked (0 for never) and what it answered.
_public_address_cache: dict[str, float | str | None] = {"asked_at": 0.0, "address": None, "chat_address": None}


def public_address() -> str | None:
    """This app's address on the workspace's public domain (what a phone can open), else None.

    It answers None while the workspace is not shared. An unreachable shell is not remembered, so the next page
    load asks again.
    """
    asked_at = float(_public_address_cache["asked_at"] or 0.0)
    remembered = _public_address_cache["address"]
    if asked_at > 0 and time.monotonic() - asked_at < PUBLIC_ADDRESS_CACHE_SECONDS:
        return str(remembered) if remembered else None
    try:
        answer = requests.get(f"{SHELL_URL}/api/inventory", timeout=PUBLIC_ADDRESS_TIMEOUT_SECONDS)
        answer.raise_for_status()
        entries = answer.json()["apps"]
    except (requests.RequestException, ValueError, KeyError):
        return None
    found = next((entry.get("share_url") for entry in entries if entry.get("name") == APP_NAME), None)
    _public_address_cache["asked_at"] = time.monotonic()
    _public_address_cache["address"] = found
    _public_address_cache["chat_address"] = next(
        (entry.get("share_url") for entry in entries if entry.get("name") == "chat"), None
    )
    return found


def render_page(basename: str) -> Response:
    page = (ASSETS_DIR / basename).read_text().replace("__SHELL_PAGE_SCRIPT__", SHELL_PAGE_SCRIPT)
    address = html.escape(public_address() or "", quote=True)
    chat_address = html.escape(str(_public_address_cache["chat_address"] or ""), quote=True)
    page = page.replace("<body ", f'<body data-public-address="{address}" data-chat-address="{chat_address}" ', 1)
    return Response(page, mimetype="text/html")


@app.route("/")
def index() -> Response:
    """The walkthrough: pick an app, answer questions, see the script, film a take, watch the reel."""
    return render_page("wizard.html")


@app.route("/phone")
def phone() -> Response:
    """The phone page: the script to read and a big button that opens the phone's camera."""
    return render_page("phone.html")


ASSET_TYPES = {
    "style.css": "text/css",
    "wizard.js": "text/javascript",
    "phone.js": "text/javascript",
    "share.js": "text/javascript",
}


@app.route("/_assets/<basename>")
def asset(basename: str) -> Response:
    """A script or style the pages load."""
    if basename not in ASSET_TYPES:
        abort(404)
    return send_file((ASSETS_DIR / basename).absolute(), mimetype=ASSET_TYPES[basename], max_age=0)


@app.route("/icon.svg")
def icon() -> Response:
    """The app's icon."""
    return send_file(ICON_PATH.absolute(), mimetype="image/svg+xml")


@app.route("/qr.svg")
def qr_code() -> Response:
    """A QR code image for the text given as ``data``."""
    text = request.args.get("data", "")
    if not text or len(text) > MAX_QR_TEXT_LENGTH:
        return error_response("data must be between 1 and %d characters" % MAX_QR_TEXT_LENGTH, 400)
    buffer = io.BytesIO()
    segno.make(text, error="m").save(buffer, kind="svg", scale=8, border=2, dark="#111111", light="#ffffff", xmldecl=False)
    return Response(buffer.getvalue(), mimetype="image/svg+xml")


@app.route("/_media/<path:name>")
def media(name: str) -> Response:
    """A sample video from the Deck List reel."""
    if name not in EXAMPLE_MEDIA_FILES:
        abort(404)
    return send_file((EXAMPLE_MEDIA_DIR / name).absolute(), mimetype="video/mp4", conditional=True)


APPS_REGISTRY = Path(os.environ.get("REEL_MAKER_APPS_FILE", "data/.state/apps.toml"))


def creator_apps() -> list[AppChoice]:
    """The apps the creator built (the user-made ones in the workspace's registry), this one left out."""
    try:
        registry = tomllib.loads(APPS_REGISTRY.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return []
    entries = registry.get("apps") or registry.get("app") or []
    return [
        AppChoice(
            name=str(entry.get("name", "")),
            display_name=str(entry.get("display_name") or entry.get("name", "")),
            description=str(entry.get("description", "")),
            icon=str(entry.get("icon", "")),
        )
        for entry in entries
        if entry.get("priority") == "user" and not entry.get("internal") and entry.get("name") != APP_NAME
    ]


def reel_answer(reel_id: str, status: int = 200) -> Response:
    return model_response(ReelResponse(reel=reels.reel_snapshot(DATA_DIR, reel_id)), status)


@app.route("/api/apps")
def list_apps() -> Response:
    """The apps a reel can be about: the ones the creator built in this workspace."""
    return model_response(AppListResponse(apps=creator_apps()))


@app.route("/api/reels", methods=["GET"])
def list_reels() -> Response:
    """The reels made in this workspace, newest first."""
    return model_response(ReelListResponse(reels=reels.list_reels(DATA_DIR)))


@app.route("/api/reels", methods=["POST"])
def create_reel() -> Response:
    """Start a reel about an app: Studio opens a chat for it and starts reading up on the app."""
    body = parse_request_body(CreateReelRequest)
    chosen = next((choice for choice in creator_apps() if choice.name == body.app), None)
    if chosen is None:
        return error_response("That app isn't one you built in this workspace.", 400)
    try:
        reel_id = reels.create_reel(DATA_DIR, chosen.model_dump(exclude={"icon"}), reels.start_agent_through_chat_app)
    except reels.ReelError as error:
        return error_response(str(error), 502)
    return reel_answer(reel_id, 201)


@app.route("/api/reels/<reel_id>")
def get_reel(reel_id: str) -> Response:
    """One reel: Studio's outputs so far, what it is doing now, and the takes."""
    try:
        return reel_answer(reel_id)
    except reels.ReelError as error:
        return error_response(str(error), 404)


@app.route("/api/reels/<reel_id>/advance", methods=["POST"])
def advance_reel(reel_id: str) -> Response:
    """Save the creator's inputs for the next stage and ask Studio to do it."""
    body = parse_request_body(AdvanceRequest)
    try:
        reels.advance(DATA_DIR, reel_id, body.stage, body.inputs, reels.send_through_chat_app)
        return reel_answer(reel_id)
    except reels.ReelError as error:
        return error_response(str(error), 409)


@app.route("/api/reels/<reel_id>/takes", methods=["POST"])
def upload_take(reel_id: str) -> Response:
    """Store a take recorded on the phone; the newest take is the one the reel is cut from until another is picked."""
    # The body is the video itself, streamed to disk: a multipart form would be spooled through /tmp first.
    if not (request.mimetype or "").startswith("video/"):
        return error_response("Send the video itself as the body, with its video content type.", 400)
    try:
        saved = reels.save_take(DATA_DIR, reel_id, request.mimetype, request.stream)
    except reels.ReelError as error:
        return error_response(str(error), 400)
    return model_response(TakeResponse(**saved), 201)


@app.route("/api/reels/<reel_id>/retry", methods=["POST"])
def retry_reel(reel_id: str) -> Response:
    """Ask Studio to do the current step again, after it stopped or gave up."""
    try:
        watchdog.retry(DATA_DIR, reel_id, reels.send_through_chat_app)
        return reel_answer(reel_id)
    except reels.ReelError as error:
        return error_response(str(error), 409)


@app.route("/api/reels/<reel_id>/choose-take", methods=["POST"])
def choose_take(reel_id: str) -> Response:
    """Pick which take the reel is cut from."""
    body = parse_request_body(ChooseTakeRequest)
    try:
        reels.choose_take(DATA_DIR, reel_id, body.take)
        return reel_answer(reel_id)
    except reels.ReelError as error:
        return error_response(str(error), 400)


@app.route("/api/reels/<reel_id>/files/<path:name>")
def reel_file(reel_id: str, name: str) -> Response:
    """A video from the reel's folder: a footage clip, a take, or the finished reel."""
    try:
        folder = reels.reel_dir(DATA_DIR, reel_id).resolve()
    except reels.ReelError:
        abort(404)
    target = (folder / name).resolve()
    if folder not in target.parents or target.suffix.lower() not in (".mp4", ".mov", ".webm", ".m4v", ".3gp"):
        abort(404)
    if not target.is_file():
        abort(404)
    download = request.args.get("download") == "1"
    return send_file(target, conditional=True, as_attachment=download, download_name=target.name)


@app.route("/_csp-report", methods=["POST"])
def content_security_policy_report() -> Response:
    """Where the browser reports what the page's security policy blocked."""
    body = request.get_json(force=True, silent=True)
    report = body.get("csp-report") if isinstance(body, dict) else None
    if not isinstance(report, dict):
        return Response(status=204)
    blocked, page, source, directive, line, sample = (
        str(report.get(key, ""))[:500]
        for key in ("blocked-uri", "document-uri", "source-file", "effective-directive", "line-number", "script-sample")
    )
    # A block caused by a browser extension is the policy doing its job and is not logged.
    if blocked.startswith(BROWSER_EXTENSION_SCHEMES) or source.startswith(BROWSER_EXTENSION_SCHEMES):
        return Response(status=204)
    # An inline script or style is reported as "inline": say where it is and how it starts instead.
    where = f" at {source}:{line}" if source and line else ""
    starting = f" starting {sample!r}" if sample else ""
    remedy = (
        "add its inline_script_source to CONTENT_SECURITY_POLICY if the page needs it"
        if blocked == "inline"
        else "add its origin to CONTENT_SECURITY_POLICY if the page needs it"
    )
    logger.error(
        "Content-Security-Policy blocked {!r} on {!r} ({}){}{}; {}", blocked, page, directive, where, starting, remedy
    )
    return Response(status=204)


@app.route("/_static/<basename>")
def shell_module(basename: str) -> Response:
    """One of the two browser-side modules the workspace shell builds and every app serves from its own origin."""
    # The two shell-built modules and nothing else: a name that is not one of
    # them is a 404, so this route can never read outside that directory.
    if basename not in SHELL_STATIC_MODULE_NAMES:
        abort(404)
    module_path = SHELL_STATIC_MODULES_DIR / basename
    if not module_path.is_file():
        abort(404)
    # Flask resolves a relative path against the app's own directory, not the cwd.
    return send_file(module_path.absolute(), mimetype="text/javascript")


@app.route("/health")
def health() -> Response:
    """Whether the app is up."""
    return model_response(HealthResponse(status="ok"))


def main() -> None:
    setup_logging()
    # Reels keep working while no window is open, so their chats are watched from the app itself.
    watchdog.start(DATA_DIR)
    run_simple(
        "127.0.0.1", PORT, app, threaded=True, use_reloader=False, use_debugger=False
    )


if __name__ == "__main__":
    main()
