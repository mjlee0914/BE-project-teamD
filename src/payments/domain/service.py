from abc import ABC, abstractmethod
from payments.domain.entities import PaymentLog

class PaymentProcessor(ABC):

    @abstractmethod
    async def approve(self, payment_key: str, reservation_id: int, amount: int) -> PaymentLog:
        """결제 승인처리"""


    @abstractmethod
    async def cancel(self, payment_key: str) -> PaymentLog:
        """결제 취소처리"""