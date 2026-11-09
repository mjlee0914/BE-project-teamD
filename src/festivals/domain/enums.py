from enum import StrEnum


# strEnum() vs Enum()
# strEnum() 자체로 쓰면 FestivalStatus.OPEN 자체를 문자열처럼 사용 가능함
# Enum()으로 사용할 경우 FestivalStatus.OPEN.value로 문자열을 꺼내야 함
class FestivalStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"