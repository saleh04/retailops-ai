"""Regression tests for the SQL validator (`database.query_validator`).

The validator is the security boundary of the product: it must reject every
statement that could modify data or read files, no matter how the statement
is obfuscated.
"""

from __future__ import annotations

import pytest

from database.query_validator import QueryValidationError, QueryValidator


@pytest.fixture
def validator() -> QueryValidator:
    return QueryValidator("sqlite")


# --------------------------------------------------------------------------
# Dialect handling
# --------------------------------------------------------------------------
def test_unsupported_dialect_is_rejected():
    with pytest.raises(QueryValidationError, match="Unsupported SQL dialect"):
        QueryValidator("oracle")


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql", "mysql", "mariadb", "mssql"])
def test_supported_dialects_are_accepted(dialect: str):
    assert QueryValidator(dialect) is not None


# --------------------------------------------------------------------------
# Empty / oversized input
# --------------------------------------------------------------------------
@pytest.mark.parametrize("query", ["", "   ", "\n\t "])
def test_empty_query_is_rejected(validator: QueryValidator, query: str):
    with pytest.raises(QueryValidationError, match="cannot be empty"):
        validator.validate(query)


def test_non_string_query_is_rejected(validator: QueryValidator):
    with pytest.raises(QueryValidationError, match="cannot be empty"):
        validator.validate(None)  # type: ignore[arg-type]


def test_overlong_query_is_rejected(validator: QueryValidator):
    query = "SELECT " + ("a" * QueryValidator.MAX_QUERY_LENGTH)
    with pytest.raises(QueryValidationError, match="too long"):
        validator.validate(query)


# --------------------------------------------------------------------------
# Read-only enforcement
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query",
    [
        "INSERT INTO customers (name) VALUES ('x')",
        "UPDATE customers SET name = 'x'",
        "DELETE FROM customers",
        "DROP TABLE customers",
        "ALTER TABLE customers ADD COLUMN nickname TEXT",
        "CREATE TABLE evil (id INTEGER)",
        "REPLACE INTO customers (id, name) VALUES (1, 'x')",
        "MERGE INTO customers USING customers ON 1 = 1 WHEN MATCHED THEN UPDATE SET name = 'x'",
    ],
)
def test_write_statements_are_rejected(validator: QueryValidator, query: str):
    with pytest.raises(QueryValidationError):
        validator.validate(query)


@pytest.mark.parametrize(
    "query",
    [
        "PRAGMA table_info(customers)",
        "PRAGMA database_list",
    ],
)
def test_pragma_statements_are_rejected(validator: QueryValidator, query: str):
    with pytest.raises(QueryValidationError, match="Only SELECT queries are allowed"):
        validator.validate(query)


def test_pragma_with_a_second_statement_is_rejected(validator: QueryValidator):
    with pytest.raises(QueryValidationError, match="Exactly one SQL statement"):
        validator.validate("PRAGMA database_list; SELECT 1")


@pytest.mark.parametrize(
    "query",
    [
        "ATTACH DATABASE '/tmp/evil.db' AS evil",
        "DETACH DATABASE evil",
        "VACUUM",
        "VACUUM INTO '/tmp/evil.db'",
        "REINDEX customers",
        "ANALYZE customers",
        "CREATE TABLE evil (id INTEGER)",
        "REPLACE INTO customers (id, name) VALUES (1, 'x')",
    ],
)
def test_ddl_and_maintenance_statements_are_rejected(
    validator: QueryValidator, query: str
):
    with pytest.raises(QueryValidationError):
        validator.validate(query)


def test_read_only_select_is_accepted(validator: QueryValidator):
    assert validator.validate("SELECT id FROM customers") == "SELECT id FROM customers"


@pytest.mark.parametrize(
    "query",
    [
        "SELECT id FROM customers FOR UPDATE",
        "SELECT id FROM customers LOCK IN SHARE MODE",
        "SELECT 1 INTO @target",
    ],
)
def test_locking_and_select_into_are_rejected(validator: QueryValidator, query: str):
    """Locking and `SELECT ... INTO` are not read-only operations."""
    with pytest.raises(QueryValidationError, match="forbidden operation"):
        validator.validate(query)


def test_union_select_is_accepted(validator: QueryValidator):
    sql = validator.validate(
        "SELECT id FROM customers UNION SELECT id FROM orders"
    )
    assert sql.upper().startswith("SELECT")
    assert "UNION" in sql.upper()


# --------------------------------------------------------------------------
# Blocked dangerous functions
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query",
    [
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_ls_dir('/tmp')",
        "SELECT load_extension('evil.so')",
        "SELECT randomblob(100000)",
        "SELECT zeroblob(1000)",
        "SELECT nextval('users_id_seq')",
        "SELECT setval('users_id_seq', 1)",
        "SELECT sleep(5)",
        "SELECT load_file('/etc/passwd')",
        "SELECT xp_cmdshell('whoami')",
        "SELECT openrowset('x', 'y')",
        "SELECT dblink('x', 'y')",
        "SELECT lo_import('/etc/passwd')",
        "SELECT set_config('x', 'y', false)",
        "SELECT pg_terminate_backend(1)",
    ],
)
def test_blocked_functions_are_rejected(validator: QueryValidator, query: str):
    with pytest.raises(QueryValidationError, match="forbidden function"):
        validator.validate(query)


def test_blocked_function_detection_is_case_insensitive(validator: QueryValidator):
    with pytest.raises(QueryValidationError, match="forbidden function"):
        validator.validate("SELECT PG_SLEEP(1)")


def test_allowed_functions_are_not_blocked(validator: QueryValidator):
    sql = validator.validate("SELECT COUNT(*), UPPER(name), ABS(total) FROM orders")
    assert "COUNT" in sql.upper()


# --------------------------------------------------------------------------
# Injection / parsing edge cases
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query",
    [
        "SELECT 1; DROP TABLE customers",
        "SELECT 1;DROP TABLE customers",
        "SELECT 1; DELETE FROM customers",
        "SELECT * FROM customers; SELECT * FROM orders",
        "SELECT 1; ATTACH DATABASE '/tmp/evil.db' AS evil",
    ],
)
def test_multi_statement_queries_are_rejected(validator: QueryValidator, query: str):
    with pytest.raises(QueryValidationError, match="Exactly one SQL statement"):
        validator.validate(query)


def test_trailing_semicolon_is_tolerated(validator: QueryValidator):
    assert validator.validate("SELECT 1;") == "SELECT 1"


@pytest.mark.parametrize(
    "query",
    [
        "/* harmless */ SELECT 1; /* DROP TABLE customers */",
        "SELECT 1; -- DROP TABLE customers",
        "SELECT 1; /* UPDATE customers SET name = 'x' */",
    ],
)
def test_second_statement_after_a_comment_is_rejected(validator: QueryValidator, query: str):
    """A comment must not be usable to smuggle a second statement."""
    with pytest.raises(QueryValidationError, match="Exactly one SQL statement"):
        validator.validate(query)


def test_write_operation_hidden_in_a_line_comment_never_executes(validator: QueryValidator):
    """The commented-out write is dropped together with the comment."""
    sql = validator.validate("-- DROP TABLE customers\nSELECT id FROM customers")
    assert "DROP" not in sql.upper()
    assert sql == "SELECT id FROM customers"


def test_write_operation_hidden_in_a_block_comment_never_executes(validator: QueryValidator):
    sql = validator.validate("SELECT id FROM customers /* DROP TABLE customers */")
    assert "DROP" not in sql.upper()
    assert sql == "SELECT id FROM customers"


def test_mysql_executable_comment_cannot_smuggle_a_statement(validator: QueryValidator):
    """Executable comments are stripped from the SQL that is executed."""
    sql = validator.validate("SELECT 1 /*! UNION SELECT 2 */")
    assert "UNION" not in sql.upper()
    assert sql == "SELECT 1"


def test_optimizer_hint_cannot_smuggle_a_statement(validator: QueryValidator):
    sql = validator.validate("SELECT 1 /*+ MAX_EXECUTION_TIME(1) */")
    assert "MAX_EXECUTION_TIME" not in sql.upper()
    assert sql == "SELECT 1"


def test_comments_are_stripped_from_the_executed_sql(validator: QueryValidator):
    sql = validator.validate("/* a comment */ SELECT id FROM customers -- trailing")
    assert "comment" not in sql
    assert "trailing" not in sql
    assert "SELECT id FROM customers" in sql


def test_comment_mentioning_forbidden_function_is_allowed(validator: QueryValidator):
    sql = validator.validate("SELECT id FROM customers /* pg_sleep(10) */")
    assert "pg_sleep" not in sql


def test_invalid_sql_is_rejected(validator: QueryValidator):
    with pytest.raises(QueryValidationError, match="Invalid or unsupported SQL"):
        validator.validate("SELECT FROM WHERE ORDER BY")


def test_unbalanced_quote_is_rejected(validator: QueryValidator):
    with pytest.raises(QueryValidationError):
        validator.validate("SELECT 'unterminated FROM customers")


def test_select_with_subquery_is_allowed(validator: QueryValidator):
    sql = validator.validate(
        "SELECT name FROM customers WHERE id IN (SELECT customer_id FROM orders)"
    )
    assert "customers" in sql


def test_select_with_cte_is_allowed(validator: QueryValidator):
    sql = validator.validate(
        "WITH totals AS (SELECT customer_id, SUM(total) AS s FROM orders "
        "GROUP BY customer_id) SELECT customer_id, s FROM totals"
    )
    assert "WITH" in sql.upper()


# --------------------------------------------------------------------------
# Duplicate column names
# --------------------------------------------------------------------------
def test_duplicate_column_names_pass_validation(validator: QueryValidator):
    """Validation is structural only - duplicates are caught at execution.

    The validator must not silently rewrite the projection, otherwise the
    executed statement would differ from what the model asked for.
    """
    sql = validator.validate(
        "SELECT c.id, o.id FROM customers c JOIN orders o ON o.customer_id = c.id"
    )
    assert sql.count("id") >= 2


def test_duplicate_column_names_are_rejected_by_the_execution_pipeline(
    validator: QueryValidator, db_manager
):
    """End-to-end check: a duplicated projection never reaches the caller."""
    from database.query_executor import QueryExecutionError, QueryExecutor

    executor = QueryExecutor(db_manager)
    with pytest.raises(QueryExecutionError, match="Duplicate column names"):
        executor.execute(
            "SELECT c.id, o.id FROM customers c JOIN orders o ON o.customer_id = c.id"
        )


# --------------------------------------------------------------------------
# MySQL specific hardening
# --------------------------------------------------------------------------
def test_mysql_executable_comment_is_rejected():
    mysql = QueryValidator("mysql")
    with pytest.raises(QueryValidationError, match="not allowed"):
        mysql.validate("SELECT /*! UNION */ 1")


def test_mysql_variable_assignment_is_rejected():
    mysql = QueryValidator("mysql")
    with pytest.raises(QueryValidationError, match="not allowed"):
        mysql.validate("SELECT 1; SET @x := 1")


def test_mysql_hint_is_rejected():
    mysql = QueryValidator("mysql")
    with pytest.raises(QueryValidationError, match="not allowed"):
        mysql.validate("SELECT /*+ MAX_EXECUTION_TIME(1000) */ 1")
