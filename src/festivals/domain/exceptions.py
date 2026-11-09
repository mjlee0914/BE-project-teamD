from shared.core.exceptions import (
    ConflictException,
    NotFoundException,
    UnprocessableException,
)


# 조회했는데 없음 (service에서 던짐)
class FestivalNotFound(NotFoundException):
    def __init__(self, message: str = "축제를 찾을 수 없습니다."):

        # super 안에 errorcode 지정하면 밖에서 못바꿈 (__init__()매개변수로 두면 raise할때 에러코드 바뀔 수 있음)
        # message는 상황에 따라 바꿀 수 있어야 하므로 매개변수로 열어 두기 
        # 나중에 공통exception 인자가 추가되거나 바뀔 수 있으므로, 키워드 인자로 넘기기
        super().__init__(message=message, error_code="FESTIVAL_NOT_FOUND")

# 시작일 >= 종료일 (엔티티 규칙 4)
class InvalidFestivalPeriod(UnprocessableException):
    def __init__(self, message: str = "축제 시작일은 종료일보다 빨라야 합니다."):
        super().__init__(message=message, error_code="INVALID_FESTIVAL_PERIOD")

# 이미 취소된 축제를 또 취소함 (규칙 8)
class FestivalAlreadyCanceled(ConflictException):
    def __init__(self, message: str = "이미 취소된 축제입니다."):
        super().__init__(message=message, error_code="FESTIVAL_ALREADY_CANCELED")

# 같은 장소에 기간이 겹치는 축제가 있음
class FestivalPeriodOverlap(ConflictException):
    def __init__(self, message: str = "같은 장소에 기간이 겹치는 축제가 있습니다."):
        super().__init__(message=message, error_code="FESTIVAL_PERIOD_OVERLAP")

# 축제기간을 벗어난 공연으로 인해 기간 변경 불가
class FestivalHasPerformanceOutsidePeriod(ConflictException):
    def __init__(self, message: str = "변경할 기간 밖에 있는 공연이 있어 축제 기간을 변경할 수 없습니다."):
        super().__init__(message=message, error_code="FESTIVAL_HAS_PERFORMANCES_OUTSIDE_PERIOD")

# 축제가 취소되지 않은 공연이 있어 축제취소를 못함 (#112)
# 이미 끝난(COMPLETED) 공연도 포함 -> 공연을 먼저 취소해야 축제를 취소할 수 있음
class FestivalHasUncanceledPerformances(ConflictException):
    def __init__(self, message: str = "취소되지 않은 공연이 있어 축제를 취소할 수 없습니다. 공연을 먼저 취소해 주세요."):
        super().__init__(message=message, error_code="FESTIVAL_HAS_UNCANCELED_PERFORMANCES")

class InvalidFestivalName(UnprocessableException):
    def __init__(self, message: str = "유효하지 않은 축제 이름입니다."):
        super().__init__(message=message, error_code="INVALID_FESTIVAL_NAME")

class InvalidFestivalVenue(UnprocessableException):
    def __init__(self, message: str = "유효하지 않은 축제 장소입니다."):
        super().__init__(message=message, error_code="INVALID_FESTIVAL_VENUE")

