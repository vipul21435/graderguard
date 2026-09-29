"""A robust grader: fresh random inputs at grading time, an independent oracle and a
byte-exact comparison of the output file."""

import random
import re
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()


def oracle(text: str) -> bytes:
    runs = re.finditer(r"([a-z])\1*", text)
    return ("".join(f"{m.group(1)}{len(m.group(0))}" for m in runs) + "\n").encode()


def run_agent(text: str) -> bytes:
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "input.txt").write_text(text + "\n", encoding="utf-8")
    out = ROOT / "out" / "encoded.txt"
    out.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rle.py"], cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    return out.read_bytes()


def test_worked_example():
    assert run_agent("aaabcc") == b"a3b1c2\n"


def test_empty_input():
    assert run_agent("") == b"\n"


def test_fresh_random_inputs():
    seed = secrets.randbits(32)
    rng = random.Random(seed)
    for _ in range(5):
        runs = rng.randint(1, 25)
        text = "".join(rng.choice("abcxyz") * rng.randint(1, 12) for _ in range(runs))
        assert run_agent(text) == oracle(text), f"seed={seed}"
