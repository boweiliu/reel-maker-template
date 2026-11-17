"""Install Reel maker on a Studio workspace from its clone, or update it in place.

Run from the workspace root (/home/user/workspace), with the repo cloned at ``.external_worktrees/reel-maker``:

    python3 .external_worktrees/reel-maker/deploy/install.py            # install or update, start, check
    python3 .external_worktrees/reel-maker/deploy/install.py --dry-run  # say what it would do

Syncs the app's own venv from its lock, writes the supervisord program entry
``system/supervisord.conf.d/reel-maker.conf`` from ``workspace/supervisord/reel-maker.conf``, has supervisord pick it
up (or restarts it when the entry is unchanged, which is what loads new code), and waits for ``/health``.

Standard library only, so it runs under a plain ``python3`` before anything is installed.
"""

import argparse
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CLONE = Path(__file__).resolve().parents[1]
PROGRAM = "reel-maker"
CONF_SOURCE = CLONE / "workspace" / "supervisord" / f"{PROGRAM}.conf"
CONF_TARGET = Path("system/supervisord.conf.d") / f"{PROGRAM}.conf"
HEALTH_URL = "http://127.0.0.1:8100/health"
HEALTH_WAIT_SECONDS = 90


def run(command: list[str], dry_run: bool) -> None:
    print("+ " + " ".join(command), flush=True)
    if not dry_run:
        subprocess.run(command, check=True)


def healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as response:
            return response.status == 200
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print the steps, change nothing")
    args = parser.parse_args(argv)

    if not Path("system/supervisord.conf.d").is_dir():
        print("Run this from the workspace root (/home/user/workspace).", file=sys.stderr)
        return 2
    if shutil.which("uv") is None:
        print("uv is not on PATH.", file=sys.stderr)
        return 2

    run(["python3", "system/scripts/workspace_bare_scripts/venv_links.py", "ensure-project", str(CLONE)], args.dry_run)
    run(["uv", "sync", "--locked", "--project", str(CLONE)], args.dry_run)

    wanted = CONF_SOURCE.read_text()
    current = CONF_TARGET.read_text() if CONF_TARGET.exists() else None
    if current == wanted:
        print(f"{CONF_TARGET} is already up to date")
    else:
        print(f"{'would write' if args.dry_run else 'writing'} {CONF_TARGET}")
        if not args.dry_run:
            CONF_TARGET.write_text(wanted)

    run(["supervisorctl", "reread"], args.dry_run)
    run(["supervisorctl", "update"], args.dry_run)
    if current == wanted:
        run(["supervisorctl", "restart", PROGRAM], args.dry_run)

    if args.dry_run:
        return 0
    deadline = time.time() + HEALTH_WAIT_SECONDS
    while time.time() < deadline:
        if healthy():
            print(f"{PROGRAM} is answering at {HEALTH_URL}")
            return 0
        time.sleep(2)
    print(
        f"{PROGRAM} did not answer within {HEALTH_WAIT_SECONDS}s; read /var/log/supervisor/{PROGRAM}-stderr.log",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
