from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    status: Literal["success", "failed"]
    data: QueryData | None = None
    error: str | None = None
    
    @model_validator(mode="after")
    def validate_execution(self):

        if self.status == "success":
            if not self.executed_sql or self.data is None:
                raise ValueError(
                    "Successful execution requires SQL and data."
                )

            if self.error is not None:
                raise ValueError(
                    "Successful execution cannot contain an error."
                )

        elif self.status == "failed":
            if self.data is not None:
                raise ValueError(
                    "Failed execution cannot contain data."
                )

            if not self.error:
                raise ValueError(
                    "Failed execution requires an error message."
                )

        return self



class AnalysisMetadata(BaseModel):
    
    model_config = ConfigDict(extra="forbid")

    dialect: str = Field(min_length=1)
    tools_used: list[str] = Field(default_factory=list)


class AnalysisResponse(BaseModel):

    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "no_data", "failed"]
    answer: str | None = None
    queries: list[SQLExecutionResult]
    metadata: AnalysisMetadata
    error: str | None = None
