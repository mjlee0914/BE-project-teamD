# API 요청·응답의 모양을 정하는 Pydantic 스키마
# 도메인 Ticket을 그대로 내보내지 않고, 밖에 보여 줄 필드만 골라 담는다

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from shared.core.schemas import ORMSchema
from tickets.domain.enums import TicketStatus

# 티켓 생성 요청 (POST /v1/tickets): 어느 예매의 티켓을 만들지만 받는다
# 가격·공연 정보는 서버가 조회하고, user_id는 로그인 정보에서 꺼낸다
# class TicketCreateRequest(BaseModel):
#     reservation_id: int


# 입장 요청 (POST /v1/tickets/enter)
class TicketEnterRequest(BaseModel):
    ticket_code: UUID


# 티켓 상세 응답 (상세 조회, 생성, 취소 공통)
class TicketDetailResponse(ORMSchema):
    ticket_id: int = Field(validation_alias="id")
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


# 목록 항목 응답 (내 목록, 관리자 검색 공통)
class TicketListItemResponse(ORMSchema):
    ticket_id: int = Field(validation_alias="id")
    reservation_id: int
    performance_id: int
    status: TicketStatus
    price: int
    performance_title: str
    performance_start_at: datetime
    created_at: datetime | None


# 입장 처리 응답
class TicketEnterResponse(ORMSchema):
    ticket_id: int = Field(validation_alias="id")
    status: TicketStatus
    used_at: datetime | None


# 회차별 입장 현황 응답: 모든 상태의 개수 (없는 상태는 0)
class EntryStatusResponse(BaseModel):
    performance_id: int
    counts: dict[TicketStatus, int]
