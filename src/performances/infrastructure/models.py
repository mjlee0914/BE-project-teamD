from enum import Enum
from datetime import datetime
from sqlalchemy import CheckConstraint, ForeignKey, DateTime, String, BigInteger, Integer, Enum as SQLEnum, func
from sqlalchemy.orm import Mapped, mapped_column
from shared.core.models import Base

class PerformanceStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    OPEN = "OPEN"
    SOLD_OUT = "SOLD_OUT"
    CANCELED = "CANCELED"
    COMPLETED = "COMPLETED"

class Performance(Base):
    __tablename__ = "performances"

    __table_args__ = (
        CheckConstraint(
            "starts_at < ends_at",
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
            "max_tickets_per_user > 0",
            name="ck_performances_max_tickets_positive",
        ),
        CheckConstraint(
            "price >= 0",
            name="ck_performances_price_nonnegative",
        ),
        CheckConstraint(
            "cancellation_deadline_at <= starts_at",
            name="ck_performances_cancellation_before_start",
        ),
        CheckConstraint(
            "booking_close_at <= starts_at",
            name="ck_performances_booking_close_before_start",
        ),
        CheckConstraint(
            "booking_open_at <= cancellation_deadline_at",
            name="ck_performances_cancellation_after_booking_open",
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
    
    title: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True
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

    cancellation_deadline_at: Mapped[datetime] = mapped_column(
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

    max_tickets_per_user: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
        )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(), 
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




    