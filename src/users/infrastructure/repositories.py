"""
# repositories.py
- 회원 Repository 구현체
- domain/repository.py의 UserRepository를 SQLAlchemy(AsyncSession)로 구현
- domain은 SQLAlchemy를 모름 → DB 코드는 이 파일에만 둔다 (의존성 역전)

# 변환 함수
- _to_domain : DB 모델(UserModel) → 엔티티(User), 조회 결과를 돌려줄 때 사용
- _to_model  : 엔티티(User) → DB 모델(UserModel), 신규 가입(INSERT)에서만 사용

# commit
- save는 flush + refresh까지만 한다
- commit/rollback은 요청 단위로 get_db(shared/core/database.py)가 담당

# IntegrityError
- DB 제약조건(UNIQUE, NOT NULL, CHECK 등)을 어겼을 때 SQLAlchemy가 던지는 예외
- service에서 중복 확인을 해도 동시에 같은 이메일로 가입하면 flush 시점에 발생할 수 있음
- 그대로 두면 500 → 어떤 컬럼인지 보고 회원 도메인 예외(DuplicateEmail, DuplicatePhone, 409)로 바꿔서 던짐
- e.orig : DB 드라이버가 보낸 원래 오류 (메시지에 제약조건·컬럼 이름이 들어 있음)

# AsyncSession
- SQLAlchemy의 비동기 DB 세션 (DB와 대화하는 창구)
- 요청마다 get_db가 하나 만들어 주입 → 같은 요청 안의 조회·저장은 같은 세션(같은 트랜잭션)에서 처리
- 비동기라서 DB를 기다리는 메서드(execute, get, flush, refresh)는 await 필요
- add()는 세션에 객체를 등록만 하고 DB에 보내지 않으므로 await 없음
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# users/domain/exceptions.py
from users.domain.exceptions import DuplicateEmail, DuplicatePhone, UserNotFound

# users/domain/repository.py
from users.domain.repository import UserRepository

# users/domain/user.py
from users.domain.user import User, normalize_email, normalize_phone

# users/infrastructure/models.py
from users.infrastructure.models import UserModel


# DB에서 꺼낼 때 사용: 모델의 모든 필드를 엔티티로 옮긴다
# DB가 채운 id, created_at, updated_at, deleted_at까지 포함
def _to_domain(model: UserModel) -> User:
    return User(
        id=model.id,
        email=model.email,
        name=model.name,
        password_hash=model.password_hash,
        phone=model.phone,
        role=model.role,
        status=model.status,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


# DB에 넣을 때 사용: 신규 회원(id=None)을 모델로 만든다
# id, created_at, updated_at은 DB가 채우므로 넣지 않는다
def _to_model(user: User) -> UserModel:
    return UserModel(
        email=user.email,
        name=user.name,
        password_hash=user.password_hash,
        phone=user.phone,
        role=user.role,
        status=user.status,
        deleted_at=user.deleted_at,
    )


# UserRepository(domain의 추상 클래스)를 SQLAlchemy로 구현한 클래스
# service는 UserRepository 타입만 알고, 실제 객체는 wiring(src/wiring/user.py)에서 이 클래스로 주입
class SqlAlchemyUserRepository(UserRepository):
    # 요청마다 get_db가 만든 세션을 주입받아 모든 메서드가 같은 세션을 사용
    def __init__(self, session: AsyncSession):
        self._session = session

    # [회원 ID로 단건 조회]
    # 내 정보 조회, 토큰의 user_id로 회원 조회에서 사용
    async def find_by_id(self, user_id: int) -> User | None:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else _to_domain(model)

    # [이메일로 단건 조회]
    # 로그인, 가입 시 이메일 중복 확인에서 사용 (규칙 3)
    # DB에는 정규화된 이메일이 저장되므로 조회 값도 정규화 (이미 정규화된 값이어도 결과는 같음)
    async def find_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == normalize_email(email))
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else _to_domain(model)

    # [전화번호로 단건 조회]
    # 가입, 정보 수정 시 전화번호 중복 확인에서 사용 (규칙 9)
    # 하이픈·공백이 섞여 들어와도 숫자만 남겨서 조회
    async def find_by_phone(self, phone: str) -> User | None:
        stmt = select(UserModel).where(UserModel.phone == normalize_phone(phone))
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else _to_domain(model)

    # [회원 신규 생성(INSERT) 또는 변경 사항 갱신(UPDATE)]
    async def save(self, user: User) -> User:
        # [1] id가 없으면 신규 가입 → INSERT
        if user.id is None:
            model = _to_model(user)
            self._session.add(model)
        # [2] id가 있으면 기존 회원 → UPDATE (정보 수정, 비밀번호 변경, 탈퇴)
        else:
            model = await self._session.get(UserModel, user.id)
            # 조회 없이 save를 부른 경우를 위한 방어 코드 → 404
            if model is None:
                raise UserNotFound()
            # email, role은 바꿀 수 없으므로 반영하지 않음 (규칙 11, 18)
            model.name = user.name
            model.phone = user.phone
            model.password_hash = user.password_hash
            model.status = user.status
            model.deleted_at = user.deleted_at

        # [3] flush: SQL을 DB에 보내 id 발급, 제약조건 검사까지 진행 (commit은 get_db)
        # service에서 중복 확인을 해도 동시 가입이면 unique 제약에 걸릴 수 있음
        # IntegrityError(SQLAlchemy 예외)를 그대로 두면 500 → 회원 예외(409)로 바꿔서 던짐
        try:
            await self._session.flush()
        except IntegrityError as e:
            message = str(e.orig).lower()
            if "email" in message:
                raise DuplicateEmail() from e
            if "phone" in message:
                raise DuplicatePhone() from e
            raise

        # [4] refresh: DB가 채운 값(id, created_at, updated_at)을 모델에 다시 읽어옴
        await self._session.refresh(model)
        return _to_domain(model)
