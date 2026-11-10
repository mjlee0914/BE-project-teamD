"""
# presentation/dependencies.py
라우터가 Depends()로 받아 쓰는 의존성 함수(자리표시자) 모음
- 실제 구현은 wiring/reservation.py가 app.dependency_overrides로 끼워 넣는다
- 교체 전에 호출하면 NotImplementedError → 500 (라우터 버그가 아님)
"""

# 표준 라이브러리
from dataclasses import dataclass

# 프로젝트 코드
from reservations.application.service import ReservationService


# 예매 서비스 제공 → wiring의 build_reservation_service로 교체됨
def provide_reservation_service() -> ReservationService:
    raise NotImplementedError("reservation_service 의존성이 주입되지 않았습니다.")


# 요청한 사람 (누구인지 + 관리자인지)
# - 티켓 PR #130의 CurrentActor와 같은 모양 (팀 전체가 같은 방식으로 맞추기 위함)
# - frozen=True : 만든 뒤 값 변경 불가 → 처리 도중 실수로 is_admin을 바꾸는 사고 방지
@dataclass(frozen=True)
class CurrentActor:
    user_id: int
    is_admin: bool


# 요청한 사람 제공 → wiring의 build_current_actor로 교체됨
# - 토큰 검증(auth) → 회원 조회(users) → 탈퇴 회원 차단 → is_admin 채우기
async def get_current_actor() -> CurrentActor:
    raise NotImplementedError("get_current_actor 의존성이 주입되지 않았습니다.")
