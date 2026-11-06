# 도메인에 작성한 설계도 구현
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession  # DB대화창구

from reservations.infrastructure.models import (
    Reservation as ReservationModel,  # 에매의 도메인 객체와 겹칠 수 있어서 별칭 설정
)
from tickets.domain.enums import (
    TicketStatus,  # 변환 함수 _to_domain에서 이 enum으로 감쌈 (_to_model에서는 .value로 반대 방향 변환.)
)
from tickets.domain.repository import TicketRepository  # 상속할 설계도
from tickets.domain.ticket import Ticket  # 반환 타입이자 반환 결과로 만드는 객체 자체
from tickets.infrastructure.models import Ticket as TicketModel


# model<->domain 간 번역기 만들기
def _to_domain(
    model: TicketModel,
) -> Ticket:  # infrastructure의 ticket을 받아서 domain Ticket으로
    """DB에서 읽은 행(ORM)을 도메인 Ticket으로 바꿈"""
    return Ticket(
        id=model.id,
        reservation_id=model.reservation_id,
        performance_id=model.performance_id,
        ticket_code=model.ticket_code,
        status=TicketStatus(model.status),  # "PENDING" 문자열 → enum
        price=model.price,
        performance_title=model.performance_title,
        performance_start_at=model.performance_start_at,
        performance_end_at=model.performance_end_at,
        cancel_deadline_at=model.cancel_deadline_at,
        issued_at=model.issued_at,
        used_at=model.used_at,
        canceled_at=model.canceled_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _to_model(ticket: Ticket) -> TicketModel:
    """도메인 Ticket을 DB에 넣을 ORM 객체로 바꿈(저장 이슈에서 사용)"""
    return TicketModel(
        id=ticket.id,  # 새 티켓이면 None → DB가 번호를 붙임
        reservation_id=ticket.reservation_id,
        performance_id=ticket.performance_id,
        ticket_code=ticket.ticket_code,
        status=ticket.status.value,  # enum → "PENDING" 문자열
        price=ticket.price,
        performance_title=ticket.performance_title,
        performance_start_at=ticket.performance_start_at,
        performance_end_at=ticket.performance_end_at,
        cancel_deadline_at=ticket.cancel_deadline_at,
        issued_at=ticket.issued_at,
        used_at=ticket.used_at,
        canceled_at=ticket.canceled_at,
        # created_at, updated_at은 DB가 채우므로 넣지 않음
    )


# 저장소 클래스
class SqlAlchemyTicketRepository(
    TicketRepository
):  # 설계도를 상속해 SQLAlchemy로 구현한 저장소
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id_for_user(self, ticket_id: int, user_id: int) -> Ticket | None:
        stmt = (
            select(TicketModel)
            .join(ReservationModel, ReservationModel.id == TicketModel.reservation_id)
            .where(TicketModel.id == ticket_id, ReservationModel.user_id == user_id)
        )

        result = await self._session.execute(stmt)  # DB에서 해당 행을 찾음
        model = result.scalar_one_or_none()  # 행 하나 꺼냄, 없으면 None
        return (
            None if model is None else _to_domain(model)
        )  # DB행에서 도메인 ticket으로 변환

    async def save(self, ticket: Ticket) -> Ticket:
        raise NotImplementedError

    async def find_by_code(self, ticket_code: UUID) -> Ticket | None:
        stmt = select(TicketModel).where(TicketModel.ticket_code == ticket_code)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def count_by_reservation_id(self, reservation_id: int) -> int:
        stmt = (
            select(
                func.count()
            )  # 행의 개수가 필요. func는 파아썬에서 sql함수를 부르는 도구
            .select_from(TicketModel)  # 어떤 행인지 모르기때문에 따로 알려줘야 함
            .where(TicketModel.reservation_id == reservation_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_all_by_user(self, user_id, status, page, size):
        raise NotImplementedError

    async def search(self, performance_id, status, page, size):
        raise NotImplementedError

    async def count_by_status(self, performance_id):
        raise NotImplementedError
