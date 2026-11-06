from abc import ABC, abstractmethod
from payments.domain.entities import Payment
from typing import List

class PaymentRepository:
    @abstractmethod
    async def find_by_id(payment_id: int) -> Payment:
        ...

    @abstractmethod
    async def find_by_reservation_id(reservation_id: int) -> List[Payment]:
        ...

    @abstractmethod
    async def save(payment: Payment) -> Payment:
        ...