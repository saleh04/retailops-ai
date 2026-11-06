from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Status = Literal["success", "failed"]


def _check_status_fields(status: Status, data: Any,
                        error: str | None, label: str) -> None:

    if status == "success":
        if error is not None:
            raise ValueError(f"Successful {label} cannot contain an error.")
    elif data is not None:
        raise ValueError(f"Failed {label} cannot contain data.")
    elif not error:
        raise ValueError(f"Failed {label} requires an error message.")


class QueryData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    truncated: bool


class SQLExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: str = Field(min_length=1)
    requested_sql: str = Field(min_length=1)
    executed_sql: str | None = None
    status: Status
    data: QueryData | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_execution(self):
        if self.status == "success" and (not self.executed_sql or self.data is None):
            raise ValueError("Successful execution requires SQL and data.")

        _check_status_fields(self.status, self.data, self.error, "execution")
        return self


class SchemaToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: str = Field(min_length=1)
    tool_name: Literal["list_tables", "describe_table"]
    status: Status
    data: list[str] | dict[str, Any] | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_result(self):
        if self.status == "success" and self.data is None:
            raise ValueError("Successful schema inspection requires data.")

        _check_status_fields(self.status, self.data, self.error, "schema inspection")

        return self


class AnalysisMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dialect: str = Field(min_length=1)
    tools_used: list[str] 


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "no_data", "failed"]
    answer: str | None = None
    queries: list[SQLExecutionResult]
    metadata: AnalysisMetadata
    schema_results: list[SchemaToolResult] 
    error: str | None = None