# 파일 역할: users 저장소로 회원을 읽고 비밀번호·활성 상태를 확인해 로그인 가능한 회원 ID를 반환한다.

from starlette.concurrency import run_in_threadpool

from auth.domain.service import UserCredentialVerifier
from users.domain.exceptions import InactiveUser
from users.domain.repository import UserRepository
from users.domain.service import PasswordHasher
from users.domain.user import normalize_email


# 회원 데이터는 users의 공개 저장소 계약으로 읽고, 비밀번호 비교는 주입된 해시 구현체에 맡긴다.
class RepositoryUserCredentialVerifier(UserCredentialVerifier):
    """users의 공개 인터페이스로 회원을 조회하고 로그인 자격을 검증한다."""

    # 외부에서 전달받은 의존성을 보관한다. 여기서 DB 연결이나 업무 처리를 새로 시작하지 않는다.
    def __init__(self, user_repo: UserRepository, password_hasher: PasswordHasher):
        self._user_repo = user_repo
        self._password_hasher = password_hasher

    # 이메일 정규화 → 회원 조회 → 해시 비교 → 활성 상태 확인 후 저장된 회원 ID를 반환한다.
    async def verify_credentials(self, email: str, plain_password: str) -> int | None:
        # 조회 기준은 users의 이메일 규칙과 맞춘다. 비밀번호에는 이 정규화를 적용하지 않는다.
        user = await self._user_repo.find_by_email(normalize_email(email))
        if user is None:
            return None

        # bcrypt 등 동기 해시 검증이 비동기 요청의 이벤트 루프를 막지 않게 한다.
        # 비밀번호 원문에는 strip/소문자 변환 등 정규화를 적용하지 않는다.
        matched = await run_in_threadpool(
            self._password_hasher.verify, plain_password, user.password_hash
        )
        if not matched:
            return None

        # 비밀번호가 틀린 요청에 회원 상태를 노출하지 않는다.
        user.ensure_active()
        if user.deleted_at is not None:
            raise InactiveUser
        if type(user.id) is not int or not 1 <= user.id <= 2**63 - 1:
            return None
        return user.id
