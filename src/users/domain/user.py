"""
# user.py
- 회원 도메인 엔티티
- 회원 한 명을 나타내는 클래스와 회원 규칙을 정의하는 파일
- FastAPI, SQLAlchemy를 import 하지 않는 순수 파이썬 코드
- DB 저장은 repository가, 요청 처리 순서는 application/service.py 가 담당

# 요구 사항 정의
[이메일]
1. 이메일은 유효한 형식이어야 한다.
2. 이메일은 앞뒤 공백을 제거하고 소문자로 정규화해 저장한다. (로그인 일관성)
3. 이메일은 로그인 아이디이므로 중복될 수 없다. (중복 확인은 application(service)에서 한다)

[이름·비밀번호]
4. 이름은 2자 이상 20자 이하여야 한다.
5. 이름은 앞뒤, 중간 공백을 제거하며 공백 기입이 불가능하다.
6. 비밀번호는 8자 이상이며 영문·숫자·특수문자(@$!%*#?&)를 각각 1개 이상 포함하고, 이 문자들로만 구성한다.
7. 비밀번호 원문은 저장하지 않고 bcrypt 해시만 저장한다. (해싱은 PasswordHasher에 맡긴다)

[전화번호]
8. 전화번호는 선택 입력이며, 하이픈·공백을 제거해 숫자만 저장한다. (예: 010-1234-5678 → 01012345678)
9. 전화번호는 중복될 수 없다. (중복 확인은 application(service)에서 한다)

[상태·역할]
10. 상태는 ACTIVE / WITHDRAWN 이며, 새 회원은 항상 ACTIVE다.
11. 역할은 USER / ADMIN 이며, 새 회원은 항상 USER다. email·role은 회원 정보 수정으로 바꿀 수 없다.
12. 탈퇴한(WITHDRAWN) 회원은 비밀번호를 변경할 수 없다.

[비밀번호 변경]
13. 기존 비밀번호가 일치해야 변경할 수 있다.
14. 새 비밀번호는 기존 비밀번호와 같을 수 없고, 6번 규칙을 만족해야 한다.

[탈퇴]
15. 탈퇴는 본인 또는 ADMIN만 할 수 있다.
16. 이미 탈퇴한 회원은 다시 탈퇴할 수 없으며, 재가입이 불가하다. (탈퇴 후에도 행이 남아 이메일 중복 확인(규칙 3)에 걸린다)
17. 탈퇴는 행을 지우지 않고 status=WITHDRAWN + deleted_at을 기록한다. (논리 삭제)

[정보 수정]
18. 회원 정보 수정은 이름과 전화번호만 가능하다. (email, role 수정 불가)
19. 값이 들어온 항목만 수정하고, 들어오지 않은(None) 항목은 그대로 둔다.
20. 수정하는 값도 생성 때와 같은 정규화, 검증을 거친다. (규칙 4, 5, 8)
21. 탈퇴한(WITHDRAWN) 회원은 정보 수정이 불가하다.

[상태 확인]
22. 로그인, 예매는 ACTIVE 회원만 가능하다.
23. ACTIVE가 아닌(WITHDRAWN) 회원이 이용하려 하면 도메인 오류가 발생한다.
24. 진행 중인 예매가 있을 경우 탈퇴가 불가하다. (예매 조회가 필요하므로 application(service)에서 확인한다)

[보류]
- 전화번호 삭제(값을 비우는 수정)
- 로그인 실패(401)는 auth 도메인에서 처리
"""

# 정규표현식 모듈: 이메일/비밀번호/전화번호 형식 검사에 사용
import re

# __init__, __repr__, __eq__를 자동으로 만들어 주는 데코레이터
from dataclasses import dataclass

# 탈퇴 시각 기록용 (UTC 기준)
from datetime import UTC, datetime

# enums.py
from users.domain.enums import UserRole, UserStatus

# exceptions.py
from users.domain.exceptions import (
    InactiveUser,
    InvalidEmail,
    InvalidName,
    InvalidPassword,
    InvalidPhone,
    InvalidUserStatus,
    WithdrawPermissionDenied,
)

# service.py
from users.domain.service import PasswordHasher

# [이름 길이 제한]
NAME_MIN_LENGTH = 2  # 이름 최소 길이 (규칙 4)
NAME_MAX_LENGTH = 20  # 이름 최대 길이 (규칙 4)

# [이메일 유효 형식 지정]
# ^[\w\.-]+   : 로컬 파트 (영문·숫자·_ . - 1자 이상)
# @           : 반드시 @ 하나
# [\w\.-]+    : 도메인 이름 (예: gmail)
# \.\w+$      : 마지막은 .com, .kr 같은 최상위 도메인
EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")

# [비밀번호 유효 형식 지정]
# (?=.*[A-Za-z])  : 영문이 최소 1개 있는지 미리 확인 (전방탐색, 문자를 소비하지 않음)
# (?=.*\d)        : 숫자 최소 1개
# (?=.*[@$!%*#?&]): 특수문자 최소 1개 (허용 특수문자는 이 7개뿐)
# [A-Za-z\d@$!%*#?&]{8,}$ : 전체가 허용 문자로만 8자 이상 → 한글·공백 등은 거부
PASSWORD_REGEX = re.compile(
    r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$"
)

# [전화번호 유효 형식 지정]
# 01[016789] : 010, 011, 016, 017, 018, 019로 시작
# \d{7,8}    : 뒤에 숫자 7~8자리 → 총 10~11자리
# 하이픈이 없는 상태를 전제 → 반드시 normalize_phone 이후에 검사
PHONE_REGEX = re.compile(r"^01[016789]\d{7,8}$")

# [이메일 소문자 정규화]
# 중복 가입 방지, 로그인 일관성
def normalize_email(email: str) -> str:
    # 앞뒤 공백 제거 + 소문자 (ex: ' A@B.com ' → 'a@b.com')
    return email.strip().lower()

# [이름 공백 정규화]
# 이름의 모든 공백 제거 (ex: ' 홍 길동 ' → '홍길동')
def normalize_name(name: str) -> str:
    return "".join(name.split())  # split(): 공백 기준으로 쪼갬 → join으로 붙임

# [전화번호 공백 정규화]
def normalize_phone(phone: str) -> str:
    # 하이픈, 공백 제거 -> 숫자만 남김 (ex: 010-1234-5678 -> 01012345678)
    # DB에 한 가지 형식으로만 저장 → 중복 검사(UNIQUE)가 정확해짐
    return phone.replace("-", "").replace(" ", "")


# User 도메인 엔티티
@dataclass
class User:
    # 필수 필드 (기본값 없음 -> 생성 시 반드시 전달)
    email: str
    name: str
    password_hash: str

    # 선택 필드 (기본값 있음)
    phone: str | None = None  # 선택 입력
    role: UserRole = UserRole.USER  # 가입 시 기본은 일반 회원
    status: UserStatus = UserStatus.ACTIVE  # 가입 직후 바로 활성 상태

    # DB가 채워주는 필드 (새 객체인 경우 None)
    # 저장 전에 None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    # [입력값 정규화 + 형식 검증]
    # 객체 생성 직후 자동 실행 (생성 시점에 불변식 보장)
    def __post_init__(self):
        # 이메일 정규화(공백 제거, 소문자)
        self.email = normalize_email(self.email)
        # 이메일 형식 검증(실패 시 422)
        self._validate_email(self.email)
        # 이름 정규화(앞뒤 공백 제거) → 공백만 입력하면 빈 문자열이 되어 길이 검증에서 거부
        self.name = normalize_name(self.name)
        # 이름 길이 (2~20자) 검증
        self._validate_name(self.name)
        # 전화번호 선택값 -> 있을 때만 정규화 후 검증
        if self.phone is not None:
            self.phone = normalize_phone(self.phone)
            self._validate_phone(self.phone)

    # [회원가입 비즈니스 로직]
    # classmethod : 인스턴스 없이 User.create(...) 호출, cls = User
    @classmethod
    def create(
        cls,
        email: str,
        name: str,
        raw_password: str,
        hasher: PasswordHasher,
        phone: str | None = None,
    ) -> "User":
        # [1] 평문 비밀번호 형식 검증 (해시 후에는 검증 불가하므로 반드시 먼저)
        cls._validate_password(raw_password)
        # [2] 객체 생성 (__post_init__에서 이메일·이름·전화번호 검증)
        return cls(
            email=email,
            name=name,
            password_hash=hasher.hash(raw_password),
            phone=phone,
        )

    # [비밀번호 변경 비즈니스 로직]
    def change_password(
        self, old_password: str, new_password: str, hasher: PasswordHasher
    ) -> None:
        # [1] 상태 검사: 탈퇴 회원은 계정 조작 불가 → 409 (규칙 12)
        if self.status == UserStatus.WITHDRAWN:
            raise InvalidUserStatus(
                f"이미 탈퇴한 회원입니다. [현재 상태 : {self.status}]"
            )
        # [2] 본인 확인: 입력한 기존 비밀번호를 저장된 해시와 비교 (규칙 13)
        if not hasher.verify(old_password, self.password_hash):
            raise InvalidPassword(
                "기존 비밀번호가 일치하지 않습니다.",
            )

        # [3] 재사용 방지: 평문끼리 비교 (같은 값이면 422) (규칙 14)
        if old_password == new_password:
            raise InvalidPassword(
                message="새 비밀번호는 이전 비밀번호와 동일할 수 없습니다."
            )
        # 새 비밀번호 형식(8자 이상, 영문+숫자+특수문자) 검증 (규칙 6)
        self._validate_password(new_password)
        # 검증 통과 시 새 비밀번호를 해시해서 저장
        # 객체 상태만 바뀜, DB 반영은 Repository/Service가 담당
        self.password_hash = hasher.hash(new_password)

    # [회원 탈퇴(소프트 삭제) 비즈니스 로직]
    # requester: 탈퇴를 '요청한 사람' (self = 탈퇴 '대상')
    # 소프트 삭제 : 실제 DELETE 대신 상태값만 바꿈 → 예매 내역 등 연관 데이터 보존
    def withdraw(self, requester: "User") -> None:
        # [1] 중복 탈퇴 방지 → 409 (규칙 16)
        if self.status == UserStatus.WITHDRAWN:
            raise InvalidUserStatus(
                f"이미 탈퇴 처리된 회원입니다. [현재 상태 : {self.status}]"
            )
        # [2] 본인 여부: 대상이 DB에 저장된 회원(id 존재)이면서 요청자 id와 같을 때 (규칙 15)
        is_owner = self.id is not None and self.id == requester.id
        # [3] 관리자 여부: 관리자는 다른 회원도 탈퇴 처리 가능
        is_admin = requester.role == UserRole.ADMIN
        # [4] 권한 검사: 본인, 관리자 둘 다 아니면 403
        if not (is_owner or is_admin):
            raise WithdrawPermissionDenied()
        # [5] 상태 전환: 이후 로그인·예매·비밀번호 변경이 차단되는 기준값
        # 행을 지우지 않고 상태, 시간만 기록 (규칙 17)
        self.status = UserStatus.WITHDRAWN
        # [6] 탈퇴 시각 기록: 서버 지역과 무관하게 UTC로 통일
        self.deleted_at = datetime.now(UTC)

    # [회원 정보 수정 비즈니스 로직]
    # email, role은 매개변수 자체가 없음 -> 수정 방법 없음 (규칙 18)
    # updated_at은 직접 넣지 않음 -> DB의 onupdate=func.now()가 저장 시 기록
    def update_profile(self, name: str | None = None, phone: str | None = None) -> None:
        # [1] 탈퇴 회원일 경우 : 수정 불가 -> 409 (규칙 21)
        if self.status == UserStatus.WITHDRAWN:
            raise InvalidUserStatus(
                f"탈퇴한 회원은 정보를 수정할 수 없습니다. [현재 상태: {self.status}]"
            )
        # [2] 이름 / 전화번호 : 값이 들어온 경우만 정규화 -> 검증 -> 반영 (규칙 19, 20)
        # 중복 확인(규칙 9)은 DB 조회가 필요해서 service에서 find_by_phone으로 처리
        # 검증을 통과한 뒤에 self에 넣어야 실패 시 기존 값 유지 가능
        if not None in (name, phone):
            new_name = normalize_name(name)  # 새 이름 공백 정규화 검사
            new_phone = normalize_phone(phone)  # 새 전화번호 공백 정규화 검사
            self._validate_name(new_name)  # 새 이름 형식 검증
            self._validate_phone(new_phone)  # 새 전화번호 형식 검증
            self.name = new_name  # 기존 이름을 새 이름으로 교체
            self.phone = new_phone  # 기존 전화번호를 새 전화번호로 교체

    # [회원 상태 확인]
    # @property : 메서드를 속성처럼 user.is_active로 사용 (괄호 없음)
    # True/False만 알려주는 "질문" -> 조건 분기가 필요한 곳에서 사용
    @property
    def is_active(self) -> bool:
        # ACTIVE만 True, WITHDRAWN은 False (규칙 22)
        return self.status == UserStatus.ACTIVE

    # [이메일 형식 검증]
    # @staticmethod: self/cls가 필요 없는 순수 검사 함수 → 클래스 안에 두어 응집도 유지
    @staticmethod
    # 이름 앞 '_' : 클래스 내부 전용(private 관례)
    def _validate_email(email: str) -> None:
        # match(): 문자열 처음부터 검사, 정규식 끝의 $와 함께 전체 일치를 강제
        if not EMAIL_REGEX.match(email):
            raise InvalidEmail(f"올바른 이메일 형식이 아닙니다. [입력 : {email}]")

    # [이름 형식 검증]
    @staticmethod
    def _validate_name(name: str) -> None:
        # len()은 글자 수 기준 (한글 '홍길동' = 3), normalize_name으로 공백을 모두 제거한 뒤 검사
        if not (NAME_MIN_LENGTH <= len(name) <= NAME_MAX_LENGTH):
            raise InvalidName(
                f"이름은 {NAME_MIN_LENGTH}자 이상 {NAME_MAX_LENGTH}자 이하여야 합니다. [입력 길이 : {len(name)}]"
            )

    # [비밀번호 형식 검증]
    @staticmethod
    def _validate_password(raw_password: str) -> None:
        # 평문 기준 검사 → create(가입)와 change_password(변경)에서 공통 사용
        # 영문·숫자·특수문자(@$!%*#?&) 각 1개 이상 + 8자 이상, 그 외 문자가 섞이면 거부
        # 보안상 비밀번호 원문은 메시지에 넣지 않음
        if not PASSWORD_REGEX.match(raw_password):
            raise InvalidPassword(
                "비밀번호는 8자 이상이며 영문, 숫자, 특수문자(@$!%*#?&)를 포함해야 합니다."
            )

    # [전화번호 형식 검증]
    @staticmethod
    def _validate_phone(phone: str) -> None:
        # normalize_phone으로 하이픈을 제거한 값을 받는다는 전제
        # 010/011/016~019로 시작하는 10~11자리 숫자만 통과 (+82 같은 국제 형식은 거부)
        if not PHONE_REGEX.match(phone):
            raise InvalidPhone(f"올바른 전화번호 형식이 아닙니다. [입력 : {phone}]")

    # [회원 상태 검사]
    # ACTIVE가 아니면 예외를 던지는 "검사" -> 로그인 검증, 예매 시작 전에 한 줄로 사용
    # ex) user.ensure_active() -> 통과하면 아무 일도 없음
    def ensure_active(self) -> None:
        if not self.is_active:
            raise InactiveUser(
                f"ACTIVE 상태의 회원만 이용할 수 있습니다. [현재 상태 : {self.status}]"
            )
