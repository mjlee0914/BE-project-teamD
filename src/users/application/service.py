"""
# service.py
- 회원 응용 서비스 (유스케이스)
- 요청 하나를 처리하는 순서를 정하는 파일: 조회 → 도메인 규칙 실행 → 저장
- 회원 규칙 자체는 domain/user.py(User)가 가지고, service는 순서와 DB가 필요한 검사(중복 확인)만 담당

# 의존성
- UserRepository, PasswordHasher 인터페이스(domain)만 알고 있음
- 실제 구현체(SqlAlchemyUserRepository, BcryptPasswordHasher)는 wiring(src/wiring/user.py)에서 주입
- 그래서 service는 SQLAlchemy·bcrypt를 import하지 않음 (의존성 역전)

# commit
- service도 commit하지 않음 → repository.save()는 flush까지만, commit/rollback은 get_db가 요청 단위로 처리
- 중간에 예외가 나면 get_db가 rollback → 도메인 객체가 바뀌었더라도 DB에는 반영되지 않음
"""

# users/domain/exceptions.py
from shared.core.time import now_utc
from users.domain.exceptions import (
    ActiveReservationExists,
    DuplicateEmail,
    DuplicatePhone,
    UserNotFound,
)

# users/domain/repository.py
from users.domain.repository import UserRepository

# users/domain/service.py
from users.domain.service import ActiveReservationChecker, PasswordHasher

# users/domain/user.py
from users.domain.user import User


# 회원 유스케이스(가입, 내 정보 조회·수정, 비밀번호 변경, 탈퇴)를 처리하는 클래스
# router는 이 클래스만 호출하고, 실제 객체는 wiring(src/wiring/user.py)에서 저장소·해셔를 넣어 만든다
class UserService:
    # 저장소와 해셔를 밖에서 받음 (타입은 domain 인터페이스)
    def __init__(
        self,
        user_repo: UserRepository,
        hasher: PasswordHasher,
        reservation_checker: ActiveReservationChecker,
    ) -> None:
        self._user_repo = user_repo
        self._hasher = hasher
        self._reservation_checker = reservation_checker

    # [회원가입]
    async def signup(
        self,
        email: str,
        name: str,
        raw_password: str,
        phone: str | None = None,
    ) -> User:
        # [1] 엔티티 생성: 형식 검증(422) + 이메일·이름·전화번호 정규화 + 비밀번호 해시
        # 정규화된 값으로 중복 확인해야 하므로 생성을 먼저 함 (' A@B.com '과 'a@b.com'은 같은 이메일)
        user = User.create(
            email=email,
            name=name,
            raw_password=raw_password,
            hasher=self._hasher,
            phone=phone,
        )
        # [2] 이메일 중복 확인 → 409 (규칙 3)
        if await self._user_repo.find_by_email(user.email) is not None:
            raise DuplicateEmail()
        # [3] 전화번호 중복 확인 (선택 입력이라 있을 때만) → 409 (규칙 9)
        if (
            user.phone is not None
            and await self._user_repo.find_by_phone(user.phone) is not None
        ):
            raise DuplicatePhone()
        # [4] 저장: DB가 채운 id, created_at이 담긴 엔티티 반환
        # 동시 가입으로 [2], [3]을 통과해도 unique 제약에 걸리면 repository가 409로 바꿔서 던짐
        return await self._user_repo.save(user)

    # [내 정보 조회]
    async def get_me(self, user_id: int) -> User:
        # [1] 회원 조회: 없으면 404
        user = await self._get_user(user_id)
        # [2] 상태 검사: ACTIVE가 아니면(탈퇴 회원) 403 (규칙 23)
        user.ensure_active()
        return user

    # [회원 정보 수정]
    async def update_profile(
        self, user_id: int, name: str | None = None, phone: str | None = None
    ) -> User:
        # [1] 회원 조회: 없으면 404
        user = await self._get_user(user_id)
        # [2] 도메인 규칙 실행: 탈퇴 회원 403, 형식 검증 422, 둘 다 들어온 경우만 반영 (규칙 18~21)
        user.update_profile(name=name, phone=phone)
        # [3] 전화번호 중복 확인 → 409 (규칙 9)
        # 정규화된 값(user.phone)으로 조회, 자기 자신의 번호 그대로면 중복이 아님
        if user.phone is not None:
            owner = await self._user_repo.find_by_phone(user.phone)
            if owner is not None and owner.id != user.id:
                raise DuplicatePhone()
        # [4] 저장 (updated_at은 DB가 기록)
        return await self._user_repo.save(user)

    # [비밀번호 변경]
    async def change_password(
        self, user_id: int, old_password: str, new_password: str
    ) -> None:
        # [1] 회원 조회: 없으면 404
        user = await self._get_user(user_id)
        # [2] 도메인 규칙 실행: 탈퇴 회원 403, 기존 비밀번호 불일치·재사용·형식 위반 422 (규칙 12~14)
        user.change_password(
            old_password=old_password,
            new_password=new_password,
            hasher=self._hasher,
        )
        # [3] 저장: 새 해시만 바뀜
        await self._user_repo.save(user)

    # [관리자 검증]
    # 다른 도메인(축제, 공연 등)의 관리자 전용 API에서 사용
    # 토큰(TokenPayload)에는 user_id만 있어서 role은 DB에서 회원을 조회해 확인
    async def verify_admin(self, user_id: int) -> User:
        # [1] 회원 조회: 없으면 404
        user = await self._get_user(user_id)
        # [2] 도메인 규칙 실행: 탈퇴, ADMIN 아님은 403 (규칙 25, 26)
        user.ensure_admin()
        # [3] 검증된 관리자 반환 (호출한 쪽에서 id 등을 바로 사용 가능)
        return user

    # [회원 탈퇴]
    # target_user_id: 탈퇴 '대상', requester_id: 탈퇴를 '요청한 사람' (토큰의 user_id)
    async def withdraw(self, target_user_id: int, requester_id: int) -> None:
        # [1] 대상, 요청자 조회: 없으면 404
        target = await self._get_user(target_user_id)
        requester = await self._get_user(requester_id)
        # [2] 도메인 규칙 실행: 이미 탈퇴 409, 본인·ADMIN이 아니면 403 (규칙 15, 16)
        target.withdraw(requester=requester, now=now_utc())
        # [3] 진행 중 예매 확인: 있으면 409 (규칙 24)
        # 위에서 바뀐 상태는 아직 저장 전 -> 예외가 나면 save 없이 끝나고 get_db가 rollback
        if await self._reservation_checker.has_active_reservation(target.id):
            raise ActiveReservationExists()
        # [4] 저장: 행은 남기고 status=WITHDRAWN, deleted_at만 기록 (규칙 17)
        await self._user_repo.save(target)

    # [회원 조회 공통 처리]
    # 이름 앞 '_' : 클래스 내부 전용, 없으면 404로 통일
    async def _get_user(self, user_id: int) -> User:
        user = await self._user_repo.find_by_id(user_id)
        if user is None:
            raise UserNotFound()
        return user
