#SQLAlchemy가 이 클래스를 보고 SQL을 만들어줌 

import enum
import uuid
from datetime import datetime
from sqlalchemy import(
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    Uuid,
    func
)
from sqlalchemy.orm import Mapped, mapped_column
from shared.core.models import Base


#티켓 상태 상수
from tickets.domain.enums import TicketStatus


#티켓 DB컬럼
class Ticket(Base):
    __tablename__ = "tickets"

    __table_args__=(
        #체크리스트
        CheckConstraint(
            "status IN ('PENDING','ISSUED','CANCELED','USED','EXPIRED')", name="check_tickets_status"),
        CheckConstraint("price > 0", name ="check_ticket_price"),
        CheckConstraint("status <> 'CANCELED' OR canceled_at IS NOT NULL", name ="check_ticket_canceled_at"),
        CheckConstraint("performance_end_at > performance_start_at", name ="check_performance_time"),
        CheckConstraint("status<> 'USED' OR used_at IS NOT NULL", name = "check_ticket_used_at"),
    )

    #테이블 컬럼
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reservation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reservations.id"), index=True)
    performance_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("performances.id"), index=True)

    #enum에 적어둔 PENDING값 꺼내옴.PENDING의 (.value)값! 
    status: Mapped[str] = mapped_column(Text, default= TicketStatus.PENDING.value, index=True)
    
    #uuid1부터 uuid4가지 있는데 uuid4가 완전 무작위
    ticket_code: Mapped[uuid.UUID] = mapped_column(Uuid, unique = True, index=True, default=uuid.uuid4)
    cancel_deadline_at : Mapped[datetime] = mapped_column(DateTime(timezone=True))

    #공연정보 스냅샷
    performance_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    performance_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    performance_title : Mapped[str] = mapped_column(Text)

    #Status 시각
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    #티켓가격
    price: Mapped[int] = mapped_column(Integer)



