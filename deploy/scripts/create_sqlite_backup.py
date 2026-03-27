#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a consistent SQLite backup using the SQLite backup API.")
    parser.add_argument("--source", required=True, help="Source sqlite database path")
    parser.add_argument("--dest", required=True, help="Destination sqlite database path")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    dest = Path(args.dest).resolve()

    if not source.exists():
        raise SystemExit(f"source database not found: {source}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()

    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
