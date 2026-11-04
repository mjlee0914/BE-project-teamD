from abc import ABC, abstractmethod
from typing import Literal

from auth.domain.entities import TokenPayload


class TokenProvider(ABC):
    """액세스·리프레시 토큰의 발급 및 검증 계약."""

    @abstractmethod
    def create_access_token(self, user_id: int) -> str:
        pass

    @abstractmethod
    def create_refresh_token(self, user_id: int) -> str:
        pass

    @abstractmethod
    def decode_token(
        self, token: str, *, expected_type: Literal["access", "refresh"] = "access"
    ) -> TokenPayload:
        pass


class TransactionManager(ABC):
    """서비스가 저장 확정·취소를 요청하는 계약."""

    @abstractmethod
    async def commit(self) -> None:
        pass

    @abstractmethod
    async def rollback(self) -> None:
        pass
