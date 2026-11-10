"""
# presentation/dependencies.py
라우터가 Depends()로 받아 쓰는 의존성 함수(자리표시자) 모음
- 실제 구현은 wiring/reservation.py가 app.dependency_overrides로 끼워 넣는다
- 교체 전에 호출하면 NotImplementedError → 500 (라우터 버그가 아님)
"""

# 프로젝트 코드
from reservations.application.service import ReservationService


# 예매 서비스 제공 → wiring의 build_reservation_service로 교체됨
def provide_reservation_service() -> ReservationService:
    raise NotImplementedError("reservation_service 의존성이 주입되지 않았습니다.")
