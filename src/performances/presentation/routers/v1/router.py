from typing import Annotated

from fastapi import APIRouter, Depends, Query

from performances.application.service import PerformanceService
from performances.presentation.dependencies import get_performance_service
from performances.presentation.schemas import (
    AvailabilityResponse,
    PerformanceCreate,
    PerformanceResponse,
    PerformanceUpdate,
)
from shared.core.actor import CurrentActor, get_current_actor
from shared.core.schemas import APIResponse, PageResponse
from users.domain.exceptions import AdminPermissionDenied

# Swagger 그룹: 조회는 "performances", 관리자 전용은 "performances-admin" (엔드포인트마다 tags 지정)
router = APIRouter(prefix="/v1")
# CurrentActorDep, PerformanceServiceDep 별칭 설정 - 의존성은 Annotated 방식으로 통일
CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]
PerformanceServiceDep = Annotated[PerformanceService, Depends(get_performance_service)]

# 관리자 검사 (티켓 라우터와 같은 방식 : 관리자 전용 API는 라우터에서 막음)
def _require_admin(actor: CurrentActor) -> None:
    if not actor.is_admin:
        raise AdminPermissionDenied()

# 인자가 오는 곳 (규칙 붙일 때 쓰는 것)
# - 경로 /performances/5      → performance_id: int  (Path)
# - 쿼리 ?festival_id=1        → festival_id: int     (Query)
# - JSON body                → body: PerformanceCreate (스키마의 Field)

# 공연 회차 등록
# POST /v1/festivals/{festival_id}/performances
@router.post("/festivals/{festival_id}/performances", status_code=201, response_model=APIResponse[PerformanceResponse], tags=["performances-admin"])
async def create_performance(
    festival_id: int,
    body: PerformanceCreate,
    service: PerformanceServiceDep,
    actor: CurrentActorDep,
):
    # 관리자 검사
    _require_admin(actor)
    performance = await service.create_performance(
            festival_id=festival_id,
            title=body.title,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            booking_open_at=body.booking_open_at,
            booking_close_at=body.booking_close_at,
            capacity=body.capacity,
            price=body.price
        )

    return APIResponse.ok(data=PerformanceResponse.model_validate(performance))

# 공연 회차 목록 조회 (축제별)
# GET /v1/festivals/{festival_id}/performances
@router.get("/festivals/{festival_id}/performances", response_model=APIResponse[PageResponse[PerformanceResponse]], tags=["performances"])
async def list_performances(
    festival_id: int,
    service: PerformanceServiceDep,
    page: Annotated[int, Query(ge=1)] = 1, # Query=엔드포인트 함수 인자의 숫자 검사기 역할. "1이상, 100 이하만 받는다" 없으면 서버가 그냥 계산하다 터짐.
    size : Annotated[int, Query(ge=1, le=100)] = 10
):
    performances, total = await service.list_performances(festival_id=festival_id, page=page, size=size)

    items = [PerformanceResponse.model_validate(p) for p in performances]
    page_data = PageResponse.create(items=items, total= total, page=page, size=size)
    return APIResponse.ok(data=page_data)

# 공연 회차 상세 조회
# GET /v1/performances/{performance_id}
@router.get("/performances/{performance_id}", response_model=APIResponse[PerformanceResponse], tags=["performances"])
async def get_performance(performance_id: int, service: PerformanceServiceDep):
    performance = await service.get_performance(performance_id)
    return APIResponse.ok(data=PerformanceResponse.model_validate(performance))

# 공연 회차 정보 수정
# PATCH /v1/performances/{performance_id}
@router.patch("/performances/{performance_id}", response_model=APIResponse[PerformanceResponse], tags=["performances-admin"])
async def update_performance(
    performance_id: int,
    body: PerformanceUpdate,
    service: PerformanceServiceDep,
    actor: CurrentActorDep,
):
    # 관리자 검사
    _require_admin(actor)
    performance = await service.update_performance(
        performance_id=performance_id,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        booking_open_at=body.booking_open_at,
        booking_close_at=body.booking_close_at,
        capacity=body.capacity
    )
    return APIResponse.ok(data=PerformanceResponse.model_validate(performance))


# 상태 변경(오픈/취소/종료)은 API로 직접 전환 → DB의 status 컬럼에 저장
# (Festival은 반대로 별도 API 없이 날짜로 status를 자동 계산)
# 상태 변경 API는 PATCH로 통일 (팀 회의 11/9)
# 공연 예매 오픈
# PATCH /v1/performances/{performance_id}/open
@router.patch("/performances/{performance_id}/open", response_model=APIResponse[PerformanceResponse], tags=["performances-admin"])
async def open_performance(
    performance_id: int,
    service: PerformanceServiceDep,
    actor: CurrentActorDep,
):
    # 관리자 검사
    _require_admin(actor)
    performance = await service.open_performance(performance_id)
    return APIResponse.ok(data=PerformanceResponse.model_validate(performance))

# 공연 취소
# PATCH /v1/performances/{performance_id}/cancel
@router.patch("/performances/{performance_id}/cancel", response_model=APIResponse[PerformanceResponse], tags=["performances-admin"])
async def cancel_performance(
    performance_id: int,
    service: PerformanceServiceDep,
    actor: CurrentActorDep,
):
    # 관리자 검사
    _require_admin(actor)
    performance = await service.cancel_performance(performance_id)
    return APIResponse.ok(data=PerformanceResponse.model_validate(performance))

# 공연 종료
# PATCH /v1/performances/{performance_id}/complete
@router.patch("/performances/{performance_id}/complete", response_model=APIResponse[PerformanceResponse], tags=["performances-admin"])
async def complete_performance(
    performance_id: int,
    service: PerformanceServiceDep,
    actor: CurrentActorDep,
):
    # 관리자 검사
    _require_admin(actor)
    performance = await service.complete_performance(performance_id)
    return APIResponse.ok(data=PerformanceResponse.model_validate(performance))

# 예매 가능 여부 조회
# GET /v1/performances/{performance_id}/availability
@router.get("/performances/{performance_id}/availability", response_model=APIResponse[AvailabilityResponse], tags=["performances"])
async def get_availability(
    performance_id: int,
    service: PerformanceServiceDep
):
    performance, is_bookable = await service.get_availability(performance_id)
    data = AvailabilityResponse(
            performance_id=performance.id,
            is_bookable=is_bookable,
            status=performance.status,
            remaining_count=performance.remaining_count
    )
    return APIResponse.ok(data=data)