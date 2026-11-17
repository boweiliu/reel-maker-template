from pathlib import Path

from imbue.imbue_common.ratchet_testing import standard_ratchet_checks as rc
from imbue.imbue_common.ratchet_testing.ratchets import check_no_type_errors
from inline_snapshot import snapshot

_DIR = Path(__file__).parent
# The app's own code. The repo root also holds the install script and Lauren's reel skill (shipped unchanged), which
# these checks are not about.
_CODE_DIR = _DIR / "src"


# Code safety


def test_prevent_todos() -> None:
    rc.check_todos(_CODE_DIR, snapshot(0))


def test_prevent_exec_usage() -> None:
    rc.check_exec(_CODE_DIR, snapshot(0))


def test_prevent_eval_usage() -> None:
    rc.check_eval(_CODE_DIR, snapshot(0))


def test_prevent_while_true() -> None:
    rc.check_while_true(_CODE_DIR, snapshot(0))


def test_prevent_time_sleep() -> None:
    rc.check_time_sleep(_CODE_DIR, snapshot(0))


def test_prevent_global_keyword() -> None:
    rc.check_global_keyword(_CODE_DIR, snapshot(0))


def test_prevent_bare_print() -> None:
    rc.check_bare_print(_CODE_DIR, snapshot(0))


# Exception handling


def test_prevent_bare_except() -> None:
    rc.check_bare_except(_CODE_DIR, snapshot(0))


def test_prevent_broad_exception_catch() -> None:
    rc.check_broad_exception_catch(_CODE_DIR, snapshot(0))


def test_prevent_builtin_exception_raises() -> None:
    rc.check_builtin_exception_raises(_CODE_DIR, snapshot(0))


# Import style


def test_prevent_inline_imports() -> None:
    rc.check_inline_imports(_CODE_DIR, snapshot(0))


def test_prevent_relative_imports() -> None:
    rc.check_relative_imports(_CODE_DIR, snapshot(0))


# Banned libraries and patterns


def test_prevent_asyncio_import() -> None:
    rc.check_asyncio_import(_CODE_DIR, snapshot(0))


def test_prevent_dataclasses_import() -> None:
    rc.check_dataclasses_import(_CODE_DIR, snapshot(0))


# Types


def test_no_type_errors() -> None:
    check_no_type_errors(_DIR)
