# 도메인에 작성한 설계도 구현
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession  # DB대화창구
from sqlalchemy.orm.exc import StaleDataError

from reservations.infrastructure.models import (
    Reservation as ReservationModel,  # 에매의 도메인 객체와 겹칠 수 있어서 별칭 설정
)
from tickets.domain.enums import (
    TicketStatus,  # 변환 함수 _to_domain에서 이 enum으로 감쌈 (_to_model에서는 .value로 반대 방향 변환.)
)
from tickets.domain.exceptions import TicketNotFound, TicketVersionConflict
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
        version=model.version,
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
        if ticket.id is None:  # 새 티켓
            model = _to_model(ticket)
            self._session.add(model)
        else:  # 기존 티켓 갱신
            model = await self._session.get(TicketModel, ticket.id)
            if model is None:
                raise TicketNotFound()

            # session.get()은 DB에서 최신 값을 다시 읽어 오므로, 서비스가 조회했던 때의
            # version(ticket.version)과 비교해야 그 사이 다른 요청이 바꾼 것을 잡을 수 있다
            if model.version != ticket.version:
                raise TicketVersionConflict()

            # 바뀔 수 있는 값만 옮겨 적는다 (공연 스냅샷, 가격, ticket_code는 불변)
            model.status = ticket.status.value
            model.issued_at = ticket.issued_at
            model.used_at = ticket.used_at
            model.canceled_at = ticket.canceled_at

        try:
            await (
                self._session.flush()
            )  # INSERT / UPDATE를 DB로 보냄 (commit은 get_db가)
        except StaleDataError:  # flush 순간에 version이 어긋난 경우 (SQLAlchemy 에러)
            raise TicketVersionConflict() from None
        await self._session.refresh(model)  # DB가 채운 id, created_at 반영
        return _to_domain(model)

    async def find_by_code(self, ticket_code: UUID) -> Ticket | None:
        stmt = select(TicketModel).where(TicketModel.ticket_code == ticket_code)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def find_all_by_reservation(self, reservation_id: int) -> list[Ticket]:
        stmt = (
            select(TicketModel)
            .where(TicketModel.reservation_id == reservation_id)
            .order_by(TicketModel.id)
        )
        models = (await self._session.scalars(stmt)).all()
        return [_to_domain(model) for model in models]

    # async def count_by_reservation_id(self, reservation_id: int) -> int:
    #     stmt = (
    #         select(
    #             func.count()
    #         )  # 행의 개수가 필요. func는 파아썬에서 sql함수를 부르는 도구
    #         .select_from(TicketModel)  # 어떤 행인지 모르기때문에 따로 알려줘야 함
    #         .where(TicketModel.reservation_id == reservation_id)
    #     )
    #     result = await self._session.execute(stmt)
    #     return result.scalar_one()

    # 본인 예매 행을 잠근다 (SELECT ... FOR UPDATE)
    # 같은 행을 잠그려는 다른 요청은 이 요청이 끝날 때까지 기다린다
    # async def lock_reservation(self, reservation_id: int, user_id: int) -> None:
    #     stmt = (
    #         select(ReservationModel.id)
    #         .where(
    #             ReservationModel.id == reservation_id,
    #             ReservationModel.user_id == user_id,
    #         )
    #         .with_for_update()  # 이 조건에 맞는 행을 읽으면서 동시에 잠가라
    #     )
    #     await self._session.execute(stmt)  # 이 시점에 잠금이 걸림.

    async def find_all_by_user(
        self, user_id: int, status: TicketStatus | None, offset: int, limit: int
    ) -> list[Ticket]:
        stmt = (
            select(TicketModel)
            .join(ReservationModel, ReservationModel.id == TicketModel.reservation_id)
            .where(ReservationModel.user_id == user_id)
            .order_by(TicketModel.created_at.desc(), TicketModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(TicketModel.status == status.value)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars().all()]

    async def count_by_user(self, user_id: int, status: TicketStatus | None) -> int:
        stmt = (
            select(func.count())
            .select_from(TicketModel)
            .join(ReservationModel, ReservationModel.id == TicketModel.reservation_id)
            .where(ReservationModel.user_id == user_id)
        )
        if status is not None:
            stmt = stmt.where(TicketModel.status == status.value)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    # 관리자
    async def find_all(
        self,
        performance_id: int | None,
        status: TicketStatus | None,
        offset: int,
        limit: int,
    ) -> list[Ticket]:
        stmt = (
            select(TicketModel)
            .order_by(TicketModel.created_at.desc(), TicketModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if performance_id is not None:
            stmt = stmt.where(TicketModel.performance_id == performance_id)
        if status is not None:
            stmt = stmt.where(TicketModel.status == status.value)
        result = await self._session.execute(stmt)
        return [_to_domain(model) for model in result.scalars().all()]

    # 관리자 검색 전체 개수 (PageResponse.total 용)
    async def count(
        self, performance_id: int | None, status: TicketStatus | None
    ) -> int:
        stmt = select(func.count()).select_from(TicketModel)
        if performance_id is not None:
            stmt = stmt.where(TicketModel.performance_id == performance_id)
        if status is not None:
            stmt = stmt.where(TicketModel.status == status.value)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    # 입장 현황
    async def count_by_status(self, performance_id: int) -> dict[TicketStatus, int]:
        stmt = (
            select(TicketModel.status, func.count())
            .where(TicketModel.performance_id == performance_id)
            .group_by(TicketModel.status)
        )
        result = await self._session.execute(stmt)
        counts = {TicketStatus(status): n for status, n in result.all()}
        # 없는 상태도 0으로 채워서 모든 상태를 돌려준다
        return {status: counts.get(status, 0) for status in TicketStatus}
