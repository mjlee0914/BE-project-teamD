from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from reservations.infrastructure.repositories import SqlalchemyReservationRepository
from shared.core.database import get_db
from tickets.application.service import TicketService
from tickets.infrastructure.repositories import SqlAlchemyTicketRepository
from tickets.presentation.dependencies import get_ticket_service


# 티켓 서비스 조립
# 저장소 3개에 "같은 세션"을 넣는 것이 핵심: 한 요청이 한 트랜잭션이어야 중간에 실패했을 때 get_db가 전부 rollback할 수 있다
def build_ticket_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TicketService:
    return TicketService(
        ticket_repo=SqlAlchemyTicketRepository(session),
        reservation_repo=SqlalchemyReservationRepository(session),
        performance_repo=SqlAlchemyPerformanceRepository(session),
    )


# 참고: 요청한 사람(get_current_actor)은 공용으로 wiring/actor.py에서 연결한다 (#143)
def wire_ticket_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리 (요청서 -> 공장 연결)
            get_ticket_service: build_ticket_service,
        }
    )