"""Branch + commit + PR. The Freigabe-Queue from PLAN.md Abschnitt 7: every
source's output lands here the same way, so a human reviews the same kind of
diff regardless of which adapter produced it."""

import subprocess
from pathlib import Path
from typing import List


def oeffne_pr(branch: str, dateien: List[Path], commit_message: str, pr_titel: str, pr_body: str) -> None:
    _run("git", "checkout", "-b", branch)
    _run("git", "add", *[str(p) for p in dateien])
    _run("git", "commit", "-m", commit_message)
    _run("git", "push", "-u", "origin", branch)
    _run("gh", "pr", "create", "--title", pr_titel, "--body", pr_body)


def _run(*cmd: str) -> None:
    subprocess.run(cmd, check=True)
