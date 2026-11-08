"""
# presentation/dependencies.py
라우터가 Depends()로 받아 쓰는 의존성 함수를 모아 둔 파일

# 왜 NotImplementedError를 던지나
- 지금은 "자리표시자"다. 라우터는 이 함수 이름만 알고, 실제 구현은 나중에 끼워 넣는다
  ① provide_reservation_service : wiring(wiring/reservation.py)에서 실제 저장소를 연결한 서비스로 교체
  ② get_current_user_id         : auth 담당이 만드는 로그인 의존성으로 교체
- 교체는 app.dependency_overrides[원래 함수] = 실제 함수 방식으로 한다
  → 라우터 코드는 고치지 않아도 됨
- 교체 전에 API를 호출하면 이 예외가 나서 500이 응답됨 (라우터 버그가 아님)
"""

# 프로젝트 코드 : 반환 타입 표시용
from reservations.application.service import ReservationService


# 예매 서비스 제공
# - 라우터에서 service: ReservationService = Depends(provide_reservation_service)로 받음
# - 서비스에는 예매·축제·공연 저장소 3개가 필요하므로, 조립은 wiring이 담당
def provide_reservation_service() -> ReservationService:
    raise NotImplementedError("reservation_service 의존성이 주입되지 않았습니다.")


# 로그인한 사용자 id 제공
# - 라우터에서 user_id: int = Depends(get_current_user_id)로 받음
# - user_id를 요청 body로 받지 않는 이유
#   → 클라이언트가 다른 사람 id를 넣어 대신 예매·조회·취소할 수 있으므로, 토큰에서 꺼낸 값만 믿는다
async def get_current_user_id() -> int:
    raise NotImplementedError("get_current_user_id 의존성이 주입되지 않았습니다.")
