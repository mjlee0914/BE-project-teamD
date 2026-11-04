from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.models import Base


class TokenBlacklistModel(Base):
    """로그아웃으로 차단한 토큰을 저장하는 테이블 모델."""

    __tablename__ = "token_blacklist"

    jti: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )
