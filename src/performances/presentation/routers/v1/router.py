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
from shared.core.schemas import APIResponse, PageResponse

router = APIRouter(
    prefix="/v1/performances",
    tags=["performances"],
)

PerformanceServiceDep = Annotated[PerformanceService, Depends(get_performance_service)]

# 공연 회차 등록
# TODO(auth): 관리자 전용 - require_admin 붙이기
# POST ??? (축제 id를 받는 경로 미정: Slack 결정 확인)
@router.post("", status_code=201, response_model=APIResponse[PerformanceResponse])
async def create_performance(
    festival_id: int,
    body: PerformanceCreate,
    service: PerformanceServiceDep
):
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
# GET ??? (축제 id를 받는 경로 미정: Slack 결정 확인)
@router.get("", response_model=APIResponse[PageResponse[PerformanceResponse]])
async def list_performances(
    festival_id: int,
    service: PerformanceServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size : Annotated[int, Query(ge=1, le=100)] = 100
):
    performances, total = await service.list_performances(festival_id=festival_id, page=page, size=size)

    items = [PerformanceResponse.model_validate(p) for p in performances]
    page_data = PageResponse.create(items=items, total= total, page=page, size=size)
    return APIResponse.ok(data=page_data)

# 공연 회차 상세 조회
# GET /v1/performances/{performance_id}
@router.get("/{performance_id}", response_model=APIResponse[PerformanceResponse])
async def get_performance(performance_id: int, service: PerformanceServiceDep):
    performance = await service.get_performance(performance_id)
    return APIResponse.ok(data=PerformanceResponse.model_validate(performance))

# 공연 회차 정보 수정
# TODO(auth): 관리자 전용 - require_admin 붙이기
# PATCH /v1/performances/{performance_id}
@router.patch("/{performance_id}", response_model=APIResponse[PerformanceResponse])
async def update_performance(
    performance_id: int,
    body: PerformanceUpdate,
    service: PerformanceServiceDep
):
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
# TODO(auth): 관리자 전용 - require_admin 붙이기
# PATCH /v1/performances/{performance_id}/open
@router.patch("/{performance_id}/open", response_model=APIResponse[PerformanceResponse])
async def open_performance(
    performance_id: int,
    service: PerformanceServiceDep
):
    performance = await service.open_performance(performance_id)
    return APIResponse.ok(data=PerformanceResponse.model_validate(performance))

# 공연 취소
# TODO(auth): 관리자 전용 - require_admin 붙이기
# PATCH /v1/performances/{performance_id}/cancel
@router.patch("/{performance_id}/cancel", response_model=APIResponse[PerformanceResponse])
async def cancel_performance(
    performance_id: int,
    service: PerformanceServiceDep
):
    performance = await service.cancel_performance(performance_id)
    return APIResponse.ok(data=PerformanceResponse.model_validate(performance))

# 공연 종료
# TODO(auth): 관리자 전용 - require_admin 붙이기
# PATCH /v1/performances/{performance_id}/complete
@router.patch("/{performance_id}/complete", response_model=APIResponse[PerformanceResponse])
async def complete_performance(
    performance_id: int,
    service: PerformanceServiceDep
):
    performance = await service.complete_performance(performance_id)
    return APIResponse.ok(data=PerformanceResponse.model_validate(performance))

# 예매 가능 여부 조회
# GET /v1/performances/{performance_id}/availability
@router.get("/{performance_id}/availability", response_model=APIResponse[AvailabilityResponse])
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