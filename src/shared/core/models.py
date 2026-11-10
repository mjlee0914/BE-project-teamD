from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# 데이터베이스 테이블의 기준 클래스
class Base(DeclarativeBase):
    pass


# 날짜 관련 공통 컬럼
class DateTimeMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )



def init_models() -> None:
    """SQLAlchemy 모델 메타데이터 등록"""
    import auth.infrastructure.models
    import festivals.infrastructure.models
    import payments.infrastructure.models
    import performances.infrastructure.models
    import reservations.infrastructure.models
    import users.infrastructure.models
    import tickets.infrastructure.models
