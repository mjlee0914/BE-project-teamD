from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.entities import TokenPayload
from auth.presentation.dependencies import get_current_user
from performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from reservations.infrastructure.repositories import SqlalchemyReservationRepository
from shared.core.database import get_db
from tickets.application.service import TicketService
from tickets.infrastructure.repositories import SqlAlchemyTicketRepository
from tickets.presentation.dependencies import (
    CurrentActor,
    get_current_actor,
    get_ticket_service,
)


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


# 요청한 사람: auth의 get_current_user가 토큰을 검증해서 돌려준 TokenPayload에서 user_id를 꺼낸다
# auth 서비스(provide_auth_service)가 wiring되기 전에는 503으로 막힌다 (검증 없이 통과하지 않음)
# TODO: 관리자·활성 회원 확인은 users 담당자가 만드는 메서드가 머지되면 여기서 연결한다.
#       그 결과로 is_admin을 채운다. 그 전에는 모두 일반 회원으로 취급하므로
#       관리자 기능은 403으로 막힌다 (권한이 열리는 쪽으로 틀리지 않게 하는 기본값)
async def build_current_actor(
    user: Annotated[TokenPayload, Depends(get_current_user)],
) -> CurrentActor:
    return CurrentActor(user_id=user.user_id, is_admin=False)  # 우선 false처리


def wire_ticket_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리 (요청서 -> 공장 연결)
            get_ticket_service: build_ticket_service,
            get_current_actor: build_current_actor,
        }
    )
