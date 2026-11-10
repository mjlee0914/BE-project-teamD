"""
# 엔드포인트 (prefix: /v1/tickets) — 관리자 전용 경로를 따로 두지 않는다
- GET   ""                     티켓 목록: 일반 회원은 내 티켓, 관리자는 전체 검색
- POST  "/enter"               입장 처리 (관리자만)
- GET   "/entry-status"        회차별 입장 현황 (관리자만)
- GET   "/{ticket_id}"         내 티켓 상세
- PATCH "/{ticket_id}/cancel"  내 티켓 취소

# 선언 순서 주의
- 고정 경로("/enter", "/entry-status")를 "/{ticket_id}"보다 먼저 선언한다
  → 반대면 "enter" 같은 글자가 ticket_id(int)로 들어가 422가 남
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query  #status

from shared.core.exceptions import ForbiddenException
from shared.core.schemas import APIResponse, PageResponse
from tickets.application.service import TicketService
from tickets.domain.enums import TicketStatus
from tickets.presentation.dependencies import (
    CurrentActor,
    get_current_actor,
    get_ticket_service,
)
from tickets.presentation.schemas import (
    EntryStatusResponse,
    #TicketCreateRequest,
    TicketDetailResponse,
    TicketEnterRequest,
    TicketEnterResponse,
    TicketListItemResponse,
)

router = APIRouter(prefix="/v1/tickets", tags=["tickets"])

# 타입 + 의존성 주입 방법 묶음
Service = Annotated[TicketService, Depends(get_ticket_service)]
Actor = Annotated[CurrentActor, Depends(get_current_actor)]


# 관리자가 아니면 403 (로그인은 했지만 권한이 없음)
def _require_admin(actor: CurrentActor) -> None:
    if not actor.is_admin:
        raise ForbiddenException("관리자만 이용할 수 있습니다.")


# 티켓 "발급"은 여기서 하지 않는다: 예매가 확정될 때
# ReservationService.confirm_reservation이 _issue_tickets로 자동 발급한다 (#134)
# 여기는 조회·취소·입장·관리자 기능만 담당한다
# 티켓 생성: 승인된 예매의 티켓을 전부 만든다 (양일권 수량 2면 4장)
# @router.post(
#     "",
#     response_model=APIResponse[list[TicketDetailResponse]],
#     status_code=status.HTTP_201_CREATED,
#     summary="티켓 생성",
# )
# async def create_tickets(
#     body: TicketCreateRequest,
#     actor: Actor,
#     service: Service,
# ):
#     tickets = await service.create_tickets(body.reservation_id, actor.user_id)
#     items = [TicketDetailResponse.model_validate(ticket) for ticket in tickets]
#     return APIResponse.ok(data=items)


# 티켓 목록
# - 일반 회원: 내 티켓만 (performance_id는 관리자 전용이라 보내면 403)
# - 관리자  : 전체 티켓 검색 (performance_id로 공연 필터 가능)
@router.get(
    "",
    response_model=APIResponse[PageResponse[TicketListItemResponse]],
    summary="티켓 목록 (회원: 내 티켓 / 관리자: 전체 검색)",
)
async def list_tickets(
    actor: Actor,
    service: Service,
    performance_id: int | None = None,
    ticket_status: Annotated[TicketStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    if actor.is_admin:
        tickets, total = await service.search_tickets(
            performance_id, ticket_status, page, size
        )
    else:
        if performance_id is not None:
            raise ForbiddenException("공연별 조회는 관리자만 이용할 수 있습니다.")
        tickets, total = await service.get_my_tickets(
            actor.user_id, ticket_status, page, size
        )
    items = [TicketListItemResponse.model_validate(ticket) for ticket in tickets]
    page_data = PageResponse.create(items=items, total=total, page=page, size=size)
    return APIResponse.ok(data=page_data)


# 입장 처리 (관리자만)
@router.post(
    "/enter",
    response_model=APIResponse[TicketEnterResponse],
    summary="티켓 입장 처리 (관리자)",
)
async def enter_ticket(
    body: TicketEnterRequest,
    actor: Actor,
    service: Service,
):
    _require_admin(actor)
    ticket = await service.enter_ticket(body.ticket_code)
    return APIResponse.ok(data=TicketEnterResponse.model_validate(ticket))


# 회차별 입장 현황 (관리자만)
@router.get(
    "/entry-status",
    response_model=APIResponse[EntryStatusResponse],
    summary="회차별 입장 현황 (관리자)",
)
async def get_entry_status(
    performance_id: int,
    actor: Actor,
    service: Service,
):
    _require_admin(actor)
    counts = await service.get_entry_status(performance_id)
    data = EntryStatusResponse(performance_id=performance_id, counts=counts)
    return APIResponse.ok(data=data)


# 내 티켓 상세
@router.get(
    "/{ticket_id}",
    response_model=APIResponse[TicketDetailResponse],
    summary="내 티켓 상세 조회",
)
async def get_my_ticket(
    ticket_id: int,
    actor: Actor,
    service: Service,
):
    ticket = await service.get_my_ticket(ticket_id, actor.user_id)
    return APIResponse.ok(data=TicketDetailResponse.model_validate(ticket))


# 내 티켓 취소
@router.patch(
    "/{ticket_id}/cancel",
    response_model=APIResponse[TicketDetailResponse],
    summary="내 티켓 취소",
)
async def cancel_ticket(
    ticket_id: int,
    actor: Actor,
    service: Service,
):
    ticket = await service.cancel_ticket(ticket_id, actor.user_id)
    return APIResponse.ok(data=TicketDetailResponse.model_validate(ticket))
