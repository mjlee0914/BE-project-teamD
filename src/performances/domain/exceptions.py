from shared.core.exceptions import (
    ConflictException,
    NotFoundException,
    UnprocessableException,
)


# 조회했는데 없을 때 (service에서 던짐)
class PerformanceNotFound(NotFoundException):
    def __init__(self, message: str = "공연을 찾을 수 없습니다."):
        super().__init__(message=message, error_code="PERFORMANCE_NOT_FOUND")

# 규칙 2 : InvalidPerformanceTitle
class InvalidPerformanceTitle(UnprocessableException):
    def __init__(self, message = "유효하지 않은 제목입니다."):
        super().__init__(message=message, error_code="INVALID_PERFORMANCE_TITLE")

# 규칙 3 ~ 6, 16 : InvalidPerformancePeriod
class InvalidPerformanceTime(UnprocessableException):
    def __init__(self, message: str = "유효하지 않은 시간입니다."): # 엔티티에서 오류 던질 때 구체적인 메시지 남기기
        super().__init__(message=message, error_code="INVALID_PERFORMANCE_TIME")

# 규칙 7 ~ 9 : InvalidPerformanceCapacity
class InvalidPerformanceCapacity(UnprocessableException):
    def __init__(self, message: str = "허용되지 않는 수량입니다."):
        super().__init__(message=message, error_code="INVALID_PERFORMANCE_CAPACITY")

# 규칙 10 : InvalidPerformancePrice
class InvalidPerformancePrice(UnprocessableException):
    def __init__(self, message: str = "허용되지 않는 금액입니다."):
        super().__init__(message=message, error_code="INVALID_PERFORMANCE_PRICE")

# 규칙 15 및 상태 전이(open/complete/cancel) 실패 : InvalidPerformanceStatus
class InvalidPerformanceStatus(ConflictException):
    def __init__(self, message: str = "현재 상태에서는 변경할 수 없습니다."):
        super().__init__(message=message, error_code="INVALID_PERFORMANCE_STATUS")

# 규칙 20 : 같은 축제 안 공연 제목 중복 - PerformanceTitleDuplicated
class PerformanceTitleDuplicated(ConflictException):
    def __init__(self, message: str="같은 축제 안에서 공연 이름은 중복될 수 없습니다."):
        super().__init__(message=message, error_code="PERFORMANCE_TITLE_DUPLICATED")