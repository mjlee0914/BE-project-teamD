# 파일 역할: 결제 상태의 허용 문자열이다. Enum은 상태 이름만 표현하고 상태 변경 판단은 Payment가 담당한다.

from enum import StrEnum


# 토스 응답과 DB 저장에 사용할 상태 이름이다. 상태 변경은 Enum 메서드가 아니라 Payment에서 수행한다.
class PaymentStatus(StrEnum):
    READY = "READY"  # 결제 준비: 아직 승인 요청을 시작하지 않음
    IN_PROGRESS = "IN_PROGRESS"  # 승인 진행 중: 외부 결과 확인이 필요할 수 있음
    WAITING_FOR_DEPOSIT = "WAITING_FOR_DEPOSIT"  # 가상계좌 발급 후 실제 입금을 기다림
    DONE = "DONE"  # 실제 결제 완료
    EXPIRED = "EXPIRED"  # 유효 기간이 지나 종료됨
    ABORTED = "ABORTED"  # 실패가 확정되어 종료됨
    CANCELED = "CANCELED"  # 전액 취소 완료


class PaymentRecoveryStatus(StrEnum):
    CONFIRMATION_PENDING = "CONFIRMATION_PENDING"
    CANCELLATION_PENDING = "CANCELLATION_PENDING"
    REFUND_ACCOUNT_REQUIRED = "REFUND_ACCOUNT_REQUIRED"
