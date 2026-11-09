# 파일 역할: 토큰 발급 이후의 탈퇴·비활성화도 차단하도록, 요청 시점의 회원 상태를 DB에서 다시 확인한다.

from auth.domain.service import UserStatusChecker
from shared.core.exceptions import UnauthorizedException
from users.domain.exceptions import InactiveUser
from users.domain.repository import UserRepository


# 토큰에 든 회원 ID를 최신 DB 회원과 대조한다. 토큰이 아직 유효해도 탈퇴 회원은 거절한다.
class RepositoryUserStatusChecker(UserStatusChecker):
    # 외부에서 전달받은 의존성을 보관한다. 여기서 DB 연결이나 업무 처리를 새로 시작하지 않는다.
    def __init__(self, user_repo: UserRepository):
        self._user_repo = user_repo

    # 유효한 회원 ID인지 확인한 뒤 회원 존재 여부·도메인 활성 상태·탈퇴 시각을 검사한다.
    async def ensure_active(self, user_id: int) -> None:
        if type(user_id) is not int or not 1 <= user_id <= 2**63 - 1:
            raise UnauthorizedException("유효한 회원을 확인할 수 없습니다.")
        user = await self._user_repo.find_by_id(user_id)
        if user is None or user.id != user_id:
            raise UnauthorizedException("유효한 회원을 확인할 수 없습니다.")
        user.ensure_active()
        if user.deleted_at is not None:
            raise InactiveUser
