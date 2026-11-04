from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

import jwt

from auth.domain.entities import TokenPayload, UnauthorizedException
from auth.domain.service import TokenProvider


class JwtTokenProvider(TokenProvider):
    """JWT 발급과 검증을 담당합니다. 블랙리스트 조회는 별도로 수행해야 합니다."""

    def __init__(self, secret_key: str) -> None:
        if not isinstance(secret_key, str) or len(secret_key.encode("utf-8")) < 32:
            raise ValueError("JWT 비밀 키는 32바이트 이상이어야 합니다.")
        self._secret_key = secret_key

    def create_access_token(self, user_id: int) -> str:
        return self._create_token(user_id, "access", timedelta(minutes=30))

    def create_refresh_token(self, user_id: int) -> str:
        return self._create_token(user_id, "refresh", timedelta(days=7))

    def _create_token(
        self,
        user_id: int,
        token_type: Literal["access", "refresh"],
        lifetime: timedelta,
    ) -> str:
        if type(user_id) is not int or user_id <= 0:
            raise ValueError("회원 ID는 양의 정수여야 합니다.")
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "jti": str(uuid4()),
            "iat": now,
            "exp": now + lifetime,
            "token_type": token_type,
        }
        return jwt.encode(payload, self._secret_key, algorithm="HS256")

    def decode_token(
        self, token: str, *, expected_type: Literal["access", "refresh"] = "access"
    ) -> TokenPayload:
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=["HS256"],
                options={"require": ["sub", "jti", "iat", "exp", "token_type"]},
            )
        except jwt.InvalidTokenError as exc:
            raise UnauthorizedException("유효하지 않거나 만료된 토큰입니다.") from exc

        if payload["token_type"] != expected_type:
            raise UnauthorizedException("요청에 사용할 수 없는 종류의 토큰입니다.")
        if not isinstance(payload["jti"], str) or not payload["jti"].strip():
            raise UnauthorizedException("토큰 식별자(jti)가 올바르지 않습니다.")
        if any(type(payload[name]) is not int for name in ("iat", "exp")):
            raise UnauthorizedException("토큰의 시간 정보가 올바르지 않습니다.")

        subject = payload["sub"]
        try:
            user_id = int(subject)
        except (ValueError, TypeError) as exc:
            raise UnauthorizedException("토큰의 회원 ID가 올바르지 않습니다.") from exc
        if user_id <= 0 or str(user_id) != subject:
            raise UnauthorizedException("토큰의 회원 ID가 올바르지 않습니다.")

        try:
            expired_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise UnauthorizedException(
                "토큰의 만료 시각이 올바르지 않습니다."
            ) from exc

        return TokenPayload(
            user_id=user_id,
            jti=payload["jti"],
            exp=expired_at,
            token_type=expected_type,
        )
