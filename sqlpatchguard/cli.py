"""Command line entry point: `sql-patch-guard patch1.sql patch2.sql`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .linter import lint_sql
from .rules import ERROR, RULES

COLORS = {"ERROR": "\033[31m", "WARN": "\033[33m"}
RESET = "\033[0m"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sql-patch-guard",
                                description="Lint Oracle/PostgreSQL patch scripts before they reach production.")
    p.add_argument("files", nargs="*", type=Path, help="SQL patch files to check")
    p.add_argument("--schema", type=Path, help="JSON snapshot of current column sizes (enables SPG006)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--disable", default="", help="comma separated rule codes to skip, e.g. SPG004,SPG007")
    p.add_argument("--fail-on", choices=["error", "warn", "never"], default="error",
                   help="exit non-zero when findings of this level exist (default: error)")
    p.add_argument("--list-rules", action="store_true")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)

    if args.list_rules:
        for code, desc, _ in RULES:
            print(f"{code}  {desc}")
        print("SPG007  Exact duplicate statement in the same file")
        return 0
    if not args.files:
        p.error("no files given")

    schema = json.loads(args.schema.read_text()) if args.schema else None
    disabled = {c.strip().upper() for c in args.disable.split(",") if c.strip()}

    results = []
    for f in args.files:
        for finding in lint_sql(f.read_text(encoding="utf-8"), schema, disabled):
            results.append((f, finding))

    if args.format == "json":
        print(json.dumps([{"file": str(f), **fd.__dict__} for f, fd in results], indent=2))
    else:
        color = sys.stdout.isatty()
        for f, fd in results:
            sev = f"{COLORS[fd.severity]}{fd.severity}{RESET}" if color else fd.severity
            print(f"{f}:{fd.line}: {sev} {fd.rule} {fd.message}")
            print(f"    {fd.statement[:160]}")
        errors = sum(1 for _, fd in results if fd.severity == ERROR)
        print(f"\n{len(args.files)} file(s) checked: {errors} error(s), {len(results) - errors} warning(s)")

    if args.fail_on == "never":
        return 0
    if args.fail_on == "warn":
        return 1 if results else 0
    return 1 if any(fd.severity == ERROR for _, fd in results) else 0


if __name__ == "__main__":
    sys.exit(main())
