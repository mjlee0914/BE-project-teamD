from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from performances.domain.performance import CANCEL_DEADLINE_BEFORE_START


class PerformanceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=50)
    starts_at: datetime
    ends_at: datetime
    booking_open_at: datetime
    booking_close_at: datetime
    capacity: int = Field(gt=0)
    price: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.starts_at >= self.ends_at:
            raise ValueError("공연 종료 시간은 시작 시간보다 늦어야 합니다.")
        if self.booking_close_at > self.starts_at:
            raise ValueError("예매 종료 시간은 공연 시작 시간보다 늦을 수 없습니다.")
        if self.booking_open_at >= self.booking_close_at:
            raise ValueError("예매 종료 시간은 예매 시작 시간보다 늦어야 합니다.")
        if not (self.booking_open_at <= self.starts_at - CANCEL_DEADLINE_BEFORE_START):
            raise ValueError("예매 시작은 공연 시작 24시간 전보다 먼저 열려야 합니다.")
        return self


# 일정과 수용 인원 수정 가능 (change_schedule, change_capacity)
# 보내지 않은 값은 기존 값으로 채운 뒤 엔티티에서 규칙 3~6을 다시 검증하므로 (규칙 16)
# 이 스키마에는 날짜 검증기를 두지 않는다.
# TODO: 제목·가격 수정은 이후 추가 예정
#   - title: 같은 축제 안 제목 중복 검사 필요 (규칙 20, exists_duplicated_title의 exclude_id 사용)
#   - price: 이미 예매된 건의 결제 금액과 어떻게 맞출지 결정 필요
class PerformanceUpdate(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    booking_open_at: datetime | None = None
    booking_close_at: datetime | None = None
    capacity: int | None = Field(default=None, gt=0)


class PerformanceResponse(BaseModel):
    performance_id: int = Field(validation_alias="id")
    festival_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    booking_open_at: datetime
    booking_close_at: datetime
    cancel_deadline_at: datetime
    capacity: int
    remaining_count: int
    price: int
    status: str
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class AvailabilityResponse(BaseModel):
    performance_id: int
    is_bookable: bool
    status: str
    remaining_count: int
