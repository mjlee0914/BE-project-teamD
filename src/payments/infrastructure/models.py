# 파일 역할: payments 테이블을 정의한다. 상태·금액·시각 제약과 식별자 중복 방지를 DB에서도 검사한다.

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from payments.domain.enums import PaymentStatus
from shared.core.models import Base, DateTimeMixin


# 도메인 Payment를 저장할 테이블이다. 하나의 예매에 여러 결제 행을 둘 수 있고 결제 키 중복은 막는다.
class PaymentModel(DateTimeMixin, Base):
    """예매 하나에 여러 결제 시도를 저장한다. 결제 삭제로 예매를 삭제하지 않는다."""

    __tablename__ = "payments"
    # 애플리케이션 검증 외에도 DB가 금액·상태·필수 시각·키 중복을 마지막으로 방어한다.
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint(
            "status <> 'DONE' OR paid_at IS NOT NULL", name="ck_payments_done_paid_at"
        ),
        CheckConstraint(
            "status <> 'CANCELED' OR canceled_at IS NOT NULL",
            name="ck_payments_canceled_at",
        ),
        UniqueConstraint("payment_key", name="uq_payments_payment_key"),
    )

    # SQLite 변형은 격리된 저장소 테스트용이다. PostgreSQL에는 BIGINT가 생성된다.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    # UNIQUE를 걸지 않아 예매 한 건에 실패 후 재시도한 여러 결제 기록을 연결할 수 있다.
    reservation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reservations.id"), nullable=False, index=True
    )
    # Enum에서 허용값과 CHECK를 생성해 상태 목록을 두 군데서 관리하지 않는다.
    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(
            PaymentStatus,
            name="payment_status",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
        default=PaymentStatus.READY,
    )
    # 결제 수단은 인증 전에는 미정이며 승인 응답의 method 문자열을 저장한다.
    method: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    fail_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 생성·수정 시각은 공통 DateTimeMixin을 따른다. 최초 생성의 updated_at은 NULL이다.
    # PostgreSQL에서는 JSONB다. 내부 메타데이터와 필요한 거래 이력을 한 목록으로 저장한다.
    payment_log: Mapped[list[dict[str, object]]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )


# 기존 JSONB의 메타데이터를 인덱싱한다. 새 컬럼은 추가하지 않는다.
Index(
    "uq_payments_log_order_id",
    PaymentModel.payment_log[0]["_payment_metadata"]["order_id"].as_string(),
    unique=True,
)
