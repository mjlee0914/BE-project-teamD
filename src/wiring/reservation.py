from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from festivals.infrastructure.repositories import SqlAlchemyFestivalRepository
from performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from reservations.application.service import ReservationService
from reservations.infrastructure.repositories import SqlalchemyReservationRepository
from reservations.presentation.dependencies import provide_reservation_service
from shared.core.database import get_db


def build_reservation_service(
    session: AsyncSession = Depends(get_db),
) -> ReservationService:
    return ReservationService(
        reservation_repo=SqlalchemyReservationRepository(session),
        festival_repo=SqlAlchemyFestivalRepository(session),
        performance_repo=SqlAlchemyPerformanceRepository(session),
    )


def wire_reservation_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리
            provide_reservation_service: build_reservation_service
        }
    )
