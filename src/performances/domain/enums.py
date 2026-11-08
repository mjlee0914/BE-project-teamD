from enum import StrEnum


class PerformanceStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    OPEN = "OPEN"
    SOLD_OUT = "SOLD_OUT"
    CANCELED = "CANCELED"
    COMPLETED = "COMPLETED"