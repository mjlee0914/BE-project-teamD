from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Dict
from payments.domain.enums import PaymentStatus
from payments.domain.exceptions import InvalidAmountException, PaymentKeyNotFoundException
from payments.domain.service import PaymentProcessor
from shared.core.logger import get_logger

logger = get_logger(__file__)

@dataclass
class ReservationInfo:
    reservation_id: int
    festival_name: str

@dataclass
class PaymentLog:
    value: Dict[str, str]

@dataclass
class Payment:
    payment_id: int
    reservation: ReservationInfo
    status: PaymentStatus
    
    amount: int 
    paid_at: datetime
    payment_key: str

    failed_reason: str

    cancelled_at: datetime
    created_at: datetime
    updated_at: datetime

    payment_log: list[Dict[str, str]] = []


    @classmethod
    def create(
            cls,
            reservation_id: int,
            festival_name: str,
            amount: int,
            status: PaymentStatus = PaymentStatus.READY,     
        ) -> "Payment":

        # 결제금액은 양수
        if amount <= 0:
            raise InvalidAmountException

        return cls(
            reservation=ReservationInfo(reservation_id, festival_name),
            status=status,
            amount=amount
        )


    async def approve(self, payment_key: str, amount: int, processor: PaymentProcessor):
        self.payment_key = payment_key
        if self.amount != amount: # 금액 변조
            raise InvalidAmountException

        # 결제 진행
        try:    
            payment_log = await processor.approve(payment_key, self.reservation.reservation_id, self.amount)
            self.paid_at = datetime.fromisoformat(payment_log["approvedAt"])
            self.add_payment_log(payment_log)

            # 결제 완료 상태 
            self.status.done()

        except Exception as err: # 결제 실패
            self.status.fail()
            self.failed_reason = str(err)
            logger.error(f"결제실패 - 예약 ID: {self.reservation.reservation_id}, 사유: {str(err)}")


    async def cancel(self, processor: PaymentProcessor):
        if not self.payment_key:
            raise PaymentKeyNotFoundException

        try:
            payment_log = await processor.cancel(self.payment_key)
            self.add_payment_log(payment_log)
            self.cancelled_at = datetime.now(timezone.utc)

            # 취소 상태
            self.status.canceled()
        except Exception as err:
            logger.error(f"취소실패 - 예약 ID: {self.reservation.reservation_id}, 사유: {str(err)}")
        
    def add_payment_log(self, log: PaymentLog):
        self.payment_log = self.payment_log or []
        self.payment_log.append(log)