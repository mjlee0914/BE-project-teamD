import os
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from auth.application.service import AuthService
from auth.domain.service import TokenProvider
from auth.infrastructure.repositories import SqlAlchemyTokenBlacklistRepository
from auth.infrastructure.security import JwtTokenProvider
from auth.infrastructure.transactions import SqlAlchemyTransactionManager
from auth.presentation.dependencies import provide_auth_service
from shared.core.database import get_db


def get_token_provider() -> TokenProvider:
    secret_key = os.getenv("JWT_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY 환경 변수가 설정되지 않았습니다.")
    return JwtTokenProvider(secret_key)


def build_auth_service(db: AsyncSession, tokens: TokenProvider) -> AuthService:
    """동일한 세션을 공유하는 저장소·트랜잭션 구현체를 조립합니다."""
    return AuthService(
        token_blacklist_repo=SqlAlchemyTokenBlacklistRepository(db),
        token_provider=tokens,
        transaction=SqlAlchemyTransactionManager(db),
    )


def create_auth_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    tokens: Annotated[TokenProvider, Depends(get_token_provider)],
) -> AuthService:
    return build_auth_service(db, tokens)


def wire_auth_dependencies(app: FastAPI) -> None:
    """애플리케이션 생성 시 호출하여 표현 계층의 주입 명세를 연결합니다."""
    app.dependency_overrides[provide_auth_service] = create_auth_service
