from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payments.domain.entities import Payment
from payments.infrastructure.models import PaymentModel


class PaymentRepository:
    """결제 저장·조회와 도메인 변환을 담당합니다. 커밋은 서비스가 수행합니다."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_id(
        self, payment_id: int, *, for_update: bool = False
    ) -> Payment | None:
        statement = select(PaymentModel).where(PaymentModel.id == payment_id)
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        model = await self.db.scalar(statement)
        return self._to_domain(model) if model is not None else None

    async def find_by_reservation_id(self, reservation_id: int) -> list[Payment]:
        """같은 예매의 결제 시도들을 결제 ID 오름차순으로 조회합니다."""
        statement = (
            select(PaymentModel)
            .where(PaymentModel.reservation_id == reservation_id)
            .order_by(PaymentModel.id)
        )
        models = await self.db.scalars(statement)
        return [self._to_domain(model) for model in models.all()]

    async def save(self, payment: Payment) -> Payment:
        """새 결제는 추가하고, 기존 결제는 상태 정보를 갱신합니다."""
        if payment.id is None:
            model = PaymentModel(
                reservation_id=payment.reservation_id,
                method=payment.method,
                amount=payment.amount,
            )
            self.db.add(model)
        else:
            model = await self.db.get(PaymentModel, payment.id)
            if model is None:
                raise LookupError("저장할 결제 기록이 존재하지 않습니다.")
            if (model.reservation_id, model.method, model.amount) != (
                payment.reservation_id,
                payment.method,
                payment.amount,
            ):
                raise ValueError(
                    "기존 결제의 예매 ID, 결제 수단, 금액은 변경할 수 없습니다."
                )

        model.status = payment.status
        model.payment_key = payment.payment_key
        model.paid_at = payment.paid_at
        model.canceled_at = payment.canceled_at
        model.fail_reason = payment.fail_reason
        # payment_log는 별도 로그 작업에서 관리하므로 상태 저장 시 덮어쓰지 않습니다.
        await self.db.flush()
        await self.db.refresh(model)
        payment.id = model.id
        payment.created_at = model.created_at
        payment.updated_at = model.updated_at
        return payment

    @staticmethod
    def _to_domain(model: PaymentModel) -> Payment:
        return Payment.restore(
            id=model.id,
            reservation_id=model.reservation_id,
            method=model.method,
            amount=model.amount,
            status=model.status,
            payment_key=model.payment_key,
            paid_at=model.paid_at,
            canceled_at=model.canceled_at,
            fail_reason=model.fail_reason,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
