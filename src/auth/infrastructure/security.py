# 파일 역할: TokenProvider를 JWT로 구현한다. 환경설정 → 서명된 토큰 발급 → 서명·만료·내용 검증 순서로 작동한다.

import os
import re
from datetime import UTC, datetime
from uuid import uuid4

import jwt
from dotenv import load_dotenv

from auth.domain.entities import TokenPayload
from auth.domain.service import TokenProvider
from shared.core.exceptions import UnauthorizedException


# 서버의 비밀키로 HS512 서명을 생성·검증한다. JWT 만료값은 DB 컬럼이 아니라 토큰 안에 둔다.
class JwtTokenProvider(TokenProvider):
    """HS512 액세스 토큰 발급·검증. 만료 정보는 JWT 안에서만 관리한다."""

    # 허용 서명 방식을 서버가 고정한다. 토큰 헤더가 지정한 임의의 방식을 따라가지 않는다.
    ALGORITHM = "HS512"
    MAX_USER_ID = 2**63 - 1

    # 비밀키 길이·유효 기간·발급자·대상을 검사한 뒤 설정을 보관한다. 잘못된 설정으로 토큰을 만들지 않는다.
    def __init__(
        self,
        secret_key: str,
        *,
        expires_in_seconds: int = 3600,
        issuer: str = "be-project-teamd",
        audience: str = "be-project-teamd-api",
    ):
        if (
            not isinstance(secret_key, str)
            or not secret_key.strip()
            or len(secret_key.encode()) < 64
        ):
            raise ValueError("JWT_SECRET_KEY는 최소 64바이트의 비밀값이어야 합니다.")
        if type(expires_in_seconds) is not int or expires_in_seconds <= 0:
            raise ValueError("JWT 액세스 토큰 유효 기간은 양의 정수(초)여야 합니다.")
        if not issuer.strip() or not audience.strip():
            raise ValueError("JWT 발급자와 대상은 비어 있을 수 없습니다.")
        self._secret_key = secret_key
        self._expires_in_seconds = expires_in_seconds
        self._issuer = issuer
        self._audience = audience

    # 환경변수에서 JWT 설정을 읽는다. 비밀키가 없으면 임시 키를 만들지 않고 생성자 검증에서 실패한다.
    @classmethod
    def from_env(cls) -> "JwtTokenProvider":
        load_dotenv()
        return cls(
            secret_key=os.getenv("JWT_SECRET_KEY", ""),
            expires_in_seconds=int(
                os.getenv("JWT_ACCESS_TOKEN_EXPIRE_SECONDS", "3600")
            ),
            issuer=os.getenv("JWT_ISSUER", "be-project-teamd"),
            audience=os.getenv("JWT_AUDIENCE", "be-project-teamd-api"),
        )

    # 회원 ID와 새 jti를 넣고 현재 시각 기준 만료값을 계산한 뒤 JWT에 서명한다.
    def create_access_token(self, user_id: int) -> tuple[str, str, int]:
        if type(user_id) is not int or not 1 <= user_id <= self.MAX_USER_ID:
            raise ValueError("회원 ID는 양의 BIGINT 정수여야 합니다.")
        issued_at = int(datetime.now(UTC).timestamp())
        jti = str(uuid4())
        # JWT 내용은 암호화되지 않아 읽을 수 있다. 비밀번호 같은 비밀 정보는 넣지 않는다.
        # sub=회원 ID, jti=토큰 식별자, iat=발급 시각, exp=만료 시각(초 단위)이다.
        # iss·aud는 발급자·대상을 제한하고 token_use는 액세스 토큰 용도를 표시한다.
        token = jwt.encode(
            {
                "sub": str(user_id),
                "jti": jti,
                "iat": issued_at,
                "exp": issued_at + self._expires_in_seconds,
                "iss": self._issuer,
                "aud": self._audience,
                "token_use": "access",
            },
            self._secret_key,
            algorithm=self.ALGORITHM,
        )
        return token, jti, self._expires_in_seconds

    # 입력 길이와 JWT 서명을 검사하고 필수 클레임의 타입·범위까지 확인해 위조되거나 잘못된 토큰을 거절한다.
    def decode_token(self, token: str) -> TokenPayload:
        if not isinstance(token, str) or not token or len(token) > 8192:
            raise self._unauthorized()
        try:
            claims = jwt.decode(
                token,
                self._secret_key,
                # 토큰 헤더가 아닌 서버 설정으로 허용 알고리즘을 고정한다.
                algorithms=[self.ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": ["sub", "jti", "iat", "exp", "iss", "aud", "token_use"],
                    "strict_aud": True,
                },
            )
        except (jwt.InvalidTokenError, TypeError, ValueError, OverflowError):
            raise self._unauthorized() from None

        # 라이브러리의 서명·만료 검사 이후, 회원 ID 표현과 시각의 타입·앞뒤 관계도 검사한다.
        subject = claims["sub"]
        jti = claims["jti"]
        issued_at = claims["iat"]
        expires_at = claims["exp"]
        if (
            not isinstance(subject, str)
            or re.fullmatch(r"[1-9][0-9]{0,18}", subject) is None
            or int(subject) > self.MAX_USER_ID
            or not isinstance(jti, str)
            or not jti.strip()
            or type(issued_at) is not int
            or type(expires_at) is not int
            or issued_at < 0
            or expires_at <= issued_at
            or claims["token_use"] != "access"
        ):
            raise self._unauthorized()
        return TokenPayload(user_id=int(subject), jti=jti)

    # 검증 실패 원인의 세부 정보를 감추고 일관된 401 예외를 생성한다.
    @staticmethod
    def _unauthorized() -> UnauthorizedException:
        return UnauthorizedException("유효하지 않거나 만료된 토큰입니다.")
