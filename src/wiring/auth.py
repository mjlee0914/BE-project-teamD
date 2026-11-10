from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from auth.application.service import AuthService
from auth.domain.service import TokenProvider
from auth.infrastructure.factory import create_auth_service
from auth.infrastructure.password_hasher import BcryptPasswordHasher
from auth.infrastructure.security import JwtTokenProvider
from auth.presentation.dependencies import provide_auth_service
from shared.core.database import get_db


# FastAPI가 요청마다 호출하는 AuthService 조립 함수
# Depends(get_db)로 받은 요청 세션 하나를 사용자 조회와 토큰 블랙리스트 저장소가 함께 사용하게 함
# JWT 설정은 환경 변수에서 읽고, bcrypt 해시 구현체를 주입해 로그인 검증 기능을 완성함.
def build_auth_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AuthService:
    token_provider: TokenProvider = JwtTokenProvider.from_env()
    return create_auth_service(
        session,
        token_provider,
        password_hasher=BcryptPasswordHasher(),
    )


# auth 라우터가 사용하는 기본 제공 함수를 실제 조립 함수로 교체한다.
# 이렇게 등록하면 라우터는 구현 클래스나 DB 생성 방법을 알 필요 없이 AuthService를 주입받는다.
def wire_auth_dependencies(app: FastAPI) -> None:
    app.dependency_overrides[provide_auth_service] = build_auth_service
