from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from festivals.infrastructure.repositories import SqlAlchemyFestivalRepository
from performances.application.service import PerformanceService
from performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from performances.presentation.dependencies import get_performance_service
from reservations.application.service import ReservationService
from reservations.infrastructure.repositories import SqlalchemyReservationRepository
from shared.core.database import get_db
from tickets.application.service import TicketService
from tickets.infrastructure.repositories import SqlAlchemyTicketRepository

# def build_performance_service(
#         session: Annotated[AsyncSession, Depends(get_db)],
# ) -> PerformanceService:
#     return PerformanceService(
#         performance_repo=SqlAlchemyPerformanceRepository(session),
#         festival_repo=SqlAlchemyFestivalRepository(session),
#         reservation_service=ReservationService(
#             reservation_repo=SqlalchemyReservationRepository(session),
#             festival_repo=SqlAlchemyFestivalRepository(session),
#             performance_repo=SqlAlchemyPerformanceRepository(session),
#             ticket_repo=SqlAlchemyTicketRepository(session),
#             )
#     )

def build_performance_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PerformanceService:
    reservation_repo = SqlalchemyReservationRepository(session)
    performance_repo = SqlAlchemyPerformanceRepository(session)
    ticket_repo = SqlAlchemyTicketRepository(session)
    return PerformanceService(
        performance_repo=performance_repo,
        festival_repo=SqlAlchemyFestivalRepository(session),
        reservation_service=ReservationService(
            reservation_repo=reservation_repo,
            festival_repo=SqlAlchemyFestivalRepository(session),
            performance_repo=performance_repo,
            ticket_repo=ticket_repo,
            ticket_service=TicketService(
                ticket_repo=ticket_repo,
                reservation_repo=reservation_repo,
                performance_repo=performance_repo,
            ),
        ),
    )

def wire_performance_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리
            get_performance_service: build_performance_service
        }
    )