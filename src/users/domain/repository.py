"""
# repository.py
- 반드시 가져야 할 메서드 목록을 정의하는 추상 클래스
- 메서드 이름, 인자 타입, 반환 타입만 존재하며 구현은 없음
- service.py는 이 클래스 타입만 보고 코드 작성
- 실제 DB 코드는 infrastructure/repositories.py의 SqlAlchemyUserRepository가 구현 -> domain은 SQLAlchemy를 몰라도 됨(의존성 역전)

# abc
- Abstract Base Classes (추상 기본 클래스)
- 추상 클래스
    - 직접 객체를 만드는 것이 아닌, 상속 받아서 쓰라고 만든 클래스
    - 자식 클래스가 모든 @abstractmethod를 구현해야 객체를 만들 수 있음
    - UserRepository()로 직접 만들면 TypeError 발생
"""

from abc import ABC, abstractmethod

# user.py
from users.domain.user import User


class UserRepository(ABC):
    @abstractmethod
    async def find_by_id(self, user_id: int) -> User | None:
        """회원 ID 기준으로 사용자 단건 조회"""
        # 없으면 None
        # 내 정보 조회, get_current_user(토큰의 user_id로 회원 조회)에서 사용

    @abstractmethod
    async def find_by_email(self, email: str) -> User | None:
        """이메일 기준으로 사용자 단건 조회"""
        # 없으면 None
        # 로그인, 가입 시 이메일 중복 확인에서 사용 (규칙 3)
        # normalize_email()로 정규화한 값으로 조회해야 함

    @abstractmethod
    async def find_by_phone(self, phone: str) -> User | None:
        """전화번호 기준으로 단건 조회"""
        # 없으면 None
        # 가입 시 전화번호 중복 확인에서 사용 (규칙 9)
        # normalize_phone()으로 정규화한 값으로 조회해야 함

    @abstractmethod
    async def save(self, user: User) -> User:
        """회원 신규 생성(INSERT) 또는 변경 사항 갱신(UPDATE)"""
        # id가 없으면 INSERT(신규 가입), 있으면 UPDATE(비밀번호 변경, 탈퇴)
        # DB가 채운 id, created_at 등이 담긴 엔티티 반환
        # commit은 하지 않음 (flush만, commit은 요청 단위로 service 담당)
