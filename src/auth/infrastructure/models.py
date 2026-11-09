# 파일 역할: token_blacklist 테이블의 ORM 정의다. 도메인 객체와 달리 컬럼·외래키 등 DB 구조를 표현한다.

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.models import Base


# jti가 기본키라 한 회원의 여러 토큰을 따로 차단할 수 있다. user_id는 users.id를 참조한다.
class TokenBlacklistModel(Base):
    """ERD의 두 컬럼만 사용한다. 한 회원의 여러 토큰을 각각 차단할 수 있다."""

    __tablename__ = "token_blacklist"

    # 회원 ID가 아닌 토큰 식별자에 PK를 둔다. 한 회원이 여러 기기에서 각각 로그아웃할 수 있다.
    jti: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
