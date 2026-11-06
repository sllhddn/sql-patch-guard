# sql-patch-guard: How to use

This guide takes you from installing the tool to running it in a release pipeline.

## 1. Install

You need Python 3.10 or newer. The tool has no runtime dependencies.

```bash
git clone https://github.com/sllhddn/sql-patch-guard.git
cd sql-patch-guard
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # installs the CLI plus pytest
sql-patch-guard --version
```

## 2. Lint a patch

```bash
sql-patch-guard examples/risky_patch.sql
```

Each finding prints as `file:line: SEVERITY CODE message`, followed by the statement that triggered it.
The last line is a summary: `1 file(s) checked: 4 error(s), 7 warning(s)`.

Lint several files at once with a glob:

```bash
sql-patch-guard patches/release-2.4/*.sql
```

## 3. Understand the result

| Severity | Meaning | What to do |
|---|---|---|
| **ERROR** | The statement will damage data or fail in production | Fix it before the patch is run |
| **WARN** | The statement may be fine, but a person must confirm it | Read it, then either fix it or accept it consciously |

See the rule table in the [README](../README.md#rules) for what each code catches.

## 4. Turn on the column-narrowing check (SPG006)

SPG006 compares new column sizes with what the database has today, so it needs a snapshot.

1. Export current column sizes from the target database.

   PostgreSQL:
   ```sql
   SELECT table_name, column_name, data_type,
          character_maximum_length AS length, numeric_precision AS precision, numeric_scale AS scale
   FROM information_schema.columns
   WHERE table_schema = 'public';
   ```

   Oracle:
   ```sql
   SELECT LOWER(table_name), LOWER(column_name), LOWER(data_type),
          char_length, data_precision, data_scale
   FROM all_tab_columns WHERE owner = :schema;
   ```

2. Convert the result into this JSON shape (one key per table, one per column):

   ```json
   {
     "application": { "remarks": { "type": "varchar", "length": 4000 } },
     "land_parcel": { "area": { "type": "numeric", "precision": 16, "scale": 4 } }
   }
   ```

3. Pass it with `--schema`:

   ```bash
   sql-patch-guard patch.sql --schema schema_snapshot.json
   ```

## 5. Options

| Option | Default | Effect |
|---|---|---|
| `--schema FILE` | none | Enables SPG006 using the JSON snapshot |
| `--format text\|json` | `text` | `json` prints machine-readable findings |
| `--disable CODES` | none | Skip rules, e.g. `--disable SPG004,SPG007` |
| `--fail-on error\|warn\|never` | `error` | When the exit code is non-zero |
| `--list-rules` | | Print every rule with its description |

Exit codes: `0` = passed, `1` = findings at or above the `--fail-on` level.

## 6. Use it in a release pipeline

### GitHub Actions

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install git+https://github.com/sllhddn/sql-patch-guard.git
- run: sql-patch-guard db/patches/*.sql --schema db/schema_snapshot.json
```

### GitLab CI

```yaml
lint-sql:
  image: python:3.12-slim
  script:
    - pip install git+https://github.com/sllhddn/sql-patch-guard.git
    - sql-patch-guard db/patches/*.sql
```

### Before a manual release

```bash
sql-patch-guard release.sql && psql -f release.sql
```

The `&&` means the patch only runs if the linter passes.

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| A finding points to the wrong line | Statement starts after a long comment | Line numbers point to the first non-comment character; check just below |
| SPG006 never fires | No `--schema`, or the snapshot uses upper-case names | Pass the snapshot and write table and column names in lower case |
| A legitimate `USING` is flagged | The expression reads a different column on purpose | Confirm it, then lint that file on its own with `--disable SPG001` |
| Odd findings inside a PL/SQL block | The splitter treats every `;` as a statement end, including inside `BEGIN … END` | Keep PL/SQL packages in their own files and lint only DDL/DML patch files |

## 8. Run the tests

```bash
pytest -q
```

14 tests cover every rule (a "should flag" and a "should not flag" case), the parser, and the example files end to end.
