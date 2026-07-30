"""Fail if a file has more than MAX_COMMENT_LINES comment-only lines.
heuristic line-based scan, not a real parser. Misses trailing
# comments and doesn't understand vue/astro template comments
"""

import sys
from pathlib import Path

MAX_COMMENT_LINES = 20
BASELINE_PATH = Path(__file__).parent / ".comment_lines_baseline"
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


def count_comments(path: str) -> int:
    ext = Path(path).suffix
    line_marker = LINE_MARKERS.get(ext)
    block_start, block_end = BLOCK_MARKERS.get(ext, (None, None))
    count = 0
    in_block = False
    for raw_line in Path(path).read_text().splitlines():
        line = raw_line.strip()
        if in_block:
            count += 1
            if block_end and block_end in line:
                in_block = False
            continue
        if not line:
            continue
        if line_marker and line.startswith(line_marker):
            count += 1
        elif block_start and line.startswith(block_start):
            count += 1
            if block_end not in line:
                in_block = True
    return count


def main(argv: list[str]) -> int:
    failed = False
    for path in argv:
        if path in BASELINE:
            continue
        n = count_comments(path)
        if n > MAX_COMMENT_LINES:
            print(f"{path}: {n} comment lines (max {MAX_COMMENT_LINES})")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
