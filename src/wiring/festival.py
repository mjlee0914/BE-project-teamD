from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.database import get_db
from festivals.application.service import FestivalService
from festivals.infrastructure.repositories import SqlAlchemyFestivalRepository
from festivals.presentation.dependencies import get_festival_service

def build_festival_service(
    session: AsyncSession = Depends(get_db),
) -> FestivalService:
    return FestivalService(
        SqlAlchemyFestivalRepository(session)
    )
    
def wire_festival_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리
            get_festival_service: build_festival_service
        }
    )