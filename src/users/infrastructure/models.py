from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.models import Base

# from user.domain.user import User
from users.domain.enums import UserRole, UserStatus


# 회원 모델 (users 테이블)
class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # 로그인 ID. 중복 가입 불가, 이메일로 조회가 잦아 인덱스 추가
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(50), nullable=False)

    # 원문 비밀번호는 저장하지 않고 bcrypt 해시만 저장
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    # 선택 입력
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)

    # native_enum=False + create_constraint=True → DB에 CHECK 제약으로 허용 값 제한
    # 기본값은 SQLEnum이 아닌 mapped_column에 지정해야 적용됨
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole, name="user_role", native_enum=False, create_constraint=True),
        default=UserRole.USER,
        nullable=False,
    )

    status: Mapped[UserStatus] = mapped_column(
        SQLEnum(
            UserStatus, name="user_status", native_enum=False, create_constraint=True
        ),
        default=UserStatus.ACTIVE,
        nullable=False,
    )

    # 생성 시각은 DB가 기록
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # 수정할 때마다 현재 시각으로 갱신
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 논리 삭제: 행을 지우지 않고 탈퇴 시각만 기록 (NULL이면 정상 회원)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
