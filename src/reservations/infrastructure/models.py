from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from reservations.domain.enums import ReservationStatus, TicketType
from shared.core.models import Base


class Reservation(Base):
    """예매"""

    __tablename__ = "reservations"

    __table_args__ = (  # table 생성시에 CHECK 제약조건을 삽입함
        CheckConstraint(  # 예매 수량은 0보다 커야 한다
            "quantity > 0", name="ck_reservations_quantity_positive"
        ),
        CheckConstraint(  # 총 금액은 0보다 커야 함 (무료 공연 없음)
            "total_price > 0", name="ck_reservations_total_price_positive"
        ),
        CheckConstraint(  # 할인 금액은 0보다 작을 수 없고 총 금액보다 작거나 같아야 함
            "discount_amount >= 0 AND discount_amount <= total_price",
            name="ck_reservations_discount_range",
        ),
        CheckConstraint(  # 최종 결제 금액 = 총 금액 - 할인 금액 | 대입된 값과 제약조건으로 도출 된 값이 일치하는지 체크
            "final_price = total_price - discount_amount",
            name="ck_reservations_final_price",
        ),
        CheckConstraint(  # 상태가 PENDING 이면 expires_at이 NULL 이면 안됨
            "status <> 'PENDING' OR expires_at IS NOT NULL",
            name="ck_reservations_pending_expires_at",
        ),
        CheckConstraint(  # 상태가 CONFIRMED 이면 confirmed_at이 NULL 이면 안됨
            "status <> 'CONFIRMED' OR confirmed_at IS NOT NULL",
            name="ck_reservations_confirmed_confirmed_at",
        ),
        CheckConstraint(  # 상태가 CANCELED 이면 canceled_at이 NULL 이면 안됨
            "status <> 'CANCELED' OR canceled_at IS NOT NULL",
            name="ck_reservations_canceled_canceled_at",
        ),
    )

    id: Mapped[int] = mapped_column(  # id 값
        BigInteger, primary_key=True, autoincrement=True
    )  # 자동 증감

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)  # 수량
    status: Mapped[ReservationStatus] = mapped_column(
        SQLEnum(
            ReservationStatus, native_enum=False, create_constraint=True, length=20
        ),
        # create_constraint=True = Enum의 값 목록을 CHECK 제약조건으로 변경해서 DDL로 삽입
        default=ReservationStatus.PENDING,
        nullable=False,
    )  # 상태
    total_price: Mapped[int] = mapped_column(Integer, nullable=False)  # 총 금액, 스냅샷
    discount_amount: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # 할인 금액, 스냅샷
    final_price: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # 최종 결제 금액, 스냅샷
    ticket_type: Mapped[TicketType] = mapped_column(
        SQLEnum(TicketType, native_enum=False, create_constraint=True, length=4),
        nullable=False,
    )  # 티켓 타입 [ SAT, SUN, BOTH ]

    expires_at: Mapped[datetime | None] = mapped_column(  # 예매 대기 만료 일시
        DateTime(timezone=True), nullable=True
    )

    confirmed_at: Mapped[datetime | None] = mapped_column(  # 예매 승인 일시
        DateTime(timezone=True), nullable=True
    )

    canceled_at: Mapped[datetime | None] = mapped_column(  # 예매 취소 일시
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(  # 예매 생성 일시
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    updated_at: Mapped[datetime | None] = mapped_column(  # 예매 업데이트 일시
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )

    festival_name: Mapped[str] = mapped_column(String(255), nullable=False)  # 스냅샷
    venue: Mapped[str] = mapped_column(String(255), nullable=False)  # 스냅샷

    user_id: Mapped[int] = mapped_column(  # 예매한 유저
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )

    performance_id: Mapped[int] = mapped_column(  # 예매한 공연
        BigInteger, ForeignKey("performances.id"), nullable=False, index=True
    )
