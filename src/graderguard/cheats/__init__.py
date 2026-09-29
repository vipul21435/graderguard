"""Built-in cheat plugins and the registry the audit iterates over."""

from __future__ import annotations

from graderguard.cheats.base import (
    APPLICABLE,
    Applicability,
    Cheat,
    NotApplicableError,
    Severity,
)
from graderguard.cheats.hardcode import HardcodeVisibleExpected
from graderguard.cheats.pytest_harness import ConftestForcePass, GutVisibleTests
from graderguard.cheats.stubs import EmptyOutput, ExitZeroStub

__all__ = [
    "APPLICABLE",
    "Applicability",
    "Cheat",
    "NotApplicableError",
    "Severity",
    "all_cheats",
    "get_cheat",
]


def all_cheats() -> list[Cheat]:
    """Fresh instances of every built-in cheat, in report order."""
    return [
        ExitZeroStub(),
        EmptyOutput(),
        HardcodeVisibleExpected(),
        ConftestForcePass(),
        GutVisibleTests(),
    ]


def get_cheat(name: str) -> Cheat:
    """Look a built-in cheat up by name; raises KeyError for unknown names."""
    for cheat in all_cheats():
        if cheat.name == name:
            return cheat
    raise KeyError(name)
