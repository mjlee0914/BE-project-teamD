# 파일 역할: 결제 요청값의 형식과 외부 응답을 정의한다. 도메인 객체 전체를 그대로 클라이언트에 노출하지 않는다.

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from payments.domain.entities import Payment
from payments.domain.enums import PaymentStatus
from payments.domain.service import RefundAccount


# 결제 키는 공백 없는 문자열, 금액은 엄격한 양의 정수만 허용한다. 알 수 없는 추가 필드는 거절한다.
class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_key: str = Field(min_length=1, max_length=200, pattern=r"^[!-~]+$")
    amount: int = Field(gt=0, strict=True)


# 저장된 결제 키를 기본으로 쓰되, 복구 요청에서 명시적인 키를 전달할 수 있게 한다.
class ReconciliationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_key: str | None = Field(
        default=None, min_length=1, max_length=200, pattern=r"^[!-~]+$"
    )


# HTTP 입력의 은행·계좌번호·예금주 형식을 검사한다. 실제 계좌 존재 여부를 조회하는 검증은 아니다.
class RefundAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    bank: str = Field(min_length=1, max_length=10)
    account_number: str = Field(pattern=r"^[0-9]{1,20}$")
    holder_name: str = Field(min_length=1, max_length=60)

    # HTTP 검증 객체를 도메인 RefundAccount로 바꿔 응용 서비스가 Pydantic에 의존하지 않게 한다.
    def to_domain(self) -> RefundAccount:
        return RefundAccount(self.bank, self.account_number, self.holder_name)


# 취소 사유와 선택적 환불 계좌를 받는다. 계좌의 필수 여부는 결제 상태·수단을 아는 서비스가 판단한다.
class CancellationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=200)
    refund_account: RefundAccountRequest | None = None


# 상태·금액·주문번호·시각처럼 공개할 필드만 정의한다. 내부 로그·비밀값·결제 키는 제외한다.
class PaymentResponse(BaseModel):
    payment_id: int
    reservation_id: int
    order_id: str
    status: PaymentStatus
    amount: int
    method: str | None
    paid_at: datetime | None
    canceled_at: datetime | None
    created_at: datetime
    updated_at: datetime | None

    # 엔티티 필드를 명시적으로 선택해 응답을 만든다. 엔티티에 필드가 추가되어도 자동으로 외부에 노출되지 않는다.
    @classmethod
    def from_domain(cls, payment: Payment) -> "PaymentResponse":
        # 로그·실패 원문·payment_key·환불 계좌는 응답에 포함하지 않는다.
        return cls(
            payment_id=payment.payment_id,
            reservation_id=payment.reservation.reservation_id,
            order_id=payment.order_id,
            status=payment.status,
            amount=payment.amount,
            method=payment.method,
            paid_at=payment.paid_at,
            canceled_at=payment.canceled_at,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )
