"""
# reservation_checker.py
- ActiveReservationChecker 구현체 (규칙 24)
- 예매 저장소의 exists_active_by_user로 진행 중(PENDING, 축제가 끝나지 않은 CONFIRMED) 예매 여부를 확인
- 같은 세션을 써서 탈퇴 요청과 한 트랜잭션으로 처리

# RepositoryActiveReservationChecker
- 진행 중인 예매 확인 구현체
- domain의 ActiveReservationChecker(추상)를 상속 -> UserService는 추상 타입만 알고 이 클래스는 모름
- 실제 객체는 wiring(src/wiring/user.py)에서 저장소를 넣어 만들어 UserService에 주입
- users 도메인이 reservations 도메인을 직접 import 하지 않도록 중간에서 연결하는 어댑터 역할
"""

# reservations/infrastructure/repositories.py
from reservations.infrastructure.repositories import SqlalchemyReservationRepository

# users/domain/service.py
from users.domain.service import ActiveReservationChecker


# [진행 중 예매 확인 구현체]
class RepositoryActiveReservationChecker(ActiveReservationChecker):
    # 예매 저장소를 밖에서 받음 (wiring이 같은 세션으로 만든 저장소를 넣어 줌 -> 같은 트랜잭션)
    # 이름 앞 '_': 클래스 내부 전용
    def __init__(self, reservation_repo: SqlalchemyReservationRepository) -> None:
        self._reservation_repo = reservation_repo

    # [진행 중 예매 여부 확인]
    # user_id 회원에게 PENDING 예매 또는 축제가 끝나지 않은 CONFIRMED 예매가 하나라도 있으면 True
    # -> UserService.withdraw가 True를 받으면 탈퇴 거절 (규칙 24)
    # 판단 로직(어떤 상태가 '진행 중'인지)은 예매 저장소에 맡기고, 여기서는 전달만 함.
    async def has_active_reservation(self, user_id: int) -> bool:
        return await self._reservation_repo.exists_active_by_user(user_id)
