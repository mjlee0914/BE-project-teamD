# 파일 역할: SQLAlchemy 모델과 Payment를 서로 변환한다. 예매 연결·잠금·변경 충돌 검사 후 flush하며 commit은 하지 않는다.

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from payments.domain.entities import Payment, PaymentLog, ReservationInfo
from payments.domain.enums import PaymentStatus
from payments.domain.exceptions import (
    PaymentConcurrentUpdate,
    PaymentDuplicateIdentifier,
    PaymentIdentityConflict,
    PaymentNotFoundException,
    PaymentReservationNotFound,
)
from payments.domain.repository import PaymentRepository
from payments.infrastructure.models import PaymentModel
from reservations.infrastructure.models import Reservation as ReservationModel


# JSON 이력의 첫 항목에서 내부 메타데이터를 읽는다. 저장소가 쓰는 정보와 일반 거래 이력을 분리한다.
def _metadata(model: PaymentModel) -> dict[str, object]:
    if model.payment_log and isinstance(model.payment_log[0], dict):
        return model.payment_log[0].get("_payment_metadata", {})
    return {}


# 조회한 모든 컬럼값으로 비교용 해시를 만든다. 저장 시 다른 요청이 행을 바꿨는지 확인하는 기준이다.
def _fingerprint(model: PaymentModel) -> str:
    """조회 시점의 상태를 메모리에만 보관한다. DB 버전 컬럼을 만들지 않는다."""
    values = {
        column.name: getattr(model, column.name) for column in model.__table__.columns
    }
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, default=str).encode()
    ).hexdigest()


# DB 컬럼·JSON 메타데이터·예매의 축제명을 조합해 Payment로 복원하고 현재 행의 비교용 해시도 붙인다.
def _to_domain(model: PaymentModel, festival_name: str) -> Payment:
    metadata = _metadata(model)
    # 기존 데이터에는 provider 응답 로그의 orderId가 있을 수 있다.
    # 메타데이터 → 기존 토스 로그 → 내부 대체 문자열 순서로 복원한다.
    # 마지막 payment-{id} 값은 실제 토스 주문번호를 복구했다는 의미는 아니다.
    order_id = metadata.get("order_id") or next(
        (item["orderId"] for item in model.payment_log if item.get("orderId")),
        f"payment-{model.id}",
    )
    return Payment(
        payment_id=model.id,
        reservation=ReservationInfo(model.reservation_id, festival_name),
        amount=model.amount,
        status=PaymentStatus(model.status),
        payment_key=model.payment_key,
        failed_reason=model.fail_reason,
        paid_at=model.paid_at,
        cancelled_at=model.cancelled_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
        order_id=order_id,
        method=model.method,
        webhook_secret_hash=metadata.get("webhook_secret_hash"),
        processed_deposit_events=list(metadata.get("processed_deposit_events", [])),
        persistence_token=_fingerprint(model),
        payment_log=[
            PaymentLog(deepcopy(item))
            for item in model.payment_log
            if "_payment_metadata" not in item
        ],
    )


# 도메인의 변경 가능한 필드를 ORM에 옮기고, 내부 메타데이터와 거래 이력을 JSON 목록으로 다시 구성한다.
def _apply_changes(model: PaymentModel, payment: Payment) -> None:
    model.status = payment.status.value
    model.method = payment.method
    model.payment_key = payment.payment_key
    model.fail_reason = payment.failed_reason
    model.paid_at = payment.paid_at
    model.cancelled_at = payment.cancelled_at
    # JSON 목록을 통째로 교체해 ORM이 변경을 추적하게 한다.
    # 기존 JSONB 안의 첫 항목에 주문번호·웹훅 검증 해시·처리 이벤트를 저장한다.
    # 전용 컬럼을 추가하지 않은 현재 저장 규칙이므로 조회 쿼리·인덱스도 같은 경로를 사용한다.
    model.payment_log = [
        {
            "_payment_metadata": {
                "order_id": payment.order_id,
                "webhook_secret_hash": payment.webhook_secret_hash,
                "processed_deposit_events": list(payment.processed_deposit_events),
            }
        }
    ] + [deepcopy(log.value) for log in payment.payment_log]


# 도메인 계약을 실제 SQL로 구현한다. 반환값은 ORM 모델이 아니라 Payment 객체다.
class SQLAlchemyPaymentRepository(PaymentRepository):
    """저장소는 flush까지만 수행한다. commit/rollback은 요청 단위에서 처리한다."""

    # 외부에서 전달받은 의존성을 보관한다. 여기서 DB 연결이나 업무 처리를 새로 시작하지 않는다.
    def __init__(self, session: AsyncSession):
        self._session = session

    # 예매 행에 FOR UPDATE를 걸어 같은 예매의 결제 작업을 직렬화한다. 잠금은 트랜잭션이 끝날 때 풀린다.
    async def lock_reservation(self, reservation_id: int) -> None:
        result = await self._session.execute(
            select(ReservationModel.id)
            .where(ReservationModel.id == reservation_id)
            .with_for_update()
        )
        if result.scalar_one_or_none() is None:
            raise PaymentReservationNotFound

    # JSON 내부 주문번호로 찾고 예매와 JOIN해 축제명까지 읽는다. 새 조회값으로 세션 캐시를 갱신한다.
    async def find_by_order_id(self, order_id: str) -> Payment | None:
        result = await self._session.execute(
            select(PaymentModel, ReservationModel.festival_name)
            .join(ReservationModel, PaymentModel.reservation_id == ReservationModel.id)
            .where(
                PaymentModel.payment_log[0]["_payment_metadata"]["order_id"].as_string()
                == order_id
            )
            .execution_options(populate_existing=True, autoflush=False)
        )
        row = result.one_or_none()
        return None if row is None else _to_domain(row[0], row[1])

    # 결제와 예매를 JOIN한 결과를 도메인 객체로 바꾼다. 해당 결제가 없으면 None을 반환한다.
    async def find_by_id(self, payment_id: int) -> Payment | None:
        result = await self._session.execute(
            select(PaymentModel, ReservationModel.festival_name)
            .join(ReservationModel, PaymentModel.reservation_id == ReservationModel.id)
            .where(PaymentModel.id == payment_id)
            .execution_options(populate_existing=True, autoflush=False)
        )
        row = result.one_or_none()
        return None if row is None else _to_domain(row[0], row[1])

    # 같은 예매의 결제 시도를 생성 시각·ID 순서로 읽어 도메인 객체 목록으로 반환한다.
    async def find_by_reservation_id(self, reservation_id: int) -> list[Payment]:
        result = await self._session.execute(
            select(PaymentModel, ReservationModel.festival_name)
            .join(ReservationModel, PaymentModel.reservation_id == ReservationModel.id)
            .where(PaymentModel.reservation_id == reservation_id)
            .order_by(PaymentModel.created_at, PaymentModel.id)
            .execution_options(populate_existing=True, autoflush=False)
        )
        return [_to_domain(model, name) for model, name in result.all()]

    # 예매 존재 확인 → 신규 INSERT 또는 기존 행 잠금·충돌 검사 → flush → refresh → 도메인 반환 순서다.
    async def save(self, payment: Payment) -> Payment:
        # festival_name은 payments에 중복 저장하지 않고 예매 스냅샷에서 읽는다.
        result = await self._session.execute(
            select(ReservationModel.festival_name).where(
                ReservationModel.id == payment.reservation.reservation_id
            )
        )
        festival_name = result.scalar_one_or_none()
        if festival_name is None:
            raise PaymentReservationNotFound

        # ID가 없는 엔티티는 신규 결제이며, ID가 있으면 기존 행을 잠근 뒤 변경을 반영한다.
        if payment.payment_id is None:
            model = PaymentModel(
                reservation_id=payment.reservation.reservation_id,
                amount=payment.amount,
                created_at=payment.created_at,
                updated_at=payment.updated_at,
            )
            _apply_changes(model, payment)
            self._session.add(model)
        else:
            result = await self._session.execute(
                select(PaymentModel)
                .where(PaymentModel.id == payment.payment_id)
                .with_for_update()
                .execution_options(populate_existing=True, autoflush=False)
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise PaymentNotFoundException
            # 최초 조회 때의 값과 잠근 최신 행이 다르면 덮어쓰지 않고 409로 재조회를 요구한다.
            if payment.persistence_token != _fingerprint(model):
                raise PaymentConcurrentUpdate
            if (
                model.reservation_id != payment.reservation.reservation_id
                or _to_domain(model, festival_name).order_id != payment.order_id
                or model.amount != payment.amount
            ):
                raise PaymentIdentityConflict
            _apply_changes(model, payment)
            model.updated_at = datetime.now(UTC)

        try:
            await self._session.flush()
        except IntegrityError as exc:
            message = str(exc.orig)
            if any(
                name in message
                for name in (
                    "uq_payments_log_order_id",
                    "uq_payments_payment_key",
                    "UNIQUE constraint failed: payments.payment_key",
                )
            ):
                raise PaymentDuplicateIdentifier from None
            raise
        # DB에서 채워진 ID·시각 등으로 객체를 갱신한다. commit은 여전히 호출자 책임이다.
        await self._session.refresh(model)
        return _to_domain(model, festival_name)
