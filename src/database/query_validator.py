from sqlglot import exp, parse
from sqlglot.errors import ErrorLevel, SqlglotError


class QueryValidationError(Exception):
    pass

class QueryValidator:
    
    MAX_QUERY_LENGTH = 10_000

    DIALECT_MAP = {  # noqa: RUF012
        "sqlite": "sqlite",
        "postgresql": "postgres",
        "mysql": "mysql",
        "mariadb": "mysql",
        "mssql": "tsql",
    }

    ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)

    FORBIDDEN_NODES = (
        exp.Insert, exp.Update, exp.Delete,
        exp.Merge, exp.Create, exp.Alter,
        exp.Drop, exp.Command, exp.Into,
        exp.Lock, exp.Hint, exp.JoinHint,
        exp.WithTableHint, exp.IndexTableHint,
        exp.QueryOption,
    )

    BLOCKED_FUNCTIONS = frozenset({
        "pg_sleep", "pg_read_file", "pg_ls_dir", "pg_ls_logdir",
        "pg_read_binary_file", "lo_import", "lo_export", "dblink",
        "set_config", "pg_terminate_backend", "pg_cancel_backend",
        "nextval", "setval", "sleep", "benchmark", "load_file",
        "get_lock", "release_lock", "load_extension", "openrowset",
        "openquery", "opendatasource", "xp_cmdshell",
        "randomblob", "zeroblob",
    })

    def __init__(self, database: str) -> None:
        
        try:
            self._dialect = self.DIALECT_MAP[database]
        except KeyError:
            raise QueryValidationError("Unsupported SQL dialect.") from None

    def validate(self, query: str) -> str:
        
        if not isinstance(query, str) or not query.strip():
            raise QueryValidationError("SQL query cannot be empty.")
        if len(query) > self.MAX_QUERY_LENGTH:
            raise QueryValidationError("SQL query is too long.")

        # MySQL executable comments / optimizer hints can change the semantics
        # or override the server-side statement timeout.
        if self._dialect == "mysql" and ("/*!" in query or "/*+" in query or ":=" in query):
            raise QueryValidationError("SQL hints, variable assignments and executable comments are not allowed.")

        try:
            statements = parse(query, read=self._dialect, error_level=ErrorLevel.RAISE)
            if len(statements) != 1 or statements[0] is None:
                raise QueryValidationError("Exactly one SQL statement is allowed.")

            statement = statements[0]
            if not isinstance(statement, self.ALLOWED_ROOTS):
                raise QueryValidationError("Only SELECT queries are allowed.")

            for node in statement.walk():
                if isinstance(node, self.FORBIDDEN_NODES):
                    raise QueryValidationError("Query contains a forbidden operation.")

                if isinstance(node, exp.Func):
                    name = node.name if isinstance(node, exp.Anonymous) else node.sql_name()
                    if name.lower() in self.BLOCKED_FUNCTIONS:
                        raise QueryValidationError("Query uses a forbidden function.")

            # Execute exactly the SQL produced from the AST we inspected.
            return statement.sql(
                dialect=self._dialect,
                comments=False,
                unsupported_level=ErrorLevel.RAISE,
            )

        except (SqlglotError, RecursionError):
            raise QueryValidationError("Invalid or unsupported SQL statement.") from None