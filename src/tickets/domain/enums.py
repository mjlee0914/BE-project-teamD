# 티켓 상태파일. 저장소, 스키마, 테스트에서 전부 사용되기 때문에 따로 작성

from enum import StrEnum


class TicketStatus(StrEnum):
    PENDING = "PENDING"  # 결제대기중
    ISSUED = "ISSUED"  # 티켓 이슈
    CANCELED = "CANCELED"  # 취소
    USED = "USED"  # 사용
    EXPIRED = "EXPIRED"  # 만료
