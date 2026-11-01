
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatabaseToolInput(BaseModel):
    """Validate inputs shared across database tools."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    table_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Name of the table to inspect.",
    )

    schema_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Optional database schema name.",
    )

    query: str | None = Field(
        default=None,
        min_length=1,
        max_length=10000,
        description="SQL query to execute.",
    )

    @model_validator(mode="after")
    def validate_input_combination(self):
        """
        Validate combinations of database tool inputs.

        Returns:
            DatabaseToolInput: Validated tool inputs.
        """
        if self.query is not None and (
            self.table_name is not None or self.schema_name is not None
        ):
            raise ValueError(
                "SQL query cannot be combined with table_name or schema."
            )

        return self
