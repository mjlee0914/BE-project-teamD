from abc import ABC, abstractmethod

from auth.domain.entities import BlacklistToken


class TokenBlacklistRepository(ABC):
    """차단 기록 저장소가 제공해야 할 기능. DB 기술에는 의존하지 않습니다."""

    @abstractmethod
    async def add(self, jti: str, user_id: int) -> None:
        pass

    @abstractmethod
    async def find_by_jti(self, jti: str) -> BlacklistToken | None:
        pass

    @abstractmethod
    async def is_blacklisted(self, jti: str) -> bool:
        pass
