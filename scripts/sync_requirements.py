"""Regenerate requirements.txt from pyproject.toml (requires Poetry + export plugin).

On Windows if `poetry lock` fails: `python -m uv tool run poetry lock`
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "requirements.txt"


def main() -> int:
    cmd = [
        "poetry",
        "export",
        "-f",
        "requirements.txt",
        "--output",
        str(OUT),
        "--without-hashes",
        "--without",
        "dev",
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
