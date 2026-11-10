# 파일 역할: 결제 데이터와 상태 변경 규칙을 관리한다. 외부 통신과 DB 저장은 하지 않으며 검증된 결과를 전달받아 반영한다.

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from payments.domain.enums import PaymentRecoveryStatus, PaymentStatus
from payments.domain.exceptions import (
    InvalidAmountException,
    PaymentKeyNotFoundException,
    PaymentStatusException,
)


# 결제에서 필요한 예매 ID·축제명만 담는다. 예매 전체의 업무 동작을 결제 엔티티에 끌어오지 않는다.
@dataclass(frozen=True)
class ReservationInfo:
    reservation_id: int
    festival_name: str


# 저장 가능한 결제 이력 한 건을 감싼다. 토스 어댑터에서 민감한 원문 필드를 제외한 결과를 전달받는다.
@dataclass(frozen=True)
class PaymentLog:
    value: dict[str, object]


# 결제 한 번의 시도를 표현한다. 상태와 시각이 모순되지 않도록 메서드를 통해 변경한다.
@dataclass
class Payment:
    reservation: ReservationInfo
    amount: int
    status: PaymentStatus = PaymentStatus.READY
    payment_id: int | None = None
    paid_at: datetime | None = None
    payment_key: str | None = None
    failed_reason: str | None = None
    canceled_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # 최초 생성에는 수정 이력이 없다. 상태가 바뀌면 각 도메인 메서드에서 시각을 기록한다.
    updated_at: datetime | None = None
    # default_factory는 결제 객체마다 별도 목록을 만든다. 다른 결제와 이력이 공유되지 않는다.
    payment_log: list[PaymentLog] = field(default_factory=list)
    # 주문번호는 우리 서버가 결제 시도별로 만든다. payment_key는 결제창 인증 후 토스에서 받는다.
    order_id: str = field(default_factory=lambda: uuid4().hex)
    method: str | None = None
    webhook_secret_hash: str | None = field(default=None, repr=False)
    processed_deposit_events: list[str] = field(default_factory=list, repr=False)
    # DB 저장 당시 행을 비교할 메모리용 표식이다. ERD의 새 컬럼으로 저장하지 않는다.
    persistence_token: str | None = field(default=None, repr=False, compare=False)
    # 복구 요청은 기존 payment_log 메타데이터에 저장한다. 환불계좌 원문은 보관하지 않는다.
    recovery_status: PaymentRecoveryStatus | None = None
    recovery_error: str | None = None
    cancellation_reason: str | None = None
    virtual_account_due_at: datetime | None = None

    # 양의 정수 금액만 허용하고 READY 상태의 새 결제를 만든다. DB 저장은 호출자가 수행한다.
    @classmethod
    def create(cls, reservation_id: int, festival_name: str, amount: int) -> "Payment":
        if type(amount) is not int or amount <= 0:
            raise InvalidAmountException
        return cls(
            reservation=ReservationInfo(reservation_id, festival_name), amount=amount
        )

    # 금액이 저장값과 같고 현재 상태·결제 키가 승인 가능한 조합인지 확인한다. 상태는 아직 변경하지 않는다.
    def ensure_approvable(self, payment_key: str, amount: int) -> None:
        """외부 승인 호출 전에 금액과 상태를 검증한다."""
        if type(amount) is not int or amount != self.amount or amount <= 0:
            raise InvalidAmountException
        if not payment_key or not payment_key.strip():
            raise PaymentKeyNotFoundException
        if self.status not in (PaymentStatus.READY, PaymentStatus.IN_PROGRESS):
            raise PaymentStatusException
        if self.payment_key is not None and self.payment_key != payment_key:
            raise PaymentStatusException(
                "다른 결제 키로 진행 중인 결제를 변경할 수 없습니다."
            )

    # 사전 검증 후 IN_PROGRESS와 결제 키를 기록해 승인 진행 중임을 표시한다.
    def start_approval(self, payment_key: str, amount: int) -> None:
        self.ensure_approvable(payment_key, amount)
        self.payment_key = payment_key
        self.status = PaymentStatus.IN_PROGRESS
        self.updated_at = datetime.now(UTC)

    # 검증된 승인 결과를 반영한다. 가상계좌 발급인 입금 대기와 실제 결제 완료를 구분한다.
    def approve(
        self,
        payment_key: str,
        amount: int,
        status: PaymentStatus,
        paid_at: datetime | None,
        log: PaymentLog,
        method: str | None = None,
        webhook_secret_hash: str | None = None,
    ) -> None:
        """입금 대기와 실제 결제 완료를 구분해 승인 결과를 반영한다."""
        self._validate_log(log)
        self.ensure_approvable(payment_key, amount)
        if status not in (PaymentStatus.WAITING_FOR_DEPOSIT, PaymentStatus.DONE):
            raise PaymentStatusException
        if status == PaymentStatus.DONE and paid_at is None:
            raise PaymentStatusException("결제 완료에는 입금 완료 시각이 필요합니다.")
        if status == PaymentStatus.WAITING_FOR_DEPOSIT and paid_at is not None:
            raise PaymentStatusException("입금 대기에는 입금 완료 시각이 없습니다.")
        self.payment_key = payment_key
        self.status = status
        self.paid_at = paid_at
        self.method = method
        self.webhook_secret_hash = webhook_secret_hash
        self.failed_reason = None
        self.add_payment_log(log)
        self.updated_at = datetime.now(UTC)

    # 완료 또는 입금 대기 상태에서만 취소에 필요한 결제 키를 반환한다.
    def ensure_cancelable(self) -> str:
        """취소 상태를 확인하고 외부 호출에 사용할 키를 반환한다."""
        if self.status not in (PaymentStatus.DONE, PaymentStatus.WAITING_FOR_DEPOSIT):
            raise PaymentStatusException
        if not self.payment_key:
            raise PaymentKeyNotFoundException
        return self.payment_key

    # 취소 가능 여부를 확인하고 CANCELED·취소 시각·이력을 갱신한다. 외부 취소 요청 자체는 하지 않는다.
    def cancel(self, canceled_at: datetime, log: PaymentLog) -> None:
        self._validate_log(log)
        self.ensure_cancelable()
        self.status = PaymentStatus.CANCELED
        self.canceled_at = canceled_at
        self.add_payment_log(log)
        self.updated_at = datetime.now(UTC)

    # 실패가 확정된 경우에만 ABORTED와 사유를 기록한다. 네트워크 오류만으로 호출하면 안 된다.
    def fail(self, reason: str) -> None:
        """실패가 확정된 경우에만 호출한다. 통신 오류만으로 실패를 확정하지 않는다."""
        if self.status in (
            PaymentStatus.DONE,
            PaymentStatus.CANCELED,
            PaymentStatus.ABORTED,
            PaymentStatus.EXPIRED,
        ):
            raise PaymentStatusException
        self.status = PaymentStatus.ABORTED
        self.failed_reason = reason
        self.updated_at = datetime.now(UTC)

    # 예약된 내부 메타데이터 키가 없는 정상 이력만 목록 뒤에 추가한다.
    def add_payment_log(self, log: PaymentLog) -> None:
        self._validate_log(log)
        self.payment_log.append(log)

    # 외부 거래 이력에 내부 저장용 _payment_metadata가 섞여 저장 규칙을 덮어쓰는 것을 막는다.
    @staticmethod
    def _validate_log(log: PaymentLog) -> None:
        if "_payment_metadata" in log.value:
            raise ValueError("결제 로그에 예약된 메타데이터 키를 사용할 수 없습니다.")

    # 결제사 재조회 결과의 허용 상태 전이와 필수 시각을 검사한 뒤 필드·이력을 함께 갱신한다.
    def synchronize(
        self,
        *,
        status: PaymentStatus,
        paid_at: datetime | None,
        canceled_at: datetime | None,
        method: str | None,
        webhook_secret_hash: str | None,
        log: PaymentLog,
    ) -> None:
        """알림 본문이 아닌, 결제사 재조회로 확인한 결과만 반영한다."""
        self._validate_log(log)
        if (
            self.status
            in (
                PaymentStatus.CANCELED,
                PaymentStatus.EXPIRED,
                PaymentStatus.ABORTED,
            )
            and status != self.status
        ):
            raise PaymentStatusException(
                "종료된 결제를 이전 상태로 되돌릴 수 없습니다."
            )
        if status not in (
            PaymentStatus.WAITING_FOR_DEPOSIT,
            PaymentStatus.DONE,
            PaymentStatus.CANCELED,
            PaymentStatus.EXPIRED,
            PaymentStatus.ABORTED,
        ):
            raise PaymentStatusException
        if self.status == PaymentStatus.DONE and status not in (
            PaymentStatus.DONE,
            PaymentStatus.CANCELED,
            PaymentStatus.WAITING_FOR_DEPOSIT,
        ):
            raise PaymentStatusException
        if (
            self.status == PaymentStatus.DONE
            and status == PaymentStatus.WAITING_FOR_DEPOSIT
            # 입금 취소 등으로 DONE → 입금 대기 복귀를 인정하는 경우도 가상계좌에 한정한다.
            and method != "가상계좌"
        ):
            raise PaymentStatusException
        if status == PaymentStatus.DONE and paid_at is None:
            raise PaymentStatusException("입금 완료 시각이 필요합니다.")
        if status == PaymentStatus.CANCELED and canceled_at is None:
            raise PaymentStatusException("취소 완료 시각이 필요합니다.")
        if status == PaymentStatus.WAITING_FOR_DEPOSIT and paid_at is not None:
            raise PaymentStatusException
        self.status = status
        self.paid_at = paid_at
        self.canceled_at = canceled_at
        self.method = method
        if webhook_secret_hash is not None:
            self.webhook_secret_hash = webhook_secret_hash
        self.add_payment_log(log)
        self.updated_at = datetime.now(UTC)
