"""Models for reading-app access users."""

from pydantic import BaseModel, Field, field_validator


class AccessUserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    note: str = Field("", max_length=200)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("用户名称不能为空")
        return value

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return value.strip()


class AccessUserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    note: str | None = Field(None, max_length=200)
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("用户名称不能为空")
        return value

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None
