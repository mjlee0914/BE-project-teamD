from abc import ABC, abstractmethod


class TokenBlacklistRepository(ABC):
    @abstractmethod
    async def add(self, jti: str, user_id: int) -> None:
        """블랙리스트에 토큰 식별자와 회원 ID 등록"""

    @abstractmethod
    async def is_blacklisted(self, jti: str) -> bool:
        """토큰이 블랙리스트에 등록되어 있는지 확인"""
