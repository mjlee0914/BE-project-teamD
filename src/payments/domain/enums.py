from enum import StrEnum
from payments.domain.exceptions import PaymentStatusException

# 결제 상태
class PaymentStatus(StrEnum):
    READY = "READY"  # 결제 준비 완료
    IN_PROGRESS = "IN_PROGRESS" # 인증 완료
    WAITING_FOR_DEPOSIT = "WAITING_FOR_DEPOSIT"  # 입금 대기
    DONE = "DONE"  # 입금 완료 확인
    EXPIRED = "EXPIRED"  # 입금 기한 만료
    ABORTED="ABORTED" # 결제 실패
    CANCELED = "CANCELED"  # 취소 완료

    def ready(self):
        self.value = PaymentStatus.READY

    def done(self):
        """결제 완료는 준비중, 진행중, 입금대기 상태에서만 가능"""
        if self.value not in [PaymentStatus.READY, PaymentStatus.IN_PROGRESS, PaymentStatus.WAITING_FOR_DEPOSIT]:
            raise PaymentStatusException

        self.value = PaymentStatus.DONE

    def canceled(self):
        """결제 취소는 입금 완료상태에서만 가능"""
        if self.value != PaymentStatus.DONE:
            raise PaymentStatusException

        self.value = PaymentStatus.CANCELED

    def fail(self):
        """결제 실패는 완료 또는 취소, 실패 상태에서는 변경이 불가"""
        if self.value in [PaymentStatus.DONE, PaymentStatus.CANCELED, PaymentStatus.ABORTED]:
            raise PaymentStatusException

        self.value = PaymentStatus.ABORTED

