from payments.domain.repository import PaymentRepository
from payments.domain.entities import Payment
from payments.domain.service import PaymentProcessor
from payments.domain.exceptions import PaymentNotFoundException

from typing import List

class PaymentService:
    def __init__(self, processor: PaymentProcessor, payment_repo: PaymentRepository):
        self.processor = processor
        self.payment_repo = payment_repo
    
    async def get_payments(self, reservation_id: int) -> List[Payment]:
        return await self.payment_repo.find_by_reservation_id(reservation_id)

    async def get_payment(self, payment_id: int) -> Payment:
        payment = await self.payment_repo.find_by_id(payment_id)
        if not payment:
            raise PaymentNotFoundException

        return payment
        
    async def approve(self, payment_id: int, payment_key: str, amount: int):
        payment = await self.get_payment(payment_id)
        await payment.approve(payment_key, amount, self.processor)
        
        
    async def cancel(self, payment_id: int):
        payment = await self.get_payment(payment_id)
        await payment.cancel(self.processor)


    # 결제 등록 - 예약 등록시 함께 생성
    async def create(self, reservation_id: int, festival_name: str, amount: int) -> Payment:
        return await Payment.create(
            reservation_id=reservation_id,
            festival_name=festival_name,
            amount=amount
        )