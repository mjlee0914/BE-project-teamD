from typing import Annotated

from fastapi import APIRouter, Depends

from auth.application.service import AuthService
from auth.domain.entities import UnauthorizedException
from auth.presentation.dependencies import (
    get_access_token,
    provide_auth_service,
    unauthorized,
)
from auth.presentation.schemas import LogoutResponse

router = APIRouter(prefix="/v1/auth", tags=["Auth"])


@router.post("/logout", response_model=LogoutResponse, summary="현재 토큰 로그아웃")
async def logout(
    access_token: Annotated[str, Depends(get_access_token)],
    service: Annotated[AuthService, Depends(provide_auth_service)],
) -> LogoutResponse:
    try:
        await service.logout(access_token)
    except UnauthorizedException as exc:
        raise unauthorized() from exc
    return LogoutResponse()
