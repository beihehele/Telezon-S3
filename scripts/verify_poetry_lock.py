"""Fail if poetry.lock still lists removed Mongo/passlib-era packages."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "poetry.lock"

FORBIDDEN = frozenset({"motor", "pymongo", "passlib"})
REQUIRED = frozenset({"sqlalchemy", "aiomysql", "bcrypt"})


def main() -> int:
    if not LOCK.is_file():
        print("poetry.lock missing", file=sys.stderr)
        return 1
    text = LOCK.read_text(encoding="utf-8")
    names = set(re.findall(r'^name = "([^"]+)"', text, re.MULTILINE))
    bad = sorted(names & FORBIDDEN)
    if bad:
        print(
            "poetry.lock still contains removed packages: "
            + ", ".join(bad)
            + ". Run: poetry lock && make export",
            file=sys.stderr,
        )
        return 1
    missing = sorted(REQUIRED - names)
    if missing:
        print(
            "poetry.lock missing expected packages: "
            + ", ".join(missing)
            + ". Run: poetry lock && make export",
            file=sys.stderr,
        )
        return 1
    print("poetry.lock OK (no motor/pymongo/passlib; has sqlalchemy/aiomysql/bcrypt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
