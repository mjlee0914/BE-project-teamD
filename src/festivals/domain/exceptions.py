
# 임시 공통 에러클래스 - 공통 exception 이후 교체 예정
class FestivalError(Exception):
    pass

# 조회했는데 없음 (service에서 던짐)
class FestivalNotFound(FestivalError):
    pass

# 시작일 >= 종료일 (엔티티 규칙 4)
class InvalidFestivalPeriod(FestivalError):
    pass

# 이미 취소된 축제를 또 취소함 (규칙 8)
class FestivalAlreadyCanceled(FestivalError):
    pass