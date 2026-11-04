from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from payments.domain.entities import Payment, PaymentStatus
from payments.infrastructure.repositories import PaymentRepository
from payments.infrastructure.reservation_repository import ReservationPaymentRepository


def utc_now() -> datetime:
    return datetime.now(UTC)


class PaymentService:
    """가상 결제 처리. 예매 확정·티켓 발급은 아직 연결하지 않은 단계입니다."""

    def __init__(
        self, db: AsyncSession, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self.db = db
        self.payments = PaymentRepository(db)
        self.reservations = ReservationPaymentRepository(db)
        self.clock = clock

    async def pay(
        self,
        *,
        reservation_id: int,
        user_id: int,
        method: str,
        requested_amount: int,
        simulate_failure: bool = False,
    ) -> Payment:
        """소유자와 예매 조건을 검사한 뒤 승인 또는 실패 기록을 커밋합니다."""
        try:
            if type(simulate_failure) is not bool:
                raise ValueError("가상 결제 실패 여부는 bool이어야 합니다.")
            # 같은 예매의 결제 요청을 직렬화합니다. 잠금은 커밋/롤백 때 해제됩니다.
            reservation = await self.reservations.find_by_id(
                reservation_id, for_update=True
            )
            if reservation is None:
                raise LookupError("예매가 존재하지 않습니다.")
            # 잠금을 기다린 시간까지 반영하여 만료 여부를 판단합니다.
            now = self.clock()
            reservation.ensure_payable(user_id, now)
            attempts = await self.payments.find_by_reservation_id(reservation_id)
            if any(
                p.status in (PaymentStatus.PAID, PaymentStatus.CANCELED)
                for p in attempts
            ):
                raise ValueError("이미 승인된 결제 기록이 있는 예매입니다.")

            payment = Payment(
                reservation_id=reservation.id,
                method=method,
                amount=reservation.final_price,
            )
            if simulate_failure:
                payment.fail("가상 결제 승인 실패")
            else:
                try:
                    payment.approve(
                        requested_amount=requested_amount,
                        payment_key=f"mock-{uuid4()}",
                        now=now,
                    )
                except ValueError as exc:
                    # 업무상 승인 실패는 기록으로 남깁니다. DB 오류는 아래에서 롤백합니다.
                    payment.fail(str(exc))
            await self.payments.save(payment)
            await self.db.commit()
            return payment
        except Exception:
            await self.db.rollback()
            raise

    async def get_payment(self, *, payment_id: int, user_id: int) -> Payment:
        payment = await self.payments.find_by_id(payment_id)
        if payment is None:
            raise LookupError("결제 기록이 존재하지 않습니다.")
        reservation = await self.reservations.find_by_id(payment.reservation_id)
        if reservation is None:
            raise LookupError("예매가 존재하지 않습니다.")
        reservation.ensure_owner(user_id)
        return payment

    async def cancel(self, *, payment_id: int, user_id: int) -> Payment:
        """예매가 이미 취소된 경우에만 승인된 결제를 취소합니다."""
        try:
            payment = await self.payments.find_by_id(payment_id)
            if payment is None:
                raise LookupError("결제 기록이 존재하지 않습니다.")
            # 결제 생성과 같은 순서로 예매를 먼저 잠가 잠금 순서를 통일합니다.
            reservation = await self.reservations.find_by_id(
                payment.reservation_id, for_update=True
            )
            if reservation is None:
                raise LookupError("예매가 존재하지 않습니다.")
            reservation.ensure_canceled(user_id)
            payment = await self.payments.find_by_id(payment_id, for_update=True)
            if payment is None:
                raise LookupError("결제 기록이 존재하지 않습니다.")
            if payment.reservation_id != reservation.id:
                raise ValueError("결제와 예매의 연결 정보가 일치하지 않습니다.")
            payment.cancel(now=self.clock())
            await self.payments.save(payment)
            await self.db.commit()
            return payment
        except Exception:
            await self.db.rollback()
            raise
