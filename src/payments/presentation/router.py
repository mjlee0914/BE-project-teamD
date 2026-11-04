from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from auth.domain.entities import TokenPayload
from auth.presentation.dependencies import get_current_token
from payments.application.service import PaymentService
from payments.presentation.dependencies import get_payment_service
from payments.presentation.schemas import PaymentCreate, PaymentResponse

router = APIRouter(prefix="/payments", tags=["payments"])


def _http_error(exc: PermissionError | LookupError | ValueError) -> HTTPException:
    if isinstance(exc, PermissionError):
        code = 403
    elif isinstance(exc, LookupError):
        code = 404
    else:
        code = 400
    return HTTPException(status_code=code, detail=str(exc))


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=201,
    summary="가상 결제 시도 생성",
    description=(
        "승인 또는 실패한 결제 시도 기록을 생성합니다. "
        "201은 기록 생성 완료를 뜻하며, 승인 여부는 응답의 status로 확인합니다. "
        "현재 단계에서는 예매 확정과 티켓 발급을 수행하지 않습니다."
    ),
    responses={
        400: {"description": "결제 조건 위반"},
        401: {"description": "인증 실패"},
        403: {"description": "다른 회원의 예매"},
        404: {"description": "예매 없음"},
    },
)
async def create_payment(
    payload: PaymentCreate,
    claims: Annotated[TokenPayload, Depends(get_current_token)],
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> PaymentResponse:
    try:
        payment = await service.pay(
            reservation_id=payload.reservation_id,
            user_id=claims.user_id,
            method=payload.method,
            requested_amount=payload.requested_amount,
            simulate_failure=payload.simulate_failure,
        )
    except (PermissionError, LookupError, ValueError) as exc:
        raise _http_error(exc) from exc
    return PaymentResponse.model_validate(payment)


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="본인 결제 조회",
    responses={
        401: {"description": "인증 실패"},
        403: {"description": "조회 권한 없음"},
        404: {"description": "결제 또는 예매 없음"},
    },
)
async def get_payment(
    payment_id: Annotated[int, Path(gt=0)],
    claims: Annotated[TokenPayload, Depends(get_current_token)],
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> PaymentResponse:
    try:
        payment = await service.get_payment(
            payment_id=payment_id, user_id=claims.user_id
        )
    except (PermissionError, LookupError, ValueError) as exc:
        raise _http_error(exc) from exc
    return PaymentResponse.model_validate(payment)


@router.patch(
    "/{payment_id}/cancel",
    response_model=PaymentResponse,
    summary="가상 결제 취소",
    description="예매가 이미 CANCELED인 경우 승인된 결제를 취소합니다.",
    responses={
        400: {"description": "취소 조건 위반"},
        401: {"description": "인증 실패"},
        403: {"description": "취소 권한 없음"},
        404: {"description": "결제 또는 예매 없음"},
    },
)
async def cancel_payment(
    payment_id: Annotated[int, Path(gt=0)],
    claims: Annotated[TokenPayload, Depends(get_current_token)],
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> PaymentResponse:
    try:
        payment = await service.cancel(payment_id=payment_id, user_id=claims.user_id)
    except (PermissionError, LookupError, ValueError) as exc:
        raise _http_error(exc) from exc
    return PaymentResponse.model_validate(payment)
