"""Reference solution: normalize data/names.txt into out/names.txt."""

from pathlib import Path


def normalize(line: str) -> str:
    return " ".join(word.capitalize() for word in line.split())


def main() -> None:
    seen: dict[str, None] = {}
    for raw in Path("data/names.txt").read_text(encoding="utf-8").splitlines():
        name = normalize(raw)
        if name:
            seen.setdefault(name, None)
    out = Path("out")
    out.mkdir(exist_ok=True)
    (out / "names.txt").write_text("".join(f"{name}\n" for name in seen), encoding="utf-8")


if __name__ == "__main__":
    main()
