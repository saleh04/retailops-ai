from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class ConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr):
        if not value.get_secret_value().strip():
            raise ValueError("Database URL cannot be empty.")
        return value


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    question: str = Field(min_length=1)
