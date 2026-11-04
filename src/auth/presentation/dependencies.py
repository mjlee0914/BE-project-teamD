from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.application.service import AuthService
from auth.domain.entities import TokenPayload, UnauthorizedException

bearer_scheme = HTTPBearer(auto_error=False, bearerFormat="JWT")


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="유효한 인증 토큰이 필요합니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def provide_auth_service() -> AuthService:
    """auth.wiring.wire_auth_dependencies(app)에서 구현체를 연결할 주입 명세."""
    raise NotImplementedError("AuthService 의존성이 연결되지 않았습니다.")


def get_access_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    if credentials is None:
        raise unauthorized()
    return credentials.credentials


async def get_current_token(
    token: Annotated[str, Depends(get_access_token)],
    service: Annotated[AuthService, Depends(provide_auth_service)],
) -> TokenPayload:
    """보호할 API에서 Depends로 사용합니다. 회원 상태 조회는 별도입니다."""
    try:
        return await service.authenticate_token(token)
    except UnauthorizedException as exc:
        raise unauthorized() from exc
