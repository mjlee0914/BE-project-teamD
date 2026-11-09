from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from festivals.infrastructure.repositories import SqlAlchemyFestivalRepository
from performances.application.service import PerformanceService
from performances.infrastructure.repositories import SqlAlchemyPerformanceRepository
from performances.presentation.dependencies import get_performance_service
from shared.core.database import get_db


def build_performance_service(
        session: Annotated[AsyncSession, Depends(get_db)],
) -> PerformanceService:
    return PerformanceService(
        SqlAlchemyPerformanceRepository(session),
        SqlAlchemyFestivalRepository(session)
    )

def wire_performance_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리
            get_performance_service: build_performance_service
        }
    )