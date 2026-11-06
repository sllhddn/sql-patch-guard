"""Minimal SQL script splitter.

Splits a patch file into individual statements while respecting quoted
strings and comments, and remembers the line each statement starts on so
findings can point back to the source file.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Statement:
    text: str        # statement text with comments removed, whitespace collapsed
    raw: str         # original text as written
    line: int        # 1-based line where the statement starts


def _strip_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments, keeping quoted text intact."""
    out, i, n = [], 0, len(sql)
    in_quote = False
    while i < n:
        ch = sql[i]
        if in_quote:
            out.append(ch)
            if ch == "'":
                # '' is an escaped quote inside a string literal
                if i + 1 < n and sql[i + 1] == "'":
                    out.append("'")
                    i += 1
                else:
                    in_quote = False
        elif ch == "'":
            in_quote = True
            out.append(ch)
        elif sql.startswith("--", i):
            while i < n and sql[i] != "\n":
                i += 1
            continue
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            chunk = sql[i:] if end == -1 else sql[i:end + 2]
            out.append("\n" * chunk.count("\n"))  # keep line numbers stable
            i = n if end == -1 else end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def split_statements(sql: str) -> list[Statement]:
    """Split on ';' (outside quotes) and on a lone '/' line (Oracle SQL*Plus style)."""
    clean = _strip_comments(sql)
    statements: list[Statement] = []
    buf: list[str] = []
    line = 1
    start_line = None
    in_quote = False

    def flush():
        nonlocal buf, start_line
        raw = "".join(buf).strip()
        if raw:
            statements.append(Statement(" ".join(raw.split()), raw, start_line or line))
        buf, start_line = [], None

    lines = clean.split("\n")
    for line_no, text in enumerate(lines, start=1):
        line = line_no
        if not in_quote and text.strip() == "/":
            flush()
            continue
        for ch in text:
            if start_line is None and not ch.isspace():
                start_line = line_no
            if ch == "'":
                in_quote = not in_quote
            if ch == ";" and not in_quote:
                flush()
                continue
            buf.append(ch)
        buf.append("\n")
    flush()
    return statements
