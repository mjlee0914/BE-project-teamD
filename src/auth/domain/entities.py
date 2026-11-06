"""인증(auth) 과정에서 주고받을 정보를 ONLY 파이선 객체로 정의"""

""" ※로그인 처리나 JWT 검증 자체를 수행하는 코드는 아님"""

# dataclasses -> 파이썬 기본 제공 모듈
# dataclass는 객체를 만들 때 필요한 초기화 메서드를 자동으로 만들어줌

from dataclasses import dataclass


@dataclass(frozen=True)  # 수정을 불가하게 해줌
class TokenPayload:
    """검증된 토큰에서 추출한 회원 ID와 토큰 식별자."""

    user_id: int
    jti: str


@dataclass(frozen=True)
class BlacklistToken:
    """로그아웃으로 사용을 차단한 토큰 한 개의 정보."""

    jti: str
    user_id: int
