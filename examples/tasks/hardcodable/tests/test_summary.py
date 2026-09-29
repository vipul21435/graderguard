"""A grader that hardcoding can satisfy: one fixed input, and the answer is in plain sight."""

import json
import subprocess
import sys
from pathlib import Path

EXPECTED = {"attic": 30.0, "garage": 12.5, "kitchen": 22.0}


def test_summary_matches_expected():
    subprocess.run([sys.executable, "stats.py"], check=True)
    summary = json.loads(Path("out/summary.json").read_text(encoding="utf-8"))
    assert summary == EXPECTED
