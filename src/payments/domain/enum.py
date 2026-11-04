from enum import Enum

class PaymentStatus(str, Enum):
    READY = "READY"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELED = "CANCELED"