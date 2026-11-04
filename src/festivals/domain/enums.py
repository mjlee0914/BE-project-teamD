from enum import Enum

class FestivalStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"