# 파일 역할: 예매의 user_id를 조회해 결제 요청자의 소유권을 검사한다. 로그인 성공만으로 타인의 결제에 접근할 수는 없다.

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payments.domain.service import (
    PaymentAccessChecker,
    PaymentCreationContext,
    PaymentCreationContextProvider,
)
from reservations.infrastructure.models import Reservation as ReservationModel
from shared.core.exceptions import ForbiddenException


# 결제의 연결 예매를 기준으로 소유자를 검사한다. 사용자 입력의 소유자 정보는 신뢰하지 않는다.
class SQLAlchemyPaymentAccessChecker(PaymentAccessChecker):
    # 외부에서 전달받은 의존성을 보관한다. 여기서 DB 연결이나 업무 처리를 새로 시작하지 않는다.
    def __init__(self, session: AsyncSession):
        self._session = session

    # reservations.user_id와 인증된 회원 ID를 비교하고, 존재 여부와 무관하게 권한이 없으면 403을 낸다.
    async def ensure_owner(self, reservation_id: int, user_id: int) -> None:
        result = await self._session.execute(
            select(ReservationModel.user_id).where(
                ReservationModel.id == reservation_id
            )
        )
        owner_id = result.scalar_one_or_none()
        if owner_id is None or owner_id != user_id:
            raise ForbiddenException("본인의 예매에 연결된 결제만 이용할 수 있습니다.")


class SQLAlchemyPaymentCreationContextProvider(PaymentCreationContextProvider):
    """결제 생성 시 DB에서 예매 소유자와 서버 기준 금액을 읽는다."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_context(self, reservation_id: int) -> PaymentCreationContext | None:
        result = await self._session.execute(
            select(ReservationModel)
            .where(ReservationModel.id == reservation_id)
            .execution_options(populate_existing=True)
        )
        reservation = result.scalar_one_or_none()
        if reservation is None:
            return None
        return PaymentCreationContext(
            reservation_id=reservation.id,
            user_id=reservation.user_id,
            festival_name=reservation.festival_name,
            amount=reservation.final_price,
            reservation_status=reservation.status,
            expires_at=reservation.expires_at,
        )
