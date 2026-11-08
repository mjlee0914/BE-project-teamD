from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from performances.domain.enums import PerformanceStatus
from shared.core.models import Base, DateTimeMixin


class Performance(DateTimeMixin, Base):
    __tablename__ = "performances"

    # 테이블 전체의 규칙을 모아두는 튜플
    # 컬럼 이름은 문자열로 적는다
    __table_args__ = (
        CheckConstraint(
            # 체크할 제약
            "starts_at < ends_at",
            # 규칙 이름표
            name="ck_performances_start_before_end",
        ),
        CheckConstraint(
            "booking_open_at < booking_close_at",
            name="ck_performances_booking_period",
        ),
        CheckConstraint(
            "capacity > 0",
            name="ck_performances_capacity_positive",
        ),
        CheckConstraint(
            "remaining_count >= 0",
            name="ck_performances_remaining_nonnegative",
        ),
        CheckConstraint(
            "remaining_count <= capacity",
            name="ck_performances_remaining_lte_capacity",
        ),
        CheckConstraint(
            "price > 0",
            name="ck_performances_price_positive",
        ),
        CheckConstraint(
            "cancel_deadline_at <= starts_at",
            name="ck_performances_cancel_before_start",
        ),
        CheckConstraint(
            "booking_close_at <= starts_at",
            name="ck_performances_booking_close_before_start",
        ),
        CheckConstraint(
            "booking_open_at <= cancel_deadline_at",
            name="ck_performances_cancel_after_booking_open",
        ),
        UniqueConstraint(
            # UniqueConstraint=겹치면 안된다는 규칙.
            # 인덱스: 규칙을 빨리 검사하려고 DB가 만드는 정리된 목록
            # --> UniqueConstraint를 사용하면 인덱스가 자동으로 같이 만들어짐. (PostgreSQL 기준)
            # --> 나중에 페스티벌별 정리된 목록 조회시에도 사용 가능
            
            # festival_id와 title 컬럼을 묶어서 이미 있는 다른 공연들의 쌍과 비교한다.
            # 같은 페스티벌-다른 타이틀 ok.
            # 다른 페스티벌-같은 타이틀 ok.
            # 제약조건에 걸리면 DB가 IntegrityError를 던짐 
            # → repository/service에서 잡아서 ConflictException(409)로 변환할 것
            "festival_id",
            "title",
            name="uq_performances_festival_title",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        )
    
    festival_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("festivals.id"),
        nullable=False,
        )

    # 회차명 (ERD 기준) - 화면에 보여줄 이름. 예: "1회차", "DAY 1 - 헤드라이너"
    # 같은 페스티벌 내에서만 중복 안되도록 설정 (A페스티벌 1/2회차, B페스티벌 1/2회차)
    title: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        )
    
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
        )

    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    booking_open_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    booking_close_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    cancel_deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    capacity: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    remaining_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    price:Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    # 낙관적 락 수정 예정.
    version:Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    
    status : Mapped[PerformanceStatus] = mapped_column(
        SQLEnum(
            PerformanceStatus,
            name="performance_status",
            native_enum=False,
            create_constraint=True,
        ),
        default=PerformanceStatus.SCHEDULED,
        nullable=False
    )




    