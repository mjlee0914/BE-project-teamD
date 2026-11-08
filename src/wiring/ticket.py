from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.database import get_db
from tickets.application.service import TicketService
from tickets.infrastructure.repositories import SqlAlchemyTicketRepository
from tickets.presentation.dependencies import get_ticket_service


def build_ticket_service(
    session: AsyncSession = Depends(get_db),
) -> TicketService:  # get_db가 요청마다 세션을 넣어줌.
    return TicketService(
        SqlAlchemyTicketRepository(session)
    )  # 세션 넣어서 저장소 완성, 그리고 그 저장소를 넣어 서비스 완성


def wire_ticket_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리 (요청서-> 공장 연결)
            get_ticket_service: build_ticket_service
        }
    )
