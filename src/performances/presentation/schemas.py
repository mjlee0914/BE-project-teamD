from datetime import datetime
from pydantic import BaseModel, Field, model_validator, ConfigDict


class PerformanceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=50)
    starts_at: datetime
    ends_at: datetime
    booking_open_at: datetime
    booking_close_at: datetime
    cancellation_deadline_at: datetime
    capacity: int = Field(gt=0)
    max_tickets_per_user: int = Field(ge=1, le=2)
    price: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.starts_at >= self.ends_at:
            raise ValueError("공연 종료 시간은 시작 시간보다 늦어야 합니다.")
        if self.booking_close_at > self.starts_at:
            raise ValueError("예매 종료 시간은 공연 시작 시간보다 늦을 수 없습니다.")
        if self.booking_open_at > self.booking_close_at:
            raise ValueError("예매 종료 시간은 예매 시작 시간보다 늦어야 합니다.")
        if self.cancellation_deadline_at < self.booking_open_at:
            raise ValueError("취소 마감 시간은 예매 시작 시간보다 빠를 수 없습니다.")
        if self.cancellation_deadline_at > self.starts_at:
            raise ValueError("취소 마감 시간은 공연 시작 시간보다 늦을 수 없습니다.")
        return self


class PerformanceUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=50)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    booking_open_at: datetime | None = None
    booking_close_at: datetime | None = None
    cancellation_deadline_at: datetime | None = None
    capacity: int | None = Field(default=None, gt=0)
    max_tickets_per_user: int | None = Field(default=None, ge=1, le=2)
    price: int | None = Field(default=None, gt=0)


class PerformanceResponse(BaseModel):
    performance_id: int = Field(validation_alias="id")
    festival_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    booking_open_at: datetime
    booking_close_at: datetime
    cancellation_deadline_at: datetime
    capacity: int
    remaining_count: int
    max_tickets_per_user: int
    price: int
    status: str
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
