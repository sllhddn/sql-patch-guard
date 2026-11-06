from __future__ import annotations

from collections import Counter

from .parser import split_statements
from .rules import RULES, WARN, Finding, Schema


def lint_sql(sql: str, schema: Schema | None = None, disabled: set[str] | None = None) -> list[Finding]:
    disabled = disabled or set()
    statements = split_statements(sql)
    findings: list[Finding] = []
    for stmt in statements:
        for code, _desc, fn in RULES:
            if code not in disabled:
                findings.extend(fn(stmt, schema))

    # SPG007 - exact duplicate statements usually mean a copy-paste slip
    if "SPG007" not in disabled:
        counts = Counter(s.text.lower() for s in statements)
        seen = set()
        for s in statements:
            key = s.text.lower()
            if counts[key] > 1 and key in seen:
                findings.append(Finding("SPG007", WARN, s.line, "duplicate of an earlier statement.", s.text))
            seen.add(key)

    return sorted(findings, key=lambda f: (f.line, f.rule))
