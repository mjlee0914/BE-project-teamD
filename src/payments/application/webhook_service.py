# 파일 역할: 가상계좌 입금 알림을 처리한다. 비밀값 검증 → 중복 확인 → 토스 최신 결과 조회 → 저장 순서다.

import hashlib
import hmac

from payments.application.reconciliation import apply_snapshot
from payments.application.service import PaymentService
from payments.domain.enums import PaymentStatus
from payments.domain.exceptions import InvalidPaymentWebhook, PaymentNotFoundException


# 웹훅 자체의 status로 바로 상태를 바꾸지 않고 실제 결제사를 다시 조회하는 응용 서비스다.
class DepositWebhookService:
    # 외부에서 전달받은 의존성을 보관한다. 여기서 DB 연결이나 업무 처리를 새로 시작하지 않는다.
    def __init__(
        self,
        payment_service: PaymentService,
    ):
        self._processor = payment_service.processor
        self._repository = payment_service.payment_repo
        self._payment_service = payment_service

    # 저장된 secret 해시로 알림을 검증하고, 처음 처리하는 거래·상태 조합만 최신 결제 결과로 반영한다.
    async def process(
        self, *, order_id: str, secret: str, transaction_key: str, status: PaymentStatus
    ) -> None:
        payment = await self._repository.find_by_order_id(order_id)
        if payment is None:
            raise PaymentNotFoundException
        await self._repository.lock_reservation(payment.reservation.reservation_id)
        payment = await self._repository.find_by_order_id(order_id)
        # 알림의 비밀값도 해시로 바꿔 저장된 해시와 비교한다. 원문 비밀값은 기록하지 않는다.
        received_hash = hashlib.sha256(secret.encode()).hexdigest()
        if (
            not payment.webhook_secret_hash
            or not payment.payment_key
            or not hmac.compare_digest(payment.webhook_secret_hash, received_hash)
        ):
            raise InvalidPaymentWebhook
        # 발송 ID는 재전송마다 바뀐다. 거래 키와 상태로 중복을 식별한다.
        event_id = hashlib.sha256(
            f"{transaction_key}:{status.value}".encode()
        ).hexdigest()
        # 이미 끝난 이벤트면 외부 재조회와 이력 추가를 반복하지 않는다.
        if event_id in payment.processed_deposit_events:
            await self._payment_service.settle(payment)
            return
        # 오래된 웹훅의 status/시각을 믿지 않고 현재 결제사 상태를 조회한다.
        snapshot = await self._processor.retrieve(payment.payment_key)
        apply_snapshot(payment, snapshot)
        payment.virtual_account_due_at = snapshot.virtual_account_due_at
        payment.processed_deposit_events.append(event_id)
        # 상태와 이벤트 처리 이력을 함께 저장한다. 응답 전 최종 commit은 요청 경계에서 보장해야 한다.
        payment = await self._repository.save(payment)
        await self._payment_service.settle(payment)
