# 파일 역할: 결제 업무의 실행 순서를 조율한다. 저장소·도메인 규칙·결제사 어댑터를 사용하며 HTTP나 SQL을 직접 작성하지 않는다.

from datetime import UTC, datetime

from payments.application.reconciliation import apply_snapshot
from payments.domain.entities import Payment
from payments.domain.enums import PaymentRecoveryStatus, PaymentStatus
from payments.domain.exceptions import (
    InvalidAmountException,
    PaymentAttemptConflict,
    PaymentIdentityConflict,
    PaymentKeyNotFoundException,
    PaymentNotFoundException,
    PaymentProcessingError,
    PaymentStatusException,
)
from payments.domain.repository import PaymentRepository
from payments.domain.service import (
    PaymentCreationContext,
    PaymentCreationContextProvider,
    PaymentProcessor,
    PaymentTransaction,
    RefundAccount,
)
from reservations.application.service import ReservationService
from reservations.domain.enums import ReservationStatus
from reservations.domain.exceptions import (
    DepositDeadlineViolation,
    InvalidReservationStatus,
)
from shared.core.exceptions import ForbiddenException, SharedException
from shared.core.time import now_utc


# 결제 상태 변경의 순서를 관리한다. 소유권 검사는 이 서비스 호출 전 API 의존성에서 수행한다.
class PaymentService:
    ACTIVE_STATUSES = frozenset(
        {
            PaymentStatus.READY,
            PaymentStatus.IN_PROGRESS,
            PaymentStatus.WAITING_FOR_DEPOSIT,
            PaymentStatus.DONE,
        }
    )

    # 외부에서 전달받은 의존성을 보관한다. 여기서 DB 연결이나 업무 처리를 새로 시작하지 않는다.
    def __init__(
        self,
        processor: PaymentProcessor,
        payment_repo: PaymentRepository,
        creation_context_provider: PaymentCreationContextProvider,
        reservation_service: ReservationService,
        transaction: PaymentTransaction,
    ):
        self.processor = processor
        self.payment_repo = payment_repo
        self.creation_context_provider = creation_context_provider
        self.reservation_service = reservation_service
        self.transaction = transaction

    # 한 예매의 여러 결제 시도를 저장소에서 조회한다. 소유권은 호출자가 먼저 검증해야 한다.
    async def get_payments(self, reservation_id: int) -> list[Payment]:
        return await self.payment_repo.find_by_reservation_id(reservation_id)

    # 저장된 결제를 반환하고, 식별자에 대응하는 결제가 없으면 404 예외를 발생시킨다.
    async def get_payment(self, payment_id: int) -> Payment:
        payment = await self.payment_repo.find_by_id(payment_id)
        if payment is None:
            raise PaymentNotFoundException
        return payment

    # 예매 잠금 → 최신 결제 재조회 → 중복·금액 검사 → 진행 상태 저장 → 토스 승인 → 결과 저장 순서다.
    async def approve(self, payment_id: int, payment_key: str, amount: int) -> Payment:
        payment = await self.get_payment(payment_id)
        await self.payment_repo.lock_reservation(payment.reservation.reservation_id)
        payment = await self.get_payment(payment_id)
        if (
            payment.status in (PaymentStatus.DONE, PaymentStatus.WAITING_FOR_DEPOSIT)
            and payment.payment_key == payment_key
            and type(amount) is int
            and payment.amount == amount
        ):
            return await self.settle(payment)
        payment.ensure_approvable(payment_key, amount)
        retrying_unknown_approval = payment.status == PaymentStatus.IN_PROGRESS
        await self._ensure_reservation_payable(payment.reservation.reservation_id)
        attempts = await self.payment_repo.find_by_reservation_id(
            payment.reservation.reservation_id
        )
        # 같은 예매에 다른 진행 중·완료 시도가 있으면 새 승인으로 중복 결제하지 못하게 한다.
        if any(
            attempt.payment_id != payment_id
            and attempt.status in self.ACTIVE_STATUSES - {PaymentStatus.READY}
            for attempt in attempts
        ):
            raise PaymentAttemptConflict
        payment.start_approval(payment_key, amount)
        # 오류 응답에도 이 진행 상태를 commit해야 결과 불명의 결제를 새 시도로 덮지 않는다.
        payment = await self.payment_repo.save(payment)
        # 외부 승인 이후 프로세스가 중단돼도 재조회할 키가 남도록 먼저 확정한다.
        await self.transaction.checkpoint()
        await self.payment_repo.lock_reservation(payment.reservation.reservation_id)
        payment = await self.get_payment(payment_id)
        await self._ensure_reservation_payable(payment.reservation.reservation_id)
        # 여기서 외부 HTTP 요청이 발생한다. 통신 실패가 실제 승인 실패를 뜻하지는 않는다.
        # 위 save는 flush까지만 하므로 프로세스 중단·전체 rollback 시 진행 기록도 사라질 수 있다.
        try:
            result = await self.processor.approve(payment_key, payment.order_id, amount)
        except PaymentProcessingError as exc:
            # 확정된 거절은 종료해 새 결제를 허용한다. 결과 불명은 재조회할 수 있도록 유지한다.
            if not exc.outcome_unknown and not retrying_unknown_approval:
                payment.fail(exc.code)
                await self.payment_repo.save(payment)
            elif retrying_unknown_approval and not exc.outcome_unknown:
                # 이번 거절이 이전 요청의 성공 여부까지 증명하지는 않는다.
                raise PaymentProcessingError(
                    "이전 승인 결과 재조회가 필요합니다.",
                    code=exc.code,
                    http_status=exc.http_status,
                    outcome_unknown=True,
                ) from None
            # 라우터가 502 응답으로 변환하면 요청 세션이 실패 상태도 commit한다.
            raise
        payment.approve(
            payment_key,
            amount,
            result.status,
            result.paid_at,
            result.log,
            result.method,
            result.webhook_secret_hash,
        )
        payment.virtual_account_due_at = result.virtual_account_due_at
        payment = await self.payment_repo.save(payment)
        return await self.settle(payment)

    # 응답 유실 등으로 결과가 불분명할 때 결제사를 재조회한다. 확인된 같은 주문의 결과만 저장한다.
    async def reconcile(
        self, payment_id: int, payment_key: str | None = None
    ) -> Payment:
        """승인 응답 유실 등을 복구한다. 호출자는 소유자/운영 권한을 검증해야 한다."""
        payment = await self.get_payment(payment_id)
        await self.payment_repo.lock_reservation(payment.reservation.reservation_id)
        payment = await self.get_payment(payment_id)
        key = payment_key or payment.payment_key
        if not key:
            raise PaymentKeyNotFoundException
        if payment.payment_key is not None and payment.payment_key != key:
            raise PaymentIdentityConflict
        # 브라우저가 주장하는 상태 대신 토스가 저장한 실제 현재 상태를 확인한다.
        snapshot = await self.processor.retrieve(key)
        if snapshot.payment_key != key:
            raise PaymentIdentityConflict
        apply_snapshot(payment, snapshot)
        payment.virtual_account_due_at = snapshot.virtual_account_due_at
        payment = await self.payment_repo.save(payment)
        return await self.settle(payment)

    # 같은 예매의 요청을 잠근 뒤 전액 취소한다. 이미 취소된 결제에는 외부 취소를 반복하지 않는다.
    async def cancel(
        self,
        payment_id: int,
        *,
        reason: str = "고객 요청",
        refund_account: RefundAccount | None = None,
    ) -> Payment:
        payment = await self.get_payment(payment_id)
        await self.payment_repo.lock_reservation(payment.reservation.reservation_id)
        payment = await self.get_payment(payment_id)
        # 토스 호출 전에 예매·티켓 취소와 재고 복구를 확정한다.
        await self._cancel_reservation(payment)
        if payment.status == PaymentStatus.CANCELED:
            return payment
        return await self._cancel_pending(payment, reason, refund_account)

    async def _cancel_reservation(
        self, payment: Payment, *, force: bool = False
    ) -> None:
        context = await self.creation_context_provider.get_context(
            payment.reservation.reservation_id
        )
        if context and context.reservation_status in (
            ReservationStatus.PENDING,
            ReservationStatus.CONFIRMED,
        ):
            if force:
                await self.reservation_service.release_for_payment_failure(
                    context.reservation_id
                )
            else:
                await self.reservation_service.cancel_reservation(
                    context.reservation_id, context.user_id, False
                )

    async def settle(self, payment: Payment) -> Payment:
        """결제사에서 확인한 결과와 예매를 연결한다. 불일치는 복구 대상으로 남긴다."""
        context = await self.creation_context_provider.get_context(
            payment.reservation.reservation_id
        )
        if context is None:
            raise PaymentStatusException("결제에 연결된 예매를 찾을 수 없습니다.")
        if payment.status == PaymentStatus.CANCELED:
            await self._cancel_reservation(payment, force=True)
            if payment.recovery_status or payment.recovery_error:
                payment.recovery_status = None
                payment.recovery_error = None
                return await self.payment_repo.save(payment)
            return payment
        if payment.recovery_status in (
            PaymentRecoveryStatus.CANCELLATION_PENDING,
            PaymentRecoveryStatus.REFUND_ACCOUNT_REQUIRED,
        ):
            return await self._cancel_pending(payment)
        unavailable = context.reservation_status in (
            ReservationStatus.CANCELED,
            ReservationStatus.EXPIRED,
        )
        expired = (
            context.reservation_status == ReservationStatus.PENDING
            and context.expires_at
            and self._utc(context.expires_at) <= now_utc()
        )
        if unavailable or expired:
            await self._cancel_reservation(payment, force=True)
            return await self._cancel_pending(payment)
        if payment.status == PaymentStatus.WAITING_FOR_DEPOSIT:
            due = payment.virtual_account_due_at
            # 화면에서 마감 시각을 늘려 보냈거나 발급 기한이 지난 계좌는 즉시 반납한다.
            if (
                due is None
                or context.deposit_due_at is None
                or self._utc(due) > self._utc(context.deposit_due_at)
                or self._utc(due) <= now_utc()
            ):
                await self._cancel_reservation(payment, force=True)
                return await self._cancel_pending(payment, "가상계좌 입금 마감 불일치")
            if context.reservation_status == ReservationStatus.CONFIRMED:
                await self._cancel_reservation(payment, force=True)
                return await self._cancel_pending(payment, "입금 취소 감지")
            return payment
        if payment.status != PaymentStatus.DONE:
            return payment
        try:
            async with self.transaction.savepoint():
                await self.reservation_service.confirm_reservation(
                    payment.reservation.reservation_id
                )
        except (DepositDeadlineViolation, InvalidReservationStatus):
            await self._cancel_reservation(payment, force=True)
            return await self._cancel_pending(payment, "예매 확정 불가")
        except SharedException as exc:
            # 티켓 저장 충돌 등은 결제 결과를 지우지 않고 다음 주기에 확정을 재시도한다.
            payment.recovery_status = PaymentRecoveryStatus.CONFIRMATION_PENDING
            payment.recovery_error = exc.error_code
            return await self.payment_repo.save(payment)
        if payment.recovery_status or payment.recovery_error:
            payment.recovery_status = None
            payment.recovery_error = None
            return await self.payment_repo.save(payment)
        return payment

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    async def _cancel_pending(
        self,
        payment: Payment,
        reason: str = "예매 취소 또는 만료",
        refund_account: RefundAccount | None = None,
    ) -> Payment:
        payment.recovery_status = PaymentRecoveryStatus.CANCELLATION_PENDING
        payment.cancellation_reason = payment.cancellation_reason or reason
        payment = await self.payment_repo.save(payment)
        # 취소 의도를 먼저 commit한다. 외부 호출 실패·프로세스 종료 후에도 작업자가 찾는다.
        await self.transaction.checkpoint()
        await self.payment_repo.lock_reservation(payment.reservation.reservation_id)
        payment = await self.get_payment(payment.payment_id)
        if payment.status in (
            PaymentStatus.CANCELED,
            PaymentStatus.ABORTED,
            PaymentStatus.EXPIRED,
        ):
            payment.recovery_status = None
            return await self.payment_repo.save(payment)
        if payment.status == PaymentStatus.READY:
            payment.fail("RESERVATION_CANCELED")
        else:
            try:
                # 입금과 취소가 경합할 수 있어 현재 토스 상태를 먼저 확인한다.
                snapshot = await self.processor.retrieve(payment.payment_key)
                apply_snapshot(payment, snapshot)
                if payment.status == PaymentStatus.IN_PROGRESS:
                    raise PaymentProcessingError(
                        "토스 승인 진행 중으로 취소 결과 재조회가 필요합니다.",
                        code="TOSS_PAYMENT_PENDING",
                        outcome_unknown=True,
                    )
                if payment.status in (
                    PaymentStatus.CANCELED,
                    PaymentStatus.ABORTED,
                    PaymentStatus.EXPIRED,
                ):
                    payment.recovery_status = None
                    return await self.payment_repo.save(payment)
                if (
                    payment.status == PaymentStatus.DONE
                    and payment.method == "가상계좌"
                    and refund_account is None
                ):
                    payment.recovery_status = (
                        PaymentRecoveryStatus.REFUND_ACCOUNT_REQUIRED
                    )
                    return await self.payment_repo.save(payment)
                result = await self.processor.cancel(
                    payment.ensure_cancelable(),
                    reason=payment.cancellation_reason,
                    refund_account=refund_account,
                )
                payment.cancel(result.canceled_at, result.log)
            except PaymentProcessingError as exc:
                payment.recovery_error = exc.code
                await self.payment_repo.save(payment)
                raise
        payment.recovery_status = None
        payment.recovery_error = None
        return await self.payment_repo.save(payment)

    async def recover(self, payment_id: int) -> Payment:
        payment = await self.get_payment(payment_id)
        await self.payment_repo.lock_reservation(payment.reservation.reservation_id)
        payment = await self.get_payment(payment_id)
        context = await self.creation_context_provider.get_context(
            payment.reservation.reservation_id
        )
        if payment.recovery_status in (
            PaymentRecoveryStatus.CANCELLATION_PENDING,
            PaymentRecoveryStatus.REFUND_ACCOUNT_REQUIRED,
        ) or (
            context
            and context.reservation_status
            in (ReservationStatus.CANCELED, ReservationStatus.EXPIRED)
        ):
            return await self._cancel_pending(payment)
        if payment.status == PaymentStatus.IN_PROGRESS:
            snapshot = await self.processor.retrieve(payment.payment_key)
            apply_snapshot(payment, snapshot)
            payment.virtual_account_due_at = snapshot.virtual_account_due_at
            payment = await self.payment_repo.save(payment)
        return await self.settle(payment)

    # Create a payment attempt from trusted reservation data.
    async def _get_owned_reservation_context(
        self, reservation_id: int, user_id: int
    ) -> PaymentCreationContext:
        context = await self.creation_context_provider.get_context(reservation_id)
        if context is None or context.user_id != user_id:
            raise ForbiddenException("본인 예매에 연결된 결제만 처리할 수 있습니다.")
        return context

    @staticmethod
    def _validate_reservation_payable(context: PaymentCreationContext) -> None:
        if context.reservation_status != ReservationStatus.PENDING:
            raise PaymentStatusException("대기 중인 예매만 결제할 수 있습니다.")
        expires_at = context.expires_at
        if expires_at is None:
            raise PaymentStatusException("예매 만료 시각이 없어 결제할 수 없습니다.")
        # Some database drivers return naive values even for timezone-aware columns.
        # Interpret stored naive timestamps as UTC before comparing.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now_utc():
            raise PaymentStatusException(
                "예매 대기 시간이 만료되어 결제할 수 없습니다."
            )

    async def _ensure_reservation_payable(self, reservation_id: int) -> None:
        context = await self.creation_context_provider.get_context(reservation_id)
        if context is None:
            raise PaymentStatusException("결제에 연결된 예매를 찾을 수 없습니다.")
        self._validate_reservation_payable(context)

    async def create(self, reservation_id: int, user_id: int) -> Payment:
        # Check ownership before taking a row lock for another user's reservation.
        context = await self._get_owned_reservation_context(reservation_id, user_id)
        await self.payment_repo.lock_reservation(reservation_id)
        # Reload after locking so concurrent status and expiry updates are observed.
        context = await self._get_owned_reservation_context(reservation_id, user_id)
        self._validate_reservation_payable(context)
        if context.amount <= 0:
            raise InvalidAmountException(
                "결제 금액이 0원이면 결제 시도를 만들 수 없습니다."
            )
        attempts = await self.payment_repo.find_by_reservation_id(reservation_id)
        if any(
            attempt.status in self.ACTIVE_STATUSES - {PaymentStatus.READY}
            for attempt in attempts
        ):
            raise PaymentAttemptConflict
        # Reuse a READY order when the client retries after closing the checkout.
        ready_attempt = next(
            (attempt for attempt in attempts if attempt.status == PaymentStatus.READY),
            None,
        )
        if ready_attempt is not None:
            return ready_attempt
        payment = Payment.create(
            reservation_id=reservation_id,
            festival_name=context.festival_name,
            amount=context.amount,
        )
        return await self.payment_repo.save(payment)

    async def checkout_context(self, payment: Payment) -> PaymentCreationContext:
        if payment.status != PaymentStatus.READY:
            raise PaymentStatusException("새 결제창은 READY 결제에서만 열 수 있습니다.")
        context = await self.creation_context_provider.get_context(
            payment.reservation.reservation_id
        )
        if context is None:
            raise PaymentStatusException("결제에 연결된 예매를 찾을 수 없습니다.")
        self._validate_reservation_payable(context)
        return context
