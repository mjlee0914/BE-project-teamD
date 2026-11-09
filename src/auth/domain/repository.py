# 파일 역할: 로그아웃 토큰 저장소의 계약이다. 실제 SQL은 infrastructure/repositories.py에 둔다.

from abc import ABC, abstractmethod


# 블랙리스트를 어떤 DB에 저장할지는 정하지 않고, 인증 서비스가 사용할 메서드만 정의한다.
class TokenBlacklistRepository(ABC):
    # 동일 토큰·동일 회원의 중복 등록은 허용하고, 다른 회원으로 소유자를 덮어쓰지 않는 계약이다.
    @abstractmethod
    async def add(self, jti: str, user_id: int) -> None:
        """토큰 등록. 같은 jti/user_id의 재등록은 성공으로 취급하며 기존 소유자는 바꾸지 않는다."""

    # 특정 jti의 차단 여부만 반환한다. 토큰 서명이나 회원 상태 검사는 다른 계약의 역할이다.
    @abstractmethod
    async def is_blacklisted(self, jti: str) -> bool:
        """토큰이 블랙리스트에 등록되어 있는지 확인"""
