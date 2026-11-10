from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.entities import TokenPayload
from auth.presentation.dependencies import get_current_user
from shared.core.actor import CurrentActor, get_current_actor
from shared.core.database import get_db
from shared.core.exceptions import UnauthorizedException
from users.infrastructure.repositories import SqlAlchemyUserRepository


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


def wire_actor_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            # 추상 의존성: 구현체 팩토리
            get_current_actor: build_current_actor,
        }
    )
