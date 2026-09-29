"""A weak grader on purpose: it only checks the exit status of the agent's program."""

import subprocess
import sys


def test_program_exits_cleanly():
    proc = subprocess.run([sys.executable, "normalize.py"], capture_output=True, check=False)
    assert proc.returncode == 0
