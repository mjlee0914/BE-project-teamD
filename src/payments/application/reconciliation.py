# 파일 역할: 수동 재조회와 웹훅이 공유하는 결과 반영 절차다. 같은 주문인지 확인한 후 도메인 상태를 갱신한다.

from payments.domain.entities import Payment
from payments.domain.exceptions import PaymentIdentityConflict
from payments.domain.service import PaymentSnapshot


# 주문번호·금액·기존 결제 키가 같은지 먼저 확인해 다른 결제의 조회 결과가 섞이지 않게 한다.
def apply_snapshot(payment: Payment, snapshot: PaymentSnapshot) -> None:
    if (
        snapshot.order_id != payment.order_id
        or snapshot.amount != payment.amount
        or (
            payment.payment_key is not None
            and snapshot.payment_key != payment.payment_key
        )
    ):
        raise PaymentIdentityConflict
    # 소유가 다른 결과를 걸러낸 뒤 도메인의 상태 전이 검사로 넘어간다.
    payment.synchronize(
        status=snapshot.status,
        paid_at=snapshot.paid_at,
        cancelled_at=snapshot.cancelled_at,
        method=snapshot.method if snapshot.method is not None else payment.method,
        webhook_secret_hash=snapshot.webhook_secret_hash,
        log=snapshot.log,
    )
    payment.payment_key = snapshot.payment_key
