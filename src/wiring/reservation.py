"""
# wiring/reservation.py
예매 도메인의 자리표시자 의존성에 실제 구현체를 연결하는 파일

# 연결하는 것 2개
① provide_reservation_service → build_reservation_service : 저장소 3개를 같은 세션으로 묶은 서비스
② get_current_actor           → build_current_actor       : 토큰 검증 + 회원 조회로 "누가, 관리자인지"

# 주의 : 로그인 동작 조건
- build_current_actor는 auth의 get_current_user를 사용한다
- auth 담당이 wiring/auth.py에 provide_auth_service를 연결하기 전까지는 503이 응답됨 (정상)
"""

# 외부 라이브러리
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

# 프로젝트 코드
from auth.domain.entities import TokenPayload
from auth.presentation.dependencies import get_current_user
from festivals.infrastructure.repositories import SqlAlchemyFestivalRepository
from performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from reservations.application.service import ReservationService
from reservations.infrastructure.repositories import SqlalchemyReservationRepository
from reservations.presentation.dependencies import (
    CurrentActor,
    get_current_actor,
    provide_reservation_service,
)
from shared.core.database import get_db
from shared.core.exceptions import UnauthorizedException
from tickets.infrastructure.repositories import SqlAlchemyTicketRepository
from users.infrastructure.repositories import SqlAlchemyUserRepository


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


# 요청한 사람 만들기
# ① auth가 토큰을 검증해 user_id를 꺼냄 (토큰이 없거나 틀리면 auth가 401)
# ② users 저장소로 회원을 조회 → role을 알기 위함 (토큰에는 role이 없음)
# ③ 탈퇴 회원이면 403 (users 엔티티의 ensure_active)
# ④ is_admin은 users 엔티티의 프로퍼티를 그대로 사용
async def build_current_actor(
    token: Annotated[TokenPayload, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CurrentActor:
    user = await SqlAlchemyUserRepository(session).find_by_id(token.user_id)
    if user is None:  # 토큰은 맞는데 회원이 사라진 경우
        raise UnauthorizedException("회원 정보를 찾을 수 없습니다.")
    user.ensure_active()
    return CurrentActor(user_id=token.user_id, is_admin=user.is_admin)


# 의존성 교체 등록 (괄호 없이 함수 자체를 넘김)
def wire_reservation_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            provide_reservation_service: build_reservation_service,
            get_current_actor: build_current_actor,
        }
    )
