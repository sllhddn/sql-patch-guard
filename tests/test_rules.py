import json
from pathlib import Path

import pytest

from sqlpatchguard import lint_sql
from sqlpatchguard.cli import main
from sqlpatchguard.parser import split_statements

EXAMPLES = Path(__file__).parent.parent / "examples"


def codes(sql, schema=None):
    return [f.rule for f in lint_sql(sql, schema)]


def test_using_other_column_is_error():
    sql = "ALTER TABLE t ALTER COLUMN b TYPE numeric(16,5) USING a::numeric(16,5);"
    assert codes(sql) == ["SPG001"]


@pytest.mark.parametrize("sql", [
    "ALTER TABLE t ALTER COLUMN b TYPE integer USING b::integer;",
    "ALTER TABLE t ALTER COLUMN b TYPE integer USING trim(b)::integer;",
    "ALTER TABLE t ALTER COLUMN b TYPE date USING to_date(b, 'YYYYMMDD');",
    "ALTER TABLE t ALTER COLUMN b TYPE numeric(16,5);",
])
def test_using_same_column_is_fine(sql):
    assert codes(sql) == []


def test_increment_by_expression():
    assert codes("ALTER SEQUENCE s INCREMENT BY 500 - 20;") == ["SPG002"]
    assert codes("ALTER SEQUENCE s INCREMENT BY 480;") == []
    assert codes("ALTER SEQUENCE s INCREMENT BY -1;") == []


def test_unbounded_dml():
    assert codes("DELETE FROM t;") == ["SPG003"]
    assert codes("UPDATE t SET a = 1;") == ["SPG003"]
    assert codes("UPDATE t SET a = 1 WHERE id = 2;") == []


def test_destructive_is_warning():
    findings = lint_sql("DROP TABLE junk_tmp;")
    assert [(f.rule, f.severity) for f in findings] == [("SPG004", "WARN")]


def test_add_not_null_without_default():
    assert codes("ALTER TABLE t ADD COLUMN c varchar(5) NOT NULL;") == ["SPG005"]
    assert codes("ALTER TABLE t ADD COLUMN c varchar(5) DEFAULT 'x' NOT NULL;") == []


def test_narrowing_needs_schema():
    schema = {"t": {"note": {"length": 4000}, "amt": {"precision": 16, "scale": 4}}}
    assert codes("ALTER TABLE t ALTER COLUMN note TYPE varchar(100);") == []
    assert codes("ALTER TABLE t ALTER COLUMN note TYPE varchar(100);", schema) == ["SPG006"]
    assert codes("ALTER TABLE t MODIFY (note VARCHAR2(100));", schema) == ["SPG006"]
    assert codes("ALTER TABLE t ALTER COLUMN amt TYPE numeric(16,5);", schema) == ["SPG006"]  # 12 -> 11 int digits
    assert codes("ALTER TABLE t ALTER COLUMN amt TYPE numeric(17,5);", schema) == []


def test_duplicates_flagged_once():
    sql = "ALTER TABLE t ADD c int;\nALTER TABLE t ADD c int;"
    assert codes(sql) == ["SPG007"]


def test_parser_handles_comments_quotes_and_slash():
    sql = "-- a; comment\nINSERT INTO t VALUES ('a;b');\n/* block; */\nBEGIN null; END;\n/\nSELECT 1 FROM dual"
    stmts = split_statements(sql)
    assert stmts[0].text == "INSERT INTO t VALUES ('a;b')"
    assert stmts[0].line == 2
    assert stmts[-1].text == "SELECT 1 FROM dual"


def test_examples_end_to_end(capsys):
    schema = str(EXAMPLES / "schema_snapshot.json")
    assert main([str(EXAMPLES / "risky_patch.sql"), "--schema", schema]) == 1
    out = capsys.readouterr().out
    for code in ["SPG001", "SPG002", "SPG003", "SPG005", "SPG006", "SPG007"]:
        assert code in out
    assert main([str(EXAMPLES / "safe_patch.sql"), "--schema", schema]) == 0


def test_json_output(capsys):
    main([str(EXAMPLES / "risky_patch.sql"), "--format", "json", "--fail-on", "never"])
    data = json.loads(capsys.readouterr().out)
    assert {d["rule"] for d in data} >= {"SPG001", "SPG002"}
