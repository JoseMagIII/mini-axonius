from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

# Nodes that write, change schema, lock rows, or run arbitrary commands, anywhere in the tree.
FORBIDDEN_NODES = (exp.DML, exp.DDL, exp.Into, exp.Command, exp.Copy, exp.Lock, exp.Set)
FORBIDDEN_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink", "set_config", "query_to_xml")


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    sql: str
    reason: str = ""


def _blocked(statement: str, reason: str) -> GuardrailResult:
    return GuardrailResult(allowed=False, sql=statement, reason=reason)


def check_sql(statement: str, row_limit: int = 200) -> GuardrailResult:
    """Allows a single read-only query and caps how many rows it returns."""
    if not statement.strip():
        return _blocked(statement, "The query is empty.")
    try:
        trees = [t for t in sqlglot.parse(statement, read="postgres") if t is not None]
    except ParseError as error:
        return _blocked(statement, f"Couldn't parse the SQL: {error}")

    if len(trees) != 1:
        return _blocked(statement, "Send exactly one statement per query.")
    tree = trees[0]
    if not isinstance(tree, exp.Query):
        return _blocked(statement, "Only SELECT queries are allowed.")

    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            return _blocked(statement, f"{type(node).__name__} isn't allowed in a read-only query.")
        if isinstance(node, exp.Func):
            name = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
            if name.startswith(FORBIDDEN_FUNCTION_PREFIXES):
                return _blocked(statement, f"The function {name} isn't allowed.")

    limit = tree.args.get("limit")
    if limit is None:
        tree = tree.limit(row_limit)
    return GuardrailResult(allowed=True, sql=tree.sql(dialect="postgres"))
