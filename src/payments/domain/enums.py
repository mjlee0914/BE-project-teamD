from enum import StrEnum


# 결제 상태
class PaymentStatus(StrEnum):
    READY = "READY"  # 결제 준비 완료
    WAITING_FOR_DEPOSIT = "WAITING_FOR_DEPOSIT"  # 입금 대기
    PAID = "PAID"  # 입금 완료 확인
    FAILED = "FAILED"  # 결제 실패
    EXPIRED = "EXPIRED"  # 입금 기한 만료
    CANCELED = "CANCELED"  # 취소 완료


# 결제 수단
class PaymentMethod(StrEnum):
    VIRTUAL_ACCOUNT = "VIRTUAL_ACCOUNT"  # 가상 계좌
