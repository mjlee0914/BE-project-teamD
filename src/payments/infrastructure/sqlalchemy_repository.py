from payments.domain.repository import PaymentRepository
from payments.domain.entities import Payment
from typing import List

class SQLAlchemyPaymentRepository(PaymentRepository):

    async def find_by_id(payment_id: int) -> Payment:
        ...

    async def find_by_reservation_id(reservation_id: int) -> List[Payment]:
        ...

    async def save(payment: Payment) -> Payment:
        ...