# 파일 역할: 인증 업무의 실행 순서를 담당한다. 회원 확인 → 토큰 발급, 로그아웃 차단, 요청 인증을 조합한다.

from auth.domain.entities import TokenPayload
from auth.domain.repository import TokenBlacklistRepository
from auth.domain.service import TokenProvider, UserCredentialVerifier, UserStatusChecker
from shared.core.exceptions import UnauthorizedException


# 로그인·로그아웃·요청 인증을 한곳에서 조율하며 구체적인 보안 기술은 주입된 객체에 맡긴다.
class AuthService:
    # 회원 자격 검사, 차단 토큰 저장소, 토큰 처리기, 현재 회원 상태 검사기를 받아 보관한다.
    def __init__(
        self,
        credential_verifier: UserCredentialVerifier,
        token_blacklist_repo: TokenBlacklistRepository,
        token_provider: TokenProvider,
        user_status_checker: UserStatusChecker,
    ):
        self._credential_verifier = credential_verifier
        self._blacklist_repo = token_blacklist_repo
        self._token_provider = token_provider
        self._user_status_checker = user_status_checker

    # 자격 검증 성공 시 토큰·인증 방식·남은 유효 기간을 반환한다. 비밀번호 자체는 반환하지 않는다.
    async def login(self, email: str, plain_password: str) -> tuple[str, str, int]:
        user_id = await self._credential_verifier.verify_credentials(
            email, plain_password
        )
        if user_id is None:
            raise UnauthorizedException("이메일 또는 비밀번호가 올바르지 않습니다.")

        token, _, expires_in = self._token_provider.create_access_token(user_id)
        return token, "bearer", expires_in

    # 검증된 토큰의 jti를 차단 목록에 추가한다. 이미 차단된 토큰의 반복 요청도 허용한다.
    async def logout(self, token: str) -> None:
        payload = self._token_provider.decode_token(token)
        if not await self._blacklist_repo.is_blacklisted(payload.jti):
            await self._blacklist_repo.add(jti=payload.jti, user_id=payload.user_id)

    # 서명·만료 확인 → 로그아웃 여부 → 현재 회원 상태를 차례로 검사한 뒤 사용자 정보를 돌려준다.
    async def authenticate_token(self, token: str) -> TokenPayload:
        payload = self._token_provider.decode_token(token)
        if await self._blacklist_repo.is_blacklisted(payload.jti):
            raise UnauthorizedException("로그아웃된 토큰입니다.")
        await self._user_status_checker.ensure_active(payload.user_id)
        return payload
