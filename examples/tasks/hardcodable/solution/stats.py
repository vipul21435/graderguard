"""Reference solution: per-sensor mean of data/readings.csv into out/summary.json."""

import csv
import json
from collections import defaultdict
from pathlib import Path


def main() -> None:
    readings: dict[str, list[float]] = defaultdict(list)
    with Path("data/readings.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            readings[row["sensor"]].append(float(row["value"]))
    summary = {name: round(sum(vals) / len(vals), 2) for name, vals in sorted(readings.items())}
    out = Path("out")
    out.mkdir(exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
