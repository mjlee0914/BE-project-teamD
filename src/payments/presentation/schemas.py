from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from payments.domain.entities import PaymentStatus


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reservation_id: int = Field(strict=True, gt=0, description="결제할 예매 ID")
    method: str = Field(strict=True, min_length=1, description="결제 수단. 예: CARD")
    requested_amount: int = Field(
        strict=True,
        ge=0,
        description="요청 금액. 서버가 예매의 final_price와 비교합니다.",
    )
    simulate_failure: bool = Field(
        default=False, strict=True, description="가상 결제 실패 시연용 옵션"
    )


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(gt=0, description="결제 ID")
    reservation_id: int = Field(gt=0, description="예매 ID")
    status: PaymentStatus
    method: str
    amount: int = Field(ge=0, description="예매의 final_price를 기준으로 저장한 금액")
    payment_key: str | None
    paid_at: datetime | None
    canceled_at: datetime | None
    fail_reason: str | None
    created_at: datetime | None
    updated_at: datetime | None
