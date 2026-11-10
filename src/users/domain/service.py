"""
# service.py
- 도메인 서비스 인터페이스
- 엔티티 하나에 속하지 않는 기능의 "약속"만 정의하는 파일
- 메서드 이름, 인자 타입, 반환 타입만 존재하며 구현은 없음

# PasswordHasher
- 비밀번호를 해시로 바꾸고(hash), 입력값이 해시와 맞는지 확인(verify)하는 기능
- User 엔티티는 이 인터페이스만 보고 비밀번호를 처리 (User.create, change_password)
- 실제 구현(bcrypt)은 auth/infrastructure/password_hasher.py의 BcryptPasswordHasher가 담당
- domain은 bcrypt 라이브러리를 몰라도 됨 (의존성 역전)
- 나중에 해싱 방식을 바꿔도 domain 코드는 수정하지 않아도 됨

# 해시 (hash)
- 단방향 암호화
- 평문 -> 해시는 가능하지만, 해시 -> 평문으로 되돌리기 불가능
- 로그인할 때는 "복호화"가 아닌 입력값을 다시 해시해서 비교(verify)함
- DB가 유출되어도 원래 비밀번호를 알 수 없음 (규칙 7)

# ActiveReservationChecker
- 회원에게 진행 중(PENDING, CONFIRMED) 예매가 있는 지 확인하는 기능 (규칙 24)
- 예매 데이터는 reservations 도메인 소유 -> users는 이 인터페이스만 알고 있음
- 실제 구현은 users/infrastructure/reservation_checker.py 담당
"""

from abc import ABC, abstractmethod


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, raw_password: str) -> str:
        """평문 비밀번호를 단방향 암호화하여 해시값으로 반환"""
        # 같은 비밀번호도 매번 다른 해시가 나옴 (bcrypt가 salt를 섞기 때문)

    @abstractmethod
    def verify(self, raw_password: str, hashed_password: str) -> bool:
        """평문 비밀번호가 기존 해시값과 일치하는 검증"""
        # 일치하면 True, 아니면 False

class ActiveReservationChecker(ABC):
    @abstractmethod
    async def has_active_reservation(self, user_id: int) -> bool:
        """진행 중 예매가 하나라도 있으면 True"""
