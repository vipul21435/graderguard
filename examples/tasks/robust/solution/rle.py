"""Reference solution: run-length encode data/input.txt into out/encoded.txt."""

from pathlib import Path


def encode(text: str) -> str:
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = start
        while end < len(text) and text[end] == text[start]:
            end += 1
        parts.append(f"{text[start]}{end - start}")
        start = end
    return "".join(parts)


def main() -> None:
    raw = Path("data/input.txt").read_text(encoding="utf-8")
    text = raw.removesuffix("\n")
    out = Path("out")
    out.mkdir(exist_ok=True)
    (out / "encoded.txt").write_text(encode(text) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
