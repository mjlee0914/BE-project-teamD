from datetime import datetime
from uuid import UUID

from shared.core.schemas import (
    ORMSchema,
)  # from_attributes=True켜져 있어서 도메인 객체에서 속성을 바로 읽어 변환
from tickets.domain.enums import TicketStatus


class TicketDetailResponse(ORMSchema):
    """내 티켓 상세 조회 응답"""

    id: int
    reservation_id: int
    performance_id: int
    ticket_code: UUID
    status: TicketStatus
    price: int
    performance_title: str
    performance_start_at: datetime
    performance_end_at: datetime
    cancel_deadline_at: datetime
    issued_at: datetime | None
    canceled_at: datetime | None
    used_at: datetime | None
    created_at: datetime | None
