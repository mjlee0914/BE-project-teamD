"""
# wiring/user.py
- 회원 도메인 의존성 조립 파일 (추상 <-> 구현체 연결은 이 파일에서만)
- router의 get_user_service(자리표시자)를 build_user_service(실제 조립 함수)로 바꿔 끼움

# 조립 내용
- UserRepository            -> SqlAlchemyUserRepository(session)
- PasswordHasher            -> BcryptPasswordHasher()
- ActiveReservationChecker  -> RepositoryActiveReservationChecker(SqlalchemyReservationRepository(session))

# 세션 (session)
- get_db가 요청마다 세션 1개를 만들어 줌 -> 모든 저장소가 같은 세션 사용 -> 한 트랜잭션
- commit/rollback은 get_db가 요청 단위로 처리

# 호출 위치
- main.py -> wiring/__init__.py의 wire_dependencies -> wire_user_dependencies(app)
"""

# Annotated[타입, Depends(...)]: 매개변수 타입과 의존성 주입을 한 번에 표시
from typing import Annotated

# FastAPI: app.dependency_overrides 등록 대상, Depends: get_db 세션 주입
from fastapi import Depends, FastAPI

# 비동기 DB 세션 타입 (get_db가 요청마다 만들어 줌)
from sqlalchemy.ext.asyncio import AsyncSession

# auth/infrastructure/password_hasher.py
from auth.infrastructure.password_hasher import BcryptPasswordHasher

# reservations/infrastructure/repositories.py
from reservations.infrastructure.repositories import SqlalchemyReservationRepository

# shared/core/database.py
from shared.core.database import get_db

# users/application/service.py
from users.application.service import UserService

# users/infrastructure/repositories.py
from users.infrastructure.repositories import SqlAlchemyUserRepository

# users/infrastructure/reservation_checker.py
from users.infrastructure.reservation_checker import RepositoryActiveReservationChecker

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
        reservation_checker=RepositoryActiveReservationChecker(
            SqlalchemyReservationRepository(session)
        ),
    )

# [회원 의존성 등록] 앱 시작 시 한 번 실행 (main.py -> wire_dependencies)
# dependency_overrides: "이 의존성 함수 대신 저 함수를 실행해라"라는 FastAPI 교체표
# 등록 후 Depends(get_user_service)가 있는 모든 API에 build_user_service가 만든 service가 들어감
def wire_user_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리
            get_user_service: build_user_service,
        }
    )