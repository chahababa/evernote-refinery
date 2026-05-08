from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from evernote_refinery.parser import parse_enex


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evernote-refinery",
        description="Convert Evernote ENEX exports into clean, reusable data.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    count = subcommands.add_parser("count", help="Count notes in an ENEX file")
    count.add_argument("enex", type=Path)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "count":
        total = sum(1 for _note in parse_enex(args.enex))
        print(f"notes: {total}")
        return 0

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
