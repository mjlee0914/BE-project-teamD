"""
# presentation/routers/v1/router.py
예매 API 엔드포인트(v1)를 정의하는 파일

# 라우터가 하는 일 (이것만 한다)
① 요청에서 값 꺼내기  : body, path, 로그인 사용자 id
② 서비스 호출         : 판단·계산은 서비스와 도메인이 담당
③ 응답 만들기         : 엔티티 → ReservationResponse 변환 → APIResponse.ok()로 감싸기

# 예외 처리를 여기서 하지 않는 이유
- 서비스·도메인이 던진 예외(ReservationNotFound 404, CancelDeadlineViolation 409 등)는
  공통 예외 핸들러가 받아서 에러 응답으로 바꿔 준다 → 라우터에 try/except 불필요

# 엔드포인트 목록 (prefix : /v1/reservations, 팀 규칙으로 버전 v1 사용)
- POST   ""                          예매 생성
- GET    "/me"                       내 예매 목록
- GET    "/{reservation_id}"         예매 단건 조회
- PATCH  "/{reservation_id}/cancel"  예매 취소

# 선언 순서 주의
- "/me"는 "/{reservation_id}"보다 먼저 선언해야 한다
  → 반대면 "me"가 reservation_id(int)로 들어가 422가 남
"""

# 외부 라이브러리
from fastapi import APIRouter, Depends, status

# 프로젝트 코드
from reservations.application.service import ReservationService
from reservations.presentation.dependencies import (
    get_current_user_id,
    provide_reservation_service,
)
from reservations.presentation.schemas import ReservationCreate, ReservationResponse
from shared.core.logger import get_logger
from shared.core.schemas import APIResponse

logger = get_logger(__file__)

router = APIRouter(prefix="/v1/reservations", tags=["reservations"])


# 예매하기
# - body : ReservationCreate (형식이 틀리면 서비스 호출 전에 422)
# - 생성이므로 201 응답
@router.post(
    "",
    response_model=APIResponse[ReservationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="예매 생성",
)
async def create_reservation(
    body: ReservationCreate,
    service: ReservationService = Depends(provide_reservation_service),
    user_id: int = Depends(get_current_user_id),
):
    # body 객체를 통째로 넘기지 않고 필드를 하나씩 꺼내 키워드 인자로 넘김
    # - user_id만 body가 아닌 로그인 정보에서 받은 값
    reservation = await service.create_reservation(
        festival_id=body.festival_id,
        user_id=user_id,
        ticket_type=body.ticket_type,
        quantity=body.quantity,
        discount_type=body.discount_type,
    )

    return APIResponse.ok(
        data=ReservationResponse.model_validate(reservation),
        # ! model_validate가 아래처럼 필드를 하나씩 옮기는 것과 같음
        # id = reservation.id,
        # festival_id = reservation.festival_id,
        # festival_name = reservation.festival_name,
        # venue = reservation.venue,
        # ticket_type = reservation.ticket_type,
        # quantity = reservation.quantity,
        # total_price = reservation.total_price,
        # discount_type = reservation.discount_type,
        # discount_amount = reservation.discount_amount,
        # final_price = reservation.final_price,
        # status = reservation.status,
        # expires_at = reservation.expires_at,
        # created_at = reservation.created_at
        message="예매가 생성되었습니다.",
    )


# 예매 목록 조회
# - 로그인한 사용자의 예매만 조회
# - 예매가 없으면 404가 아니라 빈 리스트(200)
#   → "/me"라는 목록 자원은 있고 항목이 0개일 뿐이기 때문
@router.get(
    "/me",
    response_model=APIResponse[list[ReservationResponse]],
    summary="예매 목록 조회",
)
async def get_my_reservations(
    service: ReservationService = Depends(provide_reservation_service),
    user_id: int = Depends(get_current_user_id),
):
    # 엔티티 리스트를 하나씩 응답 스키마로 변환
    # - model_validate는 객체 하나만 받으므로 리스트는 항목마다 적용
    responses = []
    get_reservations = await service.get_my_reservations(user_id)
    for reservation in get_reservations:
        responses.append(ReservationResponse.model_validate(reservation))

    return APIResponse.ok(data=responses, message="예매 목록 조회에 성공하였습니다.")


# 예매 단건 조회
# - 없는 예매거나 남의 예매면 서비스가 ReservationNotFound(404)를 던짐
#   → 남의 예매도 403이 아닌 404 : 예매가 존재한다는 사실 자체를 숨기기 위함
@router.get(
    "/{reservation_id}",
    response_model=APIResponse[ReservationResponse],
    summary="예매 단건 조회",
)
async def get_my_reservation(
    reservation_id: int,
    service: ReservationService = Depends(provide_reservation_service),
    user_id: int = Depends(get_current_user_id),
):
    reservation = await service.get_my_reservation(reservation_id, user_id)
    return APIResponse.ok(
        data=ReservationResponse.model_validate(reservation),
        message="예매 단건 조회에 성공하였습니다.",
    )


# 예매 취소
# - 상태만 바꾸는 부분 수정이므로 PATCH
# - 취소 마감이 지났거나 이미 끝난 예매면 서비스·엔티티가 409 예외를 던짐
# - 응답 data는 취소된 예매 (status = CANCELED, canceled_at 기록됨)
@router.patch(
    "/{reservation_id}/cancel",
    response_model=APIResponse[ReservationResponse],
    summary="예매 단건 취소",
)
async def cancel_reservation(
    reservation_id: int,
    service: ReservationService = Depends(provide_reservation_service),
    user_id: int = Depends(get_current_user_id),
):
    reservation = await service.cancel_reservation(reservation_id, user_id)
    return APIResponse.ok(
        data=ReservationResponse.model_validate(reservation),
        message="예매 단건 취소에 성공하였습니다.",
    )
