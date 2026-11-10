# Annotated[타입, Depends(...)]: 매개변수 타입과 의존성 주입을 한 번에 표시
from typing import Annotated

# FastAPI: app.dependency_overrides 등록 대상, Depends: get_db 세션 주입
from fastapi import Depends, FastAPI

# 비동기 DB 세션 타입 (get_db가 요청마다 만들어 줌)
from sqlalchemy.ext.asyncio import AsyncSession

# auth/infrastructure/password_hasher.py
from auth.infrastructure.password_hasher import BcryptPasswordHasher

# shared/core/database.py
from shared.core.database import get_db

# users/application/service.py
from users.application.service import UserService

# users/infrastructure/repositories.py
from users.infrastructure.repositories import SqlAlchemyUserRepository

# users/presentation/dependencies.py
from users.presentation.dependencies import get_user_service


# 요청마다 get_db가 세션을 넣어줌 -> 같은 세션으로 저장소를 만들어 한 트랜잭션으로 처리
# 추상(UserRepository, PasswordHasher) 자리에 실제 구현체(SqlAlchemy, Bcrypt)를 넣어 UserService 조립
def build_user_service(
        session: Annotated[AsyncSession, Depends(get_db)],
) -> UserService:
    return UserService(
        user_repo=SqlAlchemyUserRepository(session),
        hasher=BcryptPasswordHasher(),
    )

def wire_user_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리
            get_user_service: build_user_service,
        }
    )