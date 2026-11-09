# 파일 역할: 인증 HTTP API다. 요청 스키마 → AuthService → 공통 응답 순서로 처리한다. DB를 직접 조작하지 않는다.

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from auth.application.service import AuthService
from auth.presentation.dependencies import provide_auth_service, require_bearer_token
from auth.presentation.schemas import LoginRequest, TokenResponse
from shared.core.exceptions import UnauthorizedException
from shared.core.schemas import APIResponse

router = APIRouter(prefix="/v1/auth", tags=["auth"])
Service = Annotated[AuthService, Depends(provide_auth_service)]


# 검증된 이메일·원문 비밀번호를 서비스에 전달하고, 발급된 토큰은 캐시 방지 헤더와 함께 응답한다.
@router.post("/login", response_model=APIResponse[TokenResponse])
async def login(request: LoginRequest, response: Response, service: Service):
    # SecretStr의 원문은 비밀번호 확인에 필요한 이 지점에서 꺼낸다. 로그로 출력하지 않는다.
    token, token_type, expires_in = await service.login(
        request.email, request.password.get_secret_value()
    )
    # 토큰 응답을 브라우저·중간 캐시가 저장하지 않도록 한다.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return APIResponse.ok(
        data=TokenResponse(
            access_token=token, token_type=token_type, expires_in=expires_in
        )
    )


# 헤더의 토큰을 차단 목록에 등록한다. 성공은 내용 없는 204이며 활성 회원 검사와는 별도로 처리한다.
@router.post("/logout", status_code=204)
async def logout(
    token: Annotated[str, Depends(require_bearer_token)], service: Service
) -> Response:
    # get_current_user는 사용하지 않아 중복 로그아웃/탈퇴 후 토큰 차단도 허용한다.
    try:
        await service.logout(token)
    except UnauthorizedException as exc:
        raise HTTPException(
            status_code=401, detail=exc.message, headers={"WWW-Authenticate": "Bearer"}
        ) from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
