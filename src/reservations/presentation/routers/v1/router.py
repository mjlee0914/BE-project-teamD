"""
# presentation/routers/v1/router.py
예매 API 엔드포인트(v1)

# 라우터가 하는 일 (이것만 한다)
① 요청에서 값 꺼내기 → ② 서비스 호출 → ③ 응답 만들기
- 예외는 공통 예외 핸들러가 에러 응답으로 바꿔 줌 → try/except 불필요

# 엔드포인트
[router : /v1/reservations]
- POST   ""                          예매 생성
- GET    "/me"                       내 예매 목록
- GET    "/{reservation_id}"         예매 단건 조회 (본인 또는 관리자)
- PATCH  "/{reservation_id}/cancel"  예매 취소 (본인 또는 관리자)
[admin_router : /v1/festivals]  #117
- GET    "/{festival_id}/reservations"  축제별 예매 목록 (관리자 전용)

# 선언 순서 주의 : "/me"는 "/{reservation_id}"보다 먼저 (반대면 "me"가 id로 들어가 422)
"""

# 외부 라이브러리
from fastapi import APIRouter, Depends, Query, status

# 프로젝트 코드
from reservations.application.service import ReservationService
from reservations.domain.enums import ReservationStatus
from reservations.presentation.dependencies import (
    CurrentActor,
    get_current_actor,
    provide_reservation_service,
)
from reservations.presentation.schemas import ReservationCreate, ReservationResponse
from shared.core.enums import TicketType
from shared.core.schemas import APIResponse, PageResponse

router = APIRouter(prefix="/v1/reservations", tags=["reservations"])

# 관리자 목록은 주소가 /v1/festivals/... 로 시작해서 prefix가 다른 라우터를 하나 더 둠
# → main.py에서 include_router(reservation_admin_router)를 추가해야 함
admin_router = APIRouter(prefix="/v1/festivals", tags=["reservations-admin"])


# 예매 생성 (201)
@router.post(
    "",
    response_model=APIResponse[ReservationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="예매 생성",
)
async def create_reservation(
    body: ReservationCreate,
    service: ReservationService = Depends(provide_reservation_service),
    actor: CurrentActor = Depends(get_current_actor),
):
    reservation = await service.create_reservation(
        festival_id=body.festival_id,
        user_id=actor.user_id,  # user_id는 body가 아닌 토큰에서
        ticket_type=body.ticket_type,
        quantity=body.quantity,
        discount_type=body.discount_type,
    )
    return APIResponse.ok(
        data=ReservationResponse.model_validate(reservation),
        message="예매가 생성되었습니다.",
    )


# 내 예매 목록 (없으면 빈 리스트 200)
@router.get(
    "/me",
    response_model=APIResponse[list[ReservationResponse]],
    summary="예매 목록 조회",
)
async def get_my_reservations(
    service: ReservationService = Depends(provide_reservation_service),
    actor: CurrentActor = Depends(get_current_actor),
):
    reservations = await service.get_my_reservations(actor.user_id)
    responses = [ReservationResponse.model_validate(r) for r in reservations]
    return APIResponse.ok(data=responses, message="예매 목록 조회에 성공하였습니다.")


# 예매 단건 조회 (일반 회원이 남의 예매를 보면 404)
@router.get(
    "/{reservation_id}",
    response_model=APIResponse[ReservationResponse],
    summary="예매 단건 조회",
)
async def get_reservation(
    reservation_id: int,
    service: ReservationService = Depends(provide_reservation_service),
    actor: CurrentActor = Depends(get_current_actor),
):
    reservation = await service.get_reservation(
        reservation_id, actor.user_id, actor.is_admin
    )
    return APIResponse.ok(
        data=ReservationResponse.model_validate(reservation),
        message="예매 단건 조회에 성공하였습니다.",
    )


# 예매 취소 (상태만 바꾸는 부분 수정이라 PATCH)
@router.patch(
    "/{reservation_id}/cancel",
    response_model=APIResponse[ReservationResponse],
    summary="예매 단건 취소",
)
async def cancel_reservation(
    reservation_id: int,
    service: ReservationService = Depends(provide_reservation_service),
    actor: CurrentActor = Depends(get_current_actor),
):
    reservation = await service.cancel_reservation(
        reservation_id, actor.user_id, actor.is_admin
    )
    return APIResponse.ok(
        data=ReservationResponse.model_validate(reservation),
        message="예매 단건 취소에 성공하였습니다.",
    )


# 축제별 예매 목록 (관리자 전용, #117)
# - day      : ?day=SAT → 토요일 회차 예매 (SAT + BOTH)
# - statuses : ?statuses=PENDING&statuses=CONFIRMED (여러 개 가능)
# - 리스트 쿼리는 Query()를 붙여야 FastAPI가 body가 아닌 쿼리로 읽음
@admin_router.get(
    "/{festival_id}/reservations",
    response_model=APIResponse[PageResponse[ReservationResponse]],
    summary="축제별 예매 목록 (관리자)",
)
async def list_festival_reservations(
    festival_id: int,
    day: TicketType | None = Query(None, description="SAT 또는 SUN"),
    statuses: list[ReservationStatus] | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    service: ReservationService = Depends(provide_reservation_service),
    actor: CurrentActor = Depends(get_current_actor),
):
    items, total = await service.list_festival_reservations(
        festival_id=festival_id,
        is_admin=actor.is_admin,
        day=day,
        statuses=statuses,
        page=page,
        size=size,
    )
    return APIResponse.ok(
        data=PageResponse.create(
            items=[ReservationResponse.model_validate(r) for r in items],
            total=total,
            page=page,
            size=size,
        ),
        message="축제별 예매 목록 조회에 성공하였습니다.",
    )
