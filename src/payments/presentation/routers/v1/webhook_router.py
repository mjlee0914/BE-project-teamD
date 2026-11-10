# 파일 역할: 토스 입금 알림을 받는 HTTP 진입점이다. 사용자 JWT 대신 웹훅 서비스의 secret 검증으로 발신 내용을 확인한다.

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from payments.application.webhook_service import DepositWebhookService
from payments.domain.enums import PaymentStatus
from payments.domain.exceptions import PaymentProcessingError

router = APIRouter(prefix="/v1", tags=["payment-webhooks"])


# 토스의 camelCase 필드를 내부 snake_case로 받는다. 추가 필드는 무시하고 secret은 repr 출력에서 감춘다.
class DepositCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # DEPOSIT_CALLBACK은 일반 상태 웹훅의 data 객체와 달리 최상위 필드를 사용한다.
    event_type: Literal["DEPOSIT_CALLBACK"] | None = Field(
        default=None, alias="eventType"
    )
    order_id: str = Field(alias="orderId", min_length=6, max_length=64)
    # 검증에 쓰는 원문 비밀값이다. repr=False는 로그용 객체 표현에서 감출 뿐 암호화는 아니다.
    secret: str = Field(min_length=1, repr=False)
    transaction_key: str = Field(alias="transactionKey", min_length=1)
    status: PaymentStatus


# 입금 웹훅 서비스의 주입 지점이다. 연결 전에는 503을 내며 알림을 성공 처리하지 않는다.
def provide_deposit_webhook_service() -> DepositWebhookService:
    raise HTTPException(status_code=503, detail="입금 웹훅 서비스 연결이 필요합니다.")


# 입금 알림을 서비스에 전달한다. 재조회가 실패하면 재전송할 수 있게 503, 처리가 끝나면 빈 204를 반환한다.
@router.post("/payments/webhooks/deposit", status_code=204)
async def deposit_callback(
    request: DepositCallbackRequest,
    service: Annotated[DepositWebhookService, Depends(provide_deposit_webhook_service)],
) -> Response:
    try:
        await service.process(
            order_id=request.order_id,
            secret=request.secret,
            transaction_key=request.transaction_key,
            status=request.status,
        )
    except PaymentProcessingError:
        # 조회 실패 시 성공 응답을 주지 않아 토스가 재전송할 수 있게 한다.
        raise HTTPException(
            status_code=503, detail="결제 상태 재조회가 필요합니다."
        ) from None
    # 서비스 반환은 flush 완료까지만 의미한다. 성공 응답 전 DB commit을 보장하는 wiring이 필요하다.
    return Response(status_code=204)
