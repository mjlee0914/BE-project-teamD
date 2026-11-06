from payments.domain.service import PaymentProcessor
from payments.domain.entities import PaymentLog

class TossPaymentProcessor(PaymentProcessor):
    async def approve(self, payment_key: str, reservation_id: int, amount: int) -> PaymentLog:
        """결제 승인처리"""
    
    
    async def cancel(self, payment_key: str) -> PaymentLog:
        """결제 취소처리"""