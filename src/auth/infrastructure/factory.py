# 파일 역할: 요청의 DB 세션과 보안 구현체를 묶어 AuthService를 생성한다. 라우터 등록은 수행하지 않는다.

from sqlalchemy.ext.asyncio import AsyncSession

from auth.application.service import AuthService
from auth.domain.service import TokenProvider
from auth.infrastructure.credentials_verifier import RepositoryUserCredentialVerifier
from auth.infrastructure.repositories import SqlAlchemyTokenBlacklistRepository
from auth.infrastructure.user_status_checker import RepositoryUserStatusChecker
from users.domain.service import PasswordHasher
from users.infrastructure.repositories import SqlAlchemyUserRepository


# 같은 세션의 회원·블랙리스트 저장소를 만들고, 주입된 해시·토큰 구현체와 조립해 서비스를 반환한다.
def create_auth_service(
    session: AsyncSession,
    token_provider: TokenProvider,
    *,
    password_hasher: PasswordHasher,
) -> AuthService:
    """같은 요청 세션으로 구현체를 조립한다. 해시 구현체를 명시적으로 주입해야 한다."""
    users = SqlAlchemyUserRepository(session)
    return AuthService(
        credential_verifier=RepositoryUserCredentialVerifier(users, password_hasher),
        token_blacklist_repo=SqlAlchemyTokenBlacklistRepository(session),
        token_provider=token_provider,
        user_status_checker=RepositoryUserStatusChecker(users),
    )
