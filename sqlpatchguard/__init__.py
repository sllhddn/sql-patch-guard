"""sql-patch-guard: catch risky statements in database patch scripts."""
__version__ = "1.0.0"

from .linter import lint_sql  # noqa: E402,F401
