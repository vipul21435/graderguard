"""Local sandbox: isolated workspace copies and bounded command execution.

Every attempt gets a fresh temporary directory, so nothing an attempt does can touch the task
directory or leak into the next attempt. Commands run through ``/bin/sh -c`` in their own
process group with a scrubbed environment, a wall-clock timeout (the whole group is killed when
it expires) and, on Linux, an address-space limit. This is isolation for correctness, not a
security boundary: the grader and the cheats run as the current user.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from graderguard.task import Task

OUTPUT_TAIL_CHARS = 4000
_SYSTEM_PATH = ("/usr/local/bin", "/usr/bin", "/bin")


@dataclass(frozen=True)
class CommandResult:
    """Outcome of one command. ``output`` holds the tail of combined stdout and stderr."""

    command: str
    exit_code: int | None
    timed_out: bool
    duration_s: float
    output: str

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass(frozen=True)
class FileChange:
    """One path an attempt added (A), modified (M) or deleted (D) in the workspace."""

    kind: str
    path: str


def base_env(home: Path) -> dict[str, str]:
    """A small, fixed environment so graders do not depend on the auditor's shell."""
    python_dir = str(Path(sys.executable).parent)
    return {
        "PATH": os.pathsep.join((python_dir, *_SYSTEM_PATH)),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "PYTHONHASHSEED": "0",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }


def _limit_memory(memory_mb: int) -> Callable[[], None]:
    def apply() -> None:  # pragma: no cover - runs in the child process before exec
        limit = memory_mb * 1024 * 1024
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    return apply


def run_command(
    command: str,
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float,
    memory_mb: int | None = None,
) -> CommandResult:
    """Run ``command`` with ``/bin/sh -c`` and return its exit status and output tail."""
    preexec = None
    if memory_mb is not None and sys.platform.startswith("linux"):
        preexec = _limit_memory(memory_mb)
    start = time.monotonic()
    proc = subprocess.Popen(
        ["/bin/sh", "-c", command],
        cwd=cwd,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        preexec_fn=preexec,  # noqa: PLW1509 - only sets an rlimit, no locks involved
    )
    timed_out = False
    try:
        raw, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc.pid)
        try:
            raw, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - a daemon escaped the group
            proc.kill()
            proc.wait()
            raw = b""
    finally:
        # Reap anything the command left running in the background.
        _kill_group(proc.pid)
    duration = time.monotonic() - start
    text = raw.decode("utf-8", errors="replace")
    return CommandResult(
        command=command,
        exit_code=None if timed_out else proc.returncode,
        timed_out=timed_out,
        duration_s=round(duration, 3),
        output=text[-OUTPUT_TAIL_CHARS:],
    )


def _kill_group(pid: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGKILL)


@dataclass(frozen=True)
class Sandbox:
    """One attempt's scratch area: ``workspace`` is what the agent sees and edits."""

    root: Path
    workspace: Path
    home: Path

    @property
    def env(self) -> dict[str, str]:
        return base_env(self.home)


@contextlib.contextmanager
def sandbox_for(task: Task, *, keep: bool = False) -> Iterator[Sandbox]:
    """Create a fresh workspace for ``task`` as the agent would find it.

    The workspace starts as a copy of ``environment/``; visible tests are copied into
    ``workspace/tests``. The task directory itself is never written to.
    """
    root = Path(tempfile.mkdtemp(prefix="graderguard-"))
    try:
        workspace = root / "workspace"
        if task.environment_dir.is_dir():
            shutil.copytree(task.environment_dir, workspace, symlinks=True)
        else:
            workspace.mkdir()
        if task.tests_visible:
            shutil.copytree(task.tests_dir, workspace / "tests", symlinks=True)
        home = root / "home"
        home.mkdir()
        yield Sandbox(root=root, workspace=workspace, home=home)
    finally:
        if not keep:
            shutil.rmtree(root, ignore_errors=True)


def install_tests(task: Task, workspace: Path) -> None:
    """Put the grader's tests in place the way the harness would before grading.

    Hidden tests are always copied in. Visible tests are replaced with the pristine copy when
    ``refresh_tests`` is set; otherwise whatever the agent left in ``tests/`` is graded.
    """
    if task.tests_visible and not task.refresh_tests:
        return
    target = workspace / "tests"
    remove_path(target)
    shutil.copytree(task.tests_dir, target, symlinks=True)


def remove_path(path: Path) -> None:
    """Delete a file, symlink or directory tree if it exists."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def snapshot(root: Path) -> dict[str, str]:
    """Map every file and symlink under ``root`` to a content fingerprint."""
    result: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        names = list(filenames) + [d for d in dirnames if (base / d).is_symlink()]
        for name in names:
            path = base / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                result[rel] = "link:" + os.readlink(path)
            else:
                result[rel] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def diff_snapshots(before: Mapping[str, str], after: Mapping[str, str]) -> list[FileChange]:
    """List added, modified and deleted paths, sorted by path."""
    changes = [FileChange("A", p) for p in after if p not in before]
    changes += [FileChange("D", p) for p in before if p not in after]
    changes += [FileChange("M", p) for p in after if p in before and before[p] != after[p]]
    return sorted(changes, key=lambda change: change.path)
