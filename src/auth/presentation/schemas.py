from typing import Literal

from pydantic import BaseModel, Field


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(
        min_length=1, repr=False, description="로그아웃 또는 재발급할 리프레시 토큰"
    )


class LogoutResponse(BaseModel):
    message: str = "로그아웃이 완료되었습니다."


class TokenResponse(BaseModel):
    access_token: str = Field(repr=False, description="새로 발급한 액세스 토큰")
    token_type: Literal["bearer"] = "bearer"
