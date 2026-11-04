from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payments.domain.reservation import ReservationPaymentInfo
from reservations.infrastructure.models import Reservation


class ReservationPaymentRepository:
    """팀의 예매 모델을 읽어 결제용 정보로 변환합니다. 예매를 변경하지 않습니다."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_id(
        self, reservation_id: int, *, for_update: bool = False
    ) -> ReservationPaymentInfo | None:
        statement = select(Reservation).where(Reservation.id == reservation_id)
        if for_update:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        model = await self.db.scalar(statement)
        if model is None:
            return None
        return ReservationPaymentInfo(
            id=model.id,
            user_id=model.user_id,
            status=model.status,
            final_price=model.final_price,
            expires_at=model.expires_at,
        )
