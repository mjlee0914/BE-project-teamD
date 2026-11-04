from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from payments.domain.entities import PaymentStatus
from shared.core.models import Base, DateTimeMixin


class PaymentModel(DateTimeMixin, Base):
    """예매 한 건에 연결되는 가상 결제 시도 한 건."""

    __tablename__ = "payments"

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_payments_amount_nonnegative"),
        CheckConstraint(
            "length(trim(method)) > 0", name="ck_payments_method_not_blank"
        ),
        CheckConstraint(
            "payment_key IS NULL OR length(trim(payment_key)) > 0",
            name="ck_payments_key_not_blank",
        ),
        CheckConstraint(
            "status NOT IN ('PAID', 'CANCELED') "
            "OR (paid_at IS NOT NULL AND payment_key IS NOT NULL)",
            name="ck_payments_approved_details_required",
        ),
        CheckConstraint(
            "status <> 'FAILED' "
            "OR (fail_reason IS NOT NULL AND length(trim(fail_reason)) > 0)",
            name="ck_payments_failure_reason_required",
        ),
        CheckConstraint(
            "status <> 'CANCELED' OR canceled_at IS NOT NULL",
            name="ck_payments_cancellation_time_required",
        ),
        CheckConstraint(
            "canceled_at IS NULL OR (paid_at IS NOT NULL AND canceled_at >= paid_at)",
            name="ck_payments_cancellation_after_approval",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(
            PaymentStatus,
            name="payment_status",
            native_enum=False,
            create_constraint=True,
            length=20,
        ),
        default=PaymentStatus.READY,
        server_default=PaymentStatus.READY.value,
        nullable=False,
    )

    method: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)

    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fail_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    reservation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("reservations.id"),
        nullable=False,
        index=True,
    )

    payment_key: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    payment_log: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
