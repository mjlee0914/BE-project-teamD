from dataclasses import dataclass, field
from datetime import datetime
from payments.domain.enum import PaymentStatus


@dataclass
class Payment:
    """가상 결제 한 번의 시도와 상태 변경 규칙."""

    reservation_id: int
    method: str
    amount: int
    id: int | None = field(default=None, init=False)
    created_at: datetime | None = field(default=None, init=False)
    updated_at: datetime | None = field(default=None, init=False)
    status: PaymentStatus = field(default=PaymentStatus.READY, init=False)
    payment_key: str | None = field(default=None, init=False)
    paid_at: datetime | None = field(default=None, init=False)
    canceled_at: datetime | None = field(default=None, init=False)
    fail_reason: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if type(self.reservation_id) is not int or self.reservation_id <= 0:
            raise ValueError("예매 ID는 양의 정수여야 합니다.")
        self._validate_text(self.method, "결제 수단")
        self._validate_amount(self.amount)

    @classmethod
    def restore(
        cls,
        *,
        id: int,
        reservation_id: int,
        method: str,
        amount: int,
        status: PaymentStatus,
        payment_key: str | None = None,
        paid_at: datetime | None = None,
        canceled_at: datetime | None = None,
        fail_reason: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> "Payment":
        """저장된 상태를 검증하며 복원합니다. DB나 SQLAlchemy에는 의존하지 않습니다."""
        if type(id) is not int or id <= 0:
            raise ValueError("결제 ID는 양의 정수여야 합니다.")
        status = PaymentStatus(status)
        payment = cls(reservation_id=reservation_id, method=method, amount=amount)

        if status in (PaymentStatus.PAID, PaymentStatus.CANCELED):
            if payment_key is None or paid_at is None or fail_reason is not None:
                raise ValueError("승인된 결제의 저장 정보가 올바르지 않습니다.")
            payment.approve(
                requested_amount=amount, payment_key=payment_key, now=paid_at
            )
            if status == PaymentStatus.CANCELED:
                if canceled_at is None:
                    raise ValueError("취소된 결제에는 취소 시각이 필요합니다.")
                payment.cancel(now=canceled_at)
            elif canceled_at is not None:
                raise ValueError("승인 상태의 결제에는 취소 시각이 없어야 합니다.")
        else:
            if any(value is not None for value in (payment_key, paid_at, canceled_at)):
                raise ValueError("미승인 결제에는 승인·취소 정보가 없어야 합니다.")
            if status == PaymentStatus.FAILED:
                if fail_reason is None:
                    raise ValueError("실패한 결제에는 실패 사유가 필요합니다.")
                payment.fail(fail_reason)
            elif fail_reason is not None:
                raise ValueError("대기 상태의 결제에는 실패 사유가 없어야 합니다.")

        for value in (created_at, updated_at):
            if value is not None:
                cls._validate_datetime(value)
        payment.id = id
        payment.created_at = created_at
        payment.updated_at = updated_at
        return payment

    def approve(
        self, *, requested_amount: int, payment_key: str, now: datetime
    ) -> None:
        """READY 결제만 저장된 금액과 비교하여 승인합니다."""
        self._require_status(PaymentStatus.READY)
        self._validate_amount(requested_amount)
        if requested_amount != self.amount:
            raise ValueError("요청한 결제 금액이 예매의 결제 금액과 일치하지 않습니다.")
        self._validate_text(payment_key, "결제 승인 키")
        self._validate_datetime(now)

        self.payment_key = payment_key
        self.paid_at = now
        self.status = PaymentStatus.PAID

    def fail(self, reason: str) -> None:
        """READY 결제를 실패 처리합니다. 재시도는 새 결제 객체로 수행합니다."""
        self._require_status(PaymentStatus.READY)
        self._validate_text(reason, "결제 실패 사유")

        self.fail_reason = reason
        self.status = PaymentStatus.FAILED

    def cancel(self, *, now: datetime) -> None:
        """승인된 결제를 취소합니다. 예매의 취소 가능 여부는 서비스에서 확인합니다."""
        self._require_status(PaymentStatus.PAID)
        self._validate_datetime(now)
        if self.paid_at is None or now < self.paid_at:
            raise ValueError("결제 취소 시각은 승인 시각보다 이를 수 없습니다.")

        self.canceled_at = now
        self.status = PaymentStatus.CANCELED

    def _require_status(self, expected: PaymentStatus) -> None:
        if self.status != expected:
            raise ValueError(
                f"현재 결제 상태({self.status.value})에서는 처리할 수 없습니다."
            )

    @staticmethod
    def _validate_amount(amount: int) -> None:
        if type(amount) is not int or amount < 0:
            raise ValueError("결제 금액은 0 이상의 정수여야 합니다.")

    @staticmethod
    def _validate_text(value: str, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label}은(는) 비어 있을 수 없습니다.")

    @staticmethod
    def _validate_datetime(value: datetime) -> None:
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError("시간대 정보가 포함된 datetime이 필요합니다.")
