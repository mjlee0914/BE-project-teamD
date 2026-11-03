from datetime import date, datetime
from pydantic import BaseModel, Field, model_validator, ConfigDict


class FestivalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    venue: str = Field(min_length=1, max_length=50)
    description: str | None = None
    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.starts_on >= self.ends_on:
            raise ValueError("페스티벌 종료일은 시작일보다 늦어야 합니다.")

        return self


class FestivalUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    venue: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    description: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self):
        if (
            self.starts_on is not None
            and self.ends_on is not None
            and self.starts_on >= self.ends_on
        ):
            raise ValueError("페스티벌 종료일은 시작일보다 늦어야 합니다.")
        return self


class FestivalResponse(BaseModel):
    festival_id: int = Field(validation_alias="id")
    name: str
    venue: str
    description: str | None
    starts_on: date
    ends_on: date
    created_at: datetime
    updated_at: datetime | None
    canceled_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
