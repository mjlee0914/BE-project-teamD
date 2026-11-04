from dataclasses import dataclass


class UnauthorizedException(Exception):
    """인증 토큰이 유효하지 않거나 사용이 차단된 경우 발생합니다."""


@dataclass(frozen=True)
class TokenPayload:
    """검증된 토큰 정보. 회원 ID는 팀 ERD에 맞춰 정수로 유지합니다."""

    user_id: int
    jti: str


@dataclass
class BlacklistToken:
    """로그아웃으로 사용을 차단한 토큰 한 개의 정보."""

    jti: str
    user_id: int

    # def __post_init__(self) -> None:
    #     if not isinstance(self.jti, str) or not self.jti.strip():
    #         raise ValueError("토큰 식별자(jti)는 비어 있을 수 없습니다.")
    #     if type(self.user_id) is not int or self.user_id <= 0:
    #         raise ValueError("회원 ID는 양의 정수여야 합니다.")
