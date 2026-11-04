from typing import Annotated

from fastapi import APIRouter, Depends

from auth.application.service import AuthService
from auth.domain.entities import UnauthorizedException
from auth.presentation.dependencies import (
    get_access_token,
    provide_auth_service,
    unauthorized,
)
from auth.presentation.schemas import (
    LogoutResponse,
    RefreshTokenRequest,
    TokenResponse,
)

router = APIRouter(prefix="/v1/auth", tags=["Auth"])


@router.post("/logout", response_model=LogoutResponse, summary="현재 토큰 로그아웃")
async def logout(
    payload: RefreshTokenRequest,
    access_token: Annotated[str, Depends(get_access_token)],
    service: Annotated[AuthService, Depends(provide_auth_service)],
) -> LogoutResponse:
    try:
        await service.logout(access_token, payload.refresh_token)
    except UnauthorizedException as exc:
        raise unauthorized() from exc
    return LogoutResponse()


@router.post("/refresh", response_model=TokenResponse, summary="액세스 토큰 재발급")
async def refresh(
    payload: RefreshTokenRequest,
    service: Annotated[AuthService, Depends(provide_auth_service)],
) -> TokenResponse:
    try:
        token = await service.refresh_access_token(payload.refresh_token)
    except UnauthorizedException as exc:
        raise unauthorized() from exc
    return TokenResponse(access_token=token)
