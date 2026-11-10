# 파일 역할: 결제 HTTP API다. 인증·소유권 확인 → 응용 서비스 호출 → 공개 가능한 응답 필드만 반환하는 순서다.

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse

from auth.domain.entities import TokenPayload
from payments.application.service import PaymentService
from payments.domain.entities import Payment
from payments.domain.exceptions import PaymentProcessingError
from payments.domain.service import PaymentAccessChecker
from payments.presentation.dependencies import (
    provide_current_user,
    provide_payment_access_checker,
    provide_payment_service,
)
from payments.presentation.schemas import (
    ApprovalRequest,
    CancellationRequest,
    PaymentCreateRequest,
    PaymentResponse,
    ReconciliationRequest,
)
from shared.core.schemas import APIResponse

router = APIRouter(prefix="/v1", tags=["payments"])
CurrentUser = Annotated[TokenPayload, Depends(provide_current_user)]
Service = Annotated[PaymentService, Depends(provide_payment_service)]
AccessChecker = Annotated[PaymentAccessChecker, Depends(provide_payment_access_checker)]


# 현재 결제를 읽은 뒤 인증된 회원이 예매 소유자인지 확인한다. 단건 조회·승인·취소·재조회가 이 검사를 공유한다.
async def get_owned_payment(
    payment_id: Annotated[int, Path(gt=0)],
    user: CurrentUser,
    service: Service,
    access: AccessChecker,
) -> Payment:
    payment = await service.get_payment(payment_id)
    await access.ensure_owner(payment.reservation.reservation_id, user.user_id)
    return payment


# 이 타입을 매개변수로 선언한 API는 공통 소유권 검사를 먼저 실행한다.
OwnedPayment = Annotated[Payment, Depends(get_owned_payment)]


@router.post(
    "/payments",
    status_code=201,
    response_model=APIResponse[PaymentResponse],
)
async def create_payment(
    request: PaymentCreateRequest,
    user: CurrentUser,
    service: Service,
):
    payment = await service.create(request.reservation_id, user.user_id)
    return APIResponse.ok(data=PaymentResponse.from_domain(payment))


# 연동 오류를 502 공통 응답으로 바꾸고 오류 코드·결과 불명 여부만 공개한다. 원문 결제 로그는 반환하지 않는다.
def _processing_error(exc: PaymentProcessingError) -> JSONResponse:
    response = APIResponse.fail(
        message="결제사 처리 결과를 확인하지 못했습니다. 결제 상태 확인이 필요합니다.",
        code="PAYMENT_PROCESSING_ERROR",
        errors={"provider_code": exc.code, "outcome_unknown": exc.outcome_unknown},
    )
    # 예외를 다시 던지는 대신 응답으로 돌려줘 진행 기록을 commit할 수 있게 한다.
    # 실제 wiring의 요청 트랜잭션이 정상 반환 시 commit하도록 연결되어 있어야 한다.
    return JSONResponse(status_code=502, content=response.model_dump(mode="json"))


# 목록 조회도 예매 소유권을 먼저 확인한다. 공개 응답 스키마로 바꿔 반환한다.
@router.get("/payments", response_model=APIResponse[list[PaymentResponse]])
async def list_payments(
    reservation_id: Annotated[int, Query(gt=0)],
    user: CurrentUser,
    service: Service,
    access: AccessChecker,
):
    await access.ensure_owner(reservation_id, user.user_id)
    payments = await service.get_payments(reservation_id)
    return APIResponse.ok(
        data=[PaymentResponse.from_domain(payment) for payment in payments]
    )


# 공유 의존성에서 인증·소유권을 통과한 결제만 응답한다.
@router.get("/payments/{payment_id}", response_model=APIResponse[PaymentResponse])
async def get_payment(payment: OwnedPayment):
    return APIResponse.ok(data=PaymentResponse.from_domain(payment))


# 승인 입력을 서비스에 넘긴다. 예상한 결제사 오류는 진행 상태를 보존할 수 있도록 502 응답 객체로 반환한다.
@router.post(
    "/payments/{payment_id}/approve", response_model=APIResponse[PaymentResponse]
)
async def approve_payment(
    request: ApprovalRequest, payment: OwnedPayment, service: Service
):
    try:
        result = await service.approve(
            payment.payment_id, request.payment_key, request.amount
        )
    except PaymentProcessingError as exc:
        return _processing_error(exc)
    return APIResponse.ok(data=PaymentResponse.from_domain(result))


# 요청의 환불 계좌를 도메인 값으로 바꿔 취소를 요청하고, 결과를 공개 응답 스키마로 반환한다.
@router.post(
    "/payments/{payment_id}/cancel", response_model=APIResponse[PaymentResponse]
)
async def cancel_payment(
    request: CancellationRequest, payment: OwnedPayment, service: Service
):
    account = (
        None if request.refund_account is None else request.refund_account.to_domain()
    )
    try:
        result = await service.cancel(
            payment.payment_id, reason=request.reason, refund_account=account
        )
    except PaymentProcessingError as exc:
        return _processing_error(exc)
    return APIResponse.ok(data=PaymentResponse.from_domain(result))


# 소유권 확인 후 결제사 최신 결과를 재조회한다. 통신 실패는 승인·취소와 같은 502 형식으로 전달한다.
@router.post(
    "/payments/{payment_id}/reconcile", response_model=APIResponse[PaymentResponse]
)
async def reconcile_payment(
    request: ReconciliationRequest, payment: OwnedPayment, service: Service
):
    try:
        result = await service.reconcile(payment.payment_id, request.payment_key)
    except PaymentProcessingError as exc:
        return _processing_error(exc)
    return APIResponse.ok(data=PaymentResponse.from_domain(result))
