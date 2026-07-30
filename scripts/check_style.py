"""Fail if a comment or doc line uses an em-dash or a semicolon.

# ponytail: same line-based comment extraction as check_comment_lines.py,
# duplicated rather than shared since each is a handful of lines.
"""

import sys
from pathlib import Path

BANNED = ("—", ";")
BASELINE_PATH = Path(__file__).parent / ".style_baseline"
BASELINE = {line.strip() for line in BASELINE_PATH.read_text().splitlines() if line.strip()}

LINE_MARKERS = {
    ".py": "#",
    ".ts": "//",
    ".tsx": "//",
    ".js": "//",
    ".jsx": "//",
    ".vue": "//",
    ".astro": "//",
}
BLOCK_MARKERS = {
    ".ts": ("/*", "*/"),
    ".tsx": ("/*", "*/"),
    ".js": ("/*", "*/"),
    ".jsx": ("/*", "*/"),
    ".vue": ("/*", "*/"),
    ".astro": ("/*", "*/"),
}


def comment_lines(path: Path) -> list[tuple[int, str]]:
    line_marker = LINE_MARKERS.get(path.suffix)
    block_start, block_end = BLOCK_MARKERS.get(path.suffix, (None, None))
    found = []
    in_block = False
    for i, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if in_block:
            found.append((i, line))
            if block_end and block_end in line:
                in_block = False
            continue
        if not line:
            continue
        if line_marker and line.startswith(line_marker):
            found.append((i, line))
        elif block_start and line.startswith(block_start):
            found.append((i, line))
            if block_end not in line:
                in_block = True
    return found


def markdown_lines(path: Path) -> list[tuple[int, str]]:
    found = []
    in_fence = False
    for i, raw_line in enumerate(path.read_text().splitlines(), start=1):
        if raw_line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        found.append((i, raw_line))
    return found


def main(argv: list[str]) -> int:
    failed = False
    for arg in argv:
        if arg in BASELINE:
            continue
        path = Path(arg)
        lines = markdown_lines(path) if path.suffix == ".md" else comment_lines(path)
        for lineno, text in lines:
            for banned in BANNED:
                if banned in text:
                    print(f"{path}:{lineno}: uses {banned!r}: {text.strip()}")
                    failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
