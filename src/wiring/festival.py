from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from festivals.application.service import FestivalService
from festivals.infrastructure.repositories import SqlAlchemyFestivalRepository
from festivals.presentation.dependencies import get_festival_service
from performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from shared.core.database import get_db


def build_festival_service(
    session: Annotated[AsyncSession, Depends(get_db)],  # get_db가 요청마다 세션을 넣어줌
) -> FestivalService:
    return FestivalService( 
        # 저장소 2개를 같은 세션으로
        # -> 한 요청이 하나의 트랜잭션이어야 get_db가 한꺼번에 commit/rollback 가능
        SqlAlchemyFestivalRepository(session),
        SqlAlchemyPerformanceRepository(session)
    )
    
def wire_festival_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리
            get_festival_service: build_festival_service
        }
    )