# 파일 역할: 결제 HTTP API다. 인증·소유권 확인 → 응용 서비스 호출 → 공개 가능한 응답 필드만 반환하는 순서다.

import os
from pathlib import Path as FilePath
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import HTMLResponse, JSONResponse

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
from shared.core.time import KST

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


# 토스 결제창에서 인증을 마친 뒤 같은 페이지로 돌아와 서버 승인 API를 호출한다.
@router.get("/payments/checkout", response_class=HTMLResponse, include_in_schema=False)
async def checkout_page():
    content = FilePath(__file__).with_name("checkout.html").read_text(encoding="utf-8")
    return HTMLResponse(
        content, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    )


@router.get("/payments/{payment_id}/checkout", summary="토스 결제창 설정 조회")
async def checkout_config(payment: OwnedPayment, service: Service):
    context = await service.checkout_context(payment)
    client_key = os.getenv("TOSS_CLIENT_KEY", "")
    if not client_key.startswith(("test_ck_", "live_ck_")):
        raise HTTPException(
            status_code=503,
            detail="TOSS_CLIENT_KEY에 API 개별 연동 클라이언트 키를 설정해 주세요.",
        )
    return APIResponse.ok(
        data={
            "payment_id": payment.payment_id,
            "client_key": client_key,
            "customer_key": "customer_" + uuid4().hex,
            "order_id": payment.order_id,
            "order_name": payment.reservation.festival_name,
            "amount": payment.amount,
            "deposit_due_at": context.deposit_due_at,
            "virtual_account_due_date": context.deposit_due_at.astimezone(KST).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
        }
    )


def _payment_response(payment: Payment):
    data = APIResponse.ok(data=PaymentResponse.from_domain(payment))
    return JSONResponse(
        status_code=202 if payment.recovery_status else 200,
        content=data.model_dump(mode="json"),
    )


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
    return _payment_response(result)


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
    return _payment_response(result)


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
    return _payment_response(result)
