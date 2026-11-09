# 파일 역할: 결제사·소유권 검사의 계약과 결과 데이터다. 도메인이 httpx나 SQLAlchemy를 직접 알 필요가 없게 한다.

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from payments.domain.entities import PaymentLog
from payments.domain.enums import PaymentStatus


# 외부 승인 응답에서 도메인에 필요한 상태·시각·이력·결제 수단만 추려 전달한다.
@dataclass(frozen=True)
class PaymentApprovalResult:
    status: PaymentStatus
    paid_at: datetime | None
    log: PaymentLog
    method: str | None = None
    webhook_secret_hash: str | None = None


# 결제사에 재조회한 현재 결과다. 주문 식별과 상태 동기화에 필요한 정보를 함께 전달한다.
@dataclass(frozen=True)
class PaymentSnapshot:
    payment_key: str
    order_id: str
    amount: int
    status: PaymentStatus
    paid_at: datetime | None
    cancelled_at: datetime | None
    log: PaymentLog
    method: str | None = None
    webhook_secret_hash: str | None = None


# 외부 전액 취소가 완료된 시각과 저장 가능한 이력을 반환하는 데이터다.
@dataclass(frozen=True)
class PaymentCancellationResult:
    cancelled_at: datetime
    log: PaymentLog


# 가상계좌 환불에 필요한 은행·계좌번호·예금주를 전달한다. DB의 새 테이블이나 컬럼은 아니다.
@dataclass(frozen=True)
class RefundAccount:
    bank: str
    account_number: str
    holder_name: str


# 예매 소유권을 확인하는 계약이다. 구현체가 회원 ID와 예매 소유자를 비교한다.
class PaymentAccessChecker(ABC):
    # 정상 소유자이면 통과하고, 없거나 다른 회원의 예매이면 접근 예외를 발생시키는 계약이다.
    @abstractmethod
    async def ensure_owner(self, reservation_id: int, user_id: int) -> None:
        """예매 소유자가 아니거나 예매가 없으면 접근을 거절한다."""


# 승인·조회·취소에 대한 결제사 계약이다. 실제 토스 HTTP 구현과 모의 구현을 같은 방식으로 사용할 수 있다.
class PaymentProcessor(ABC):
    # 결제 키로 외부 결제사의 최신 상태를 읽어 PaymentSnapshot으로 반환하도록 정의한다.
    @abstractmethod
    async def retrieve(self, payment_key: str) -> PaymentSnapshot:
        """결제사에 저장된 최신 결제 결과를 조회한다."""

    # 결제 키·서버 주문번호·검증된 금액으로 승인하고 PaymentApprovalResult를 반환하도록 정의한다.
    @abstractmethod
    async def approve(
        self, payment_key: str, order_id: str, amount: int
    ) -> PaymentApprovalResult:
        """승인 결과 반환. 예상한 연동 실패는 PaymentProcessingError로 전달한다."""

    # 전액 취소 결과를 반환하는 계약이다. 필요한 경우 환불 계좌도 함께 전달받는다.
    @abstractmethod
    async def cancel(
        self,
        payment_key: str,
        *,
        reason: str = "고객 요청",
        refund_account: RefundAccount | None = None,
    ) -> PaymentCancellationResult:
        """취소 결과 반환. 예상한 연동 실패는 PaymentProcessingError로 전달한다."""
