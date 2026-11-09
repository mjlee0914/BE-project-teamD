# 파일 역할: 인증에 필요한 기능의 계약이다. JWT·회원 조회·회원 상태 검사의 구현체를 밖에서 주입받는다.

from abc import ABC, abstractmethod

from auth.domain.entities import TokenPayload


# 토큰 발급·검증 방식의 교체 지점이다. 실제 JWT 구현은 infrastructure/security.py에 있다.
class TokenProvider(ABC):
    # 회원 ID를 받아 토큰 문자열, 토큰 식별자, 유효 기간(초)을 반환하도록 정의한다.
    @abstractmethod
    def create_access_token(self, user_id: int) -> tuple[str, str, int]:
        """(token, jti, expires_in_seconds) 반환"""

    # 검증에 성공한 토큰만 TokenPayload로 바꾸도록 요구한다. 내용을 읽는 것만으로 인증하지 않는다.
    @abstractmethod
    def decode_token(self, token: str) -> TokenPayload:
        """서명과 만료 여부를 검증하고 회원 ID와 jti 반환"""


# 이메일·비밀번호 확인을 users 저장 방식과 분리한다.
class UserCredentialVerifier(ABC):
    # 로그인 자격이 맞으면 회원 ID, 계정 없음·비밀번호 불일치이면 None을 반환하는 계약이다.
    @abstractmethod
    async def verify_credentials(self, email: str, plain_password: str) -> int | None:
        """로그인 성공하면 user_id 반환, 실패 시 None 반환"""


# 이미 발급된 토큰을 쓰는 회원도 현재 활동 가능한지 확인하는 계약이다.
class UserStatusChecker(ABC):
    # 회원이 없거나 비활성 상태이면 예외를 발생시키고, 통과하면 반환값 없이 끝낸다.
    @abstractmethod
    async def ensure_active(self, user_id: int) -> None:
        """현재 회원이 없으면 401, 비활성/탈퇴 상태이면 403으로 거절한다."""
