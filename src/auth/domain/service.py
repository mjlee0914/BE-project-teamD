from abc import ABC, abstractmethod

from auth.domain.entities import TokenPayload


class TokenProvider(ABC):
    @abstractmethod
    def create_access_token(self, user_id: int) -> tuple[str, str, int]:
        """(token, jti, expires_in_seconds) 반환"""

    @abstractmethod
    def decode_token(self, token: str) -> TokenPayload:
        """서명과 만료 여부를 검증하고 회원 ID와 jti 반환"""


class UserCredentialVerifier(ABC):
    @abstractmethod
    async def verify_credentials(self, email: str, plain_password: str) -> int | None:
        """로그인 성공하면 user_id 반환, 실패 시 None 반환"""
