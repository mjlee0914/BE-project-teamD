"""
# wiring/reservation.py
예매 도메인의 자리표시자 의존성에 실제 구현체를 연결하는 파일

# 연결하는 것
- provide_reservation_service → build_reservation_service : 저장소 4개를 같은 세션으로 묶은 서비스

# 참고
- 요청한 사람(get_current_actor)은 공용으로 wiring/actor.py에서 연결 (#143)
"""

# 외부 라이브러리
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

# 프로젝트 코드
from festivals.infrastructure.repositories import SqlAlchemyFestivalRepository
from performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from reservations.application.service import ReservationService
from reservations.infrastructure.repositories import SqlalchemyReservationRepository
from reservations.presentation.dependencies import (
    provide_reservation_service,
)
from shared.core.database import get_db
from tickets.infrastructure.repositories import SqlAlchemyTicketRepository


# 예매 서비스 조립 (저장소 3개에 "같은 세션" → 한 트랜잭션)
def build_reservation_service(
    session: AsyncSession = Depends(get_db),
) -> ReservationService:
    return ReservationService(
        reservation_repo=SqlalchemyReservationRepository(session),
        festival_repo=SqlAlchemyFestivalRepository(session),
        performance_repo=SqlAlchemyPerformanceRepository(session),
        ticket_repo=SqlAlchemyTicketRepository(session),
    )


# 의존성 교체 등록 (괄호 없이 함수 자체를 넘김)
def wire_reservation_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            provide_reservation_service: build_reservation_service,
        }
    )
