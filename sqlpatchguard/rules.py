"""Lint rules for database patch scripts.

Each rule receives a parsed Statement (plus optional schema snapshot) and
yields Finding objects. Rules are deliberately conservative: they flag
statements a human should look at before the patch is run in production.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

from .parser import Statement

ERROR, WARN = "ERROR", "WARN"


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    line: int
    message: str
    statement: str


# schema snapshot shape: {"table": {"column": {"type": "varchar", "length": 100, "precision": 16, "scale": 4}}}
Schema = dict

RuleFn = Callable[[Statement, Schema | None], Iterable[Finding]]
RULES: list[tuple[str, str, RuleFn]] = []


def rule(code: str, description: str):
    def deco(fn: RuleFn) -> RuleFn:
        RULES.append((code, description, fn))
        return fn
    return deco


IDENT = r'"?[A-Za-z_][A-Za-z0-9_$#]*"?'


def _norm(name: str) -> str:
    return name.strip('"').lower()


# --------------------------------------------------------------------------- #
# SPG001 - USING clause that reads from a *different* column
# --------------------------------------------------------------------------- #
_ALTER_TYPE_USING = re.compile(
    rf"ALTER\s+TABLE\s+(?:{IDENT}\.)?(?P<table>{IDENT})\s+ALTER\s+COLUMN\s+(?P<col>{IDENT})\s+"
    rf"(?:SET\s+DATA\s+)?TYPE\s+.+?\s+USING\s+(?P<expr>.+)$",
    re.IGNORECASE,
)
_SQL_WORDS = {
    "cast", "as", "numeric", "integer", "int", "bigint", "smallint", "text", "varchar", "character",
    "varying", "date", "timestamp", "boolean", "bool", "null", "case", "when", "then", "else", "end",
    "trim", "coalesce", "nullif", "to_number", "to_date", "to_char", "round", "true", "false", "and",
    "or", "not", "is", "decimal", "real", "double", "precision", "bytea", "char", "upper", "lower",
}


@rule("SPG001", "ALTER COLUMN ... TYPE ... USING reads a different column (silent data overwrite)")
def using_other_column(stmt: Statement, schema: Schema | None):
    m = _ALTER_TYPE_USING.search(stmt.text)
    if not m:
        return
    target = _norm(m["col"])
    expr = re.sub(r"'[^']*'", "", m["expr"])          # drop string literals
    expr = re.sub(r"::\s*[A-Za-z_ ]+(\([^)]*\))?", "", expr)  # drop ::type casts
    idents = {_norm(t) for t in re.findall(IDENT, expr)} - _SQL_WORDS
    others = sorted(i for i in idents if i != target and not i.isdigit())
    if others and target not in idents:
        yield Finding(
            "SPG001", ERROR, stmt.line,
            f"column '{target}' is rewritten from {', '.join(repr(o) for o in others)} - every row will be "
            f"overwritten with another column's value. If only the type/size changes, drop the USING clause.",
            stmt.text,
        )


# --------------------------------------------------------------------------- #
# SPG002 - Oracle ALTER SEQUENCE INCREMENT BY with an expression
# --------------------------------------------------------------------------- #
_INCREMENT = re.compile(r"ALTER\s+SEQUENCE\s+\S+\s+INCREMENT\s+BY\s+(?P<val>[^\s]+(?:\s*[-+*/]\s*[^\s]+)*)", re.I)


@rule("SPG002", "INCREMENT BY must be a literal integer (Oracle does not evaluate expressions in DDL)")
def increment_expression(stmt: Statement, schema: Schema | None):
    m = _INCREMENT.search(stmt.text)
    if m and not re.fullmatch(r"-?\d+", m["val"].replace(" ", "")):
        yield Finding("SPG002", ERROR, stmt.line,
                      f"INCREMENT BY '{m['val']}' is not a literal - pre-calculate the gap (ORA-01722 otherwise).",
                      stmt.text)


# --------------------------------------------------------------------------- #
# SPG003 - UPDATE / DELETE without WHERE
# --------------------------------------------------------------------------- #
@rule("SPG003", "UPDATE or DELETE without a WHERE clause")
def unbounded_dml(stmt: Statement, schema: Schema | None):
    head = stmt.text.lstrip().upper()
    if (head.startswith("UPDATE ") or head.startswith("DELETE ")) and " WHERE " not in f" {head} ":
        yield Finding("SPG003", ERROR, stmt.line, "statement affects every row in the table (no WHERE clause).",
                      stmt.text)


# --------------------------------------------------------------------------- #
# SPG004 - destructive DDL
# --------------------------------------------------------------------------- #
_DESTRUCTIVE = re.compile(r"^(DROP\s+TABLE|TRUNCATE|ALTER\s+TABLE\s+\S+\s+DROP\s+(COLUMN|CONSTRAINT))", re.I)


@rule("SPG004", "Destructive DDL (DROP / TRUNCATE) - confirm a backup or rollback exists")
def destructive(stmt: Statement, schema: Schema | None):
    m = _DESTRUCTIVE.search(stmt.text)
    if m:
        yield Finding("SPG004", WARN, stmt.line, f"destructive operation '{m.group(1).upper()}'.", stmt.text)


# --------------------------------------------------------------------------- #
# SPG005 - NOT NULL column added without DEFAULT
# --------------------------------------------------------------------------- #
_ADD_COL = re.compile(r"ALTER\s+TABLE\s+\S+\s+ADD\s+(?:COLUMN\s+)?(?P<def>.+)$", re.I)


@rule("SPG005", "ADD COLUMN ... NOT NULL without DEFAULT fails on non-empty tables")
def add_not_null(stmt: Statement, schema: Schema | None):
    m = _ADD_COL.search(stmt.text)
    if m and re.search(r"\bNOT\s+NULL\b", m["def"], re.I) and not re.search(r"\bDEFAULT\b", m["def"], re.I) \
            and not re.match(r"\s*CONSTRAINT\b", m["def"], re.I):
        yield Finding("SPG005", WARN, stmt.line, "NOT NULL column without DEFAULT - existing rows will reject it.",
                      stmt.text)


# --------------------------------------------------------------------------- #
# SPG006 - column narrowing (needs a schema snapshot)
# --------------------------------------------------------------------------- #
_PG_ALTER = re.compile(
    rf"ALTER\s+TABLE\s+(?:{IDENT}\.)?(?P<table>{IDENT})\s+ALTER\s+COLUMN\s+(?P<col>{IDENT})\s+"
    rf"(?:SET\s+DATA\s+)?TYPE\s+(?P<type>[A-Za-z0-9_ ]+?)\s*\((?P<a>\d+)\s*(?:,\s*(?P<b>\d+))?\)", re.I)
_ORA_MODIFY = re.compile(
    rf"ALTER\s+TABLE\s+(?:{IDENT}\.)?(?P<table>{IDENT})\s+MODIFY\s*\(?\s*(?P<col>{IDENT})\s+"
    rf"(?P<type>[A-Za-z0-9_ ]+?)\s*\((?P<a>\d+)\s*(?:,\s*(?P<b>\d+))?\)", re.I)


@rule("SPG006", "Column is being narrowed compared to the current schema (possible truncation)")
def narrowing(stmt: Statement, schema: Schema | None):
    if not schema:
        return
    m = _PG_ALTER.search(stmt.text) or _ORA_MODIFY.search(stmt.text)
    if not m:
        return
    cur = schema.get(_norm(m["table"]), {}).get(_norm(m["col"]))
    if not cur:
        return
    new_a, new_b = int(m["a"]), int(m["b"]) if m["b"] else None
    if "length" in cur and new_a < cur["length"]:
        yield Finding("SPG006", WARN, stmt.line,
                      f"{_norm(m['table'])}.{_norm(m['col'])} length {cur['length']} -> {new_a}.", stmt.text)
    if "precision" in cur:
        cur_int = cur["precision"] - cur.get("scale", 0)
        new_int = new_a - (new_b or 0)
        if new_int < cur_int or (new_b is not None and new_b < cur.get("scale", 0)):
            yield Finding("SPG006", WARN, stmt.line,
                          f"{_norm(m['table'])}.{_norm(m['col'])} numeric({cur['precision']},{cur.get('scale', 0)})"
                          f" -> numeric({new_a},{new_b or 0}): integer digits {cur_int} -> {new_int}, "
                          f"scale {cur.get('scale', 0)} -> {new_b or 0}. Check MAX(value) fits first.", stmt.text)
