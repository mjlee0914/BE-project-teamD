# 파일 역할: FastAPI 의존성이다. Bearer 토큰 추출과 현재 사용자 인증을 처리하고 AuthService의 주입 지점을 제공한다.

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.application.service import AuthService
from auth.domain.entities import TokenPayload
from shared.core.exceptions import UnauthorizedException

# 누락 처리를 UnauthorizedException으로 통일한다. HTTP 응답과 인증 헤더는 공통 핸들러가 만든다.
bearer = HTTPBearer(auto_error=False)


# Authorization 헤더에서 추출한 Bearer 자격 정보의 토큰 문자열을 반환한다. 누락은 401이다.
def require_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    if credentials is None:
        raise UnauthorizedException("인증 토큰이 필요합니다.")
    return credentials.credentials


# 실제 서비스로 교체할 주입 지점이다. wiring이 연결되지 않은 상태는 503으로 차단한다.
def provide_auth_service() -> AuthService:
    # 실제 구성 없이 토큰을 허용하거나 임시 비밀키를 사용하지 않는다.
    raise HTTPException(status_code=503, detail="인증 서비스 연결이 필요합니다.")


# AuthService로 토큰을 검증한다. 인증 예외를 HTTPException으로 바꾸지 않고 공통 핸들러에 맡긴다.
async def get_current_user(
    token: Annotated[str, Depends(require_bearer_token)],
    service: Annotated[AuthService, Depends(provide_auth_service)],
) -> TokenPayload:
    return await service.authenticate_token(token)
