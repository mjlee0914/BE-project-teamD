# 인증 모듈

## JWT 구현

`infrastructure/security.py`의 JwtTokenProvider가 TokenProvider를 구현한다.

- 서명 알고리즘은 서버에서 HS512로 고정한다.
- sub에는 양의 BIGINT 회원 ID를 문자열로 넣고 검증 후 int로 반환한다.
- jti는 발급할 때마다 새 UUID 문자열을 생성한다.
- exp/iat, 발급자 iss, 대상 aud, 액세스 토큰 용도를 검증한다.
- 누락·만료·위조 토큰은 세부 원문 없이 UnauthorizedException(401)으로 전달한다.
- TokenPayload에는 기존대로 user_id와 jti만 둔다. DB/엔티티에 exp를 추가하지 않는다.

로컬 .env에 다음을 설정한다. 키는 예시 값을 사용하지 말고 무작위로 생성한다.

```dotenv
JWT_SECRET_KEY=<최소 64바이트의 무작위 비밀값>
JWT_ACCESS_TOKEN_EXPIRE_SECONDS=3600
JWT_ISSUER=be-project-teamd
JWT_AUDIENCE=be-project-teamd-api
```

키 생성 명령(출력은 로컬 .env에만 보관):

```powershell
uv run python -c "import secrets; print(secrets.token_hex(64))"
```

```python
from auth.infrastructure.security import JwtTokenProvider

provider = JwtTokenProvider.from_env()
token, jti, expires_in = provider.create_access_token(user_id=1)
payload = provider.decode_token(token)
```

PyJWT는 서명과 시간 검증만 수행한다. 블랙리스트와 회원 상태 확인은 응용 서비스 및
회원 조회 구현체에서 수행해야 한다. 키와 발급자·대상 설정은 모든 서버 인스턴스에서 일치해야 한다.
기본/개발용 비밀키로 자동 대체하지 않으며 키가 없거나 짧으면 설정 오류로 중단한다.

## 블랙리스트 저장소

`infrastructure/models.py`와 `infrastructure/repositories.py`를 구현했다.

- auth 테이블은 ERD 그대로 jti TEXT 기본 키, user_id BIGINT → users.id 외래 키만 사용한다.
- user_id에 UNIQUE를 추가하지 않아 한 회원의 여러 토큰을 차단할 수 있다.
- PostgreSQL의 ON CONFLICT DO NOTHING으로 동일 토큰의 반복·경합 등록을 처리한다.
- 기존 jti를 다른 회원으로 덮어쓰지 않으며 소유자 충돌은 409로 전달한다.
- 저장소는 commit하지 않는다. 로그아웃 응답 전 요청 트랜잭션이 commit돼야 차단이 유지된다.
- exp/expired_at 컬럼이나 자동 삭제 기능은 추가하지 않았다. 정리 정책이 없으므로 기록이 누적된다.

```python
from auth.infrastructure.repositories import SqlAlchemyTokenBlacklistRepository

repository = SqlAlchemyTokenBlacklistRepository(session)
```

auth ORM은 공통 init_models에 등록했다. 모델 등록은 테이블 생성과 다르며, 실제 DB 적용은 별도 작업이다.
원본 앱의 라우터·wiring 연결은 아직 반영하지 않았다.
현재 개발 DB에 테이블을 영구 생성하지 않았다.

검증 명령:

```powershell
$env:PYTHONPATH = 'src'
$env:RUN_AUTH_POSTGRES_TESTS = '1'
uv run python -m unittest discover -s tests -p 'test_auth*.py' -v
Remove-Item Env:RUN_AUTH_POSTGRES_TESTS
```

AUTH_TEST_DATABASE_URL이 있으면 그 DB를, 없으면 로컬 .env의 DATABASE_URL을 사용한다.
실제 PostgreSQL 검증은 격리된 스키마·트랜잭션에서 실행하며 마지막에 전체 rollback과 잔존 여부를 검사한다.
public의 기존 테이블과 데이터는 수정하지 않는다.

## 회원 자격 검증

`infrastructure/credentials_verifier.py`의 RepositoryUserCredentialVerifier를 구현했다.

- users의 UserRepository.find_by_email과 PasswordHasher.verify 인터페이스를 주입받는다.
- 이메일의 앞뒤 공백과 대소문자를 users 규칙에 맞춰 정규화하며 비밀번호 원문은 변형하지 않는다.
- 회원이 없거나 비밀번호가 일치하지 않으면 None을 반환하고 AuthService가 401로 처리한다.
- 비밀번호가 일치한 뒤 ACTIVE 여부와 deleted_at을 검사한다. 탈퇴 회원의 로그인은 403으로 거절한다.
- 실제 해시 비교는 스레드 풀에서 실행해 이벤트 루프를 막지 않는다.
- 조회·해시 구현의 예상하지 못한 오류를 로그인 실패로 숨기지 않는다.
- 이 구현체는 회원 정보를 저장하거나 비밀번호를 다시 해싱하지 않는다.

```python
from auth.infrastructure.credentials_verifier import RepositoryUserCredentialVerifier

verifier = RepositoryUserCredentialVerifier(user_repo, password_hasher)
```

auth의 BcryptPasswordHasher를 users의 기존 PasswordHasher 인터페이스로 주입할 수 있다.
users 엔티티 생성·비밀번호 변경에 같은 구현체를 전달했을 때 로그인과 호환되는 것을 검증했다.
users 파일이나 실제 회원가입 API에는 적용하지 않았다. 실제 앱 연결 시 동일한 해시 구현체를 주입해야 한다.

## 토큰 인증 시 현재 회원 상태 확인

`RepositoryUserStatusChecker`는 기존 users의 UserRepository.find_by_id와 User.ensure_active를 사용한다.
users 폴더의 구조·코드를 변경하지 않는다.

AuthService 생성 시 네 번째 인자인 user_status_checker가 필수다.
검사를 생략하는 기본값이나 임시로 모든 회원을 허용하는 구현은 제공하지 않는다.

```python
from auth.application.service import AuthService
from auth.infrastructure.user_status_checker import RepositoryUserStatusChecker

service = AuthService(
    credential_verifier=verifier,
    token_blacklist_repo=blacklist_repository,
    token_provider=provider,
    user_status_checker=RepositoryUserStatusChecker(user_repository),
)
```

인증 순서는 JWT 서명·만료 검증 → 블랙리스트 확인 → 현재 회원 조회·상태 확인이다.
회원이 없으면 401, 비활성/탈퇴 또는 deleted_at이 있으면 403이다.
기존 토큰이 아직 만료되지 않았더라도 회원 상태가 바뀌면 다음 요청에서 거절한다.
DB 조회 오류는 인증 성공으로 처리하지 않는다.

저장소/세션은 요청 단위로 생성하고 인증 결과를 요청 간 캐시하지 않아야 한다.
같은 장기 세션의 ORM 캐시를 재사용하면 최신 상태 반영이 늦을 수 있다.
로그아웃은 현재 회원 상태 검사 없이 유효한 토큰을 블랙리스트에 등록할 수 있어
탈퇴한 회원도 자신의 토큰을 차단할 수 있다.

## 로그인·로그아웃 API와 인증 의존성

다음 라우터를 작성했다. 아직 main.py나 wiring에는 연결하지 않았다.

| 메서드 | 경로 | 동작 |
| --- | --- | --- |
| POST | /v1/auth/login | 자격 검증 후 액세스 토큰 반환 |
| POST | /v1/auth/logout | 전달된 토큰을 블랙리스트에 등록, 204 반환 |

로그인 요청:

```json
{"email": "user@example.com", "password": "회원 비밀번호"}
```

응답은 공통 APIResponse 형식이며 data에 access_token/token_type/expires_in을 담는다.
토큰 응답은 Cache-Control: no-store로 설정한다. 비밀번호는 SecretStr로 감싸 repr에서 노출하지 않는다.
이메일은 users의 정규화·형식 규칙을 따르고, 비밀번호 공백이나 대소문자는 변형하지 않는다.
추가 필드나 잘못된 입력은 422로 거절한다. 로그인 실패는 401, 탈퇴 회원은 403이다.
전역 요청 검증 핸들러가 응답에 원본 비밀번호를 포함하지 않는 것도 테스트한다.

다른 API는 `auth.presentation.dependencies.get_current_user`를 의존 함수로 사용할 수 있다.
이 함수는 Bearer 토큰과 현재 회원 상태를 모두 검증한 TokenPayload만 반환한다.
누락·잘못된 인증 헤더와 무효 토큰은 401이며 WWW-Authenticate: Bearer 헤더를 반환한다.
auth는 UnauthorizedException을 그대로 전파하고, 공통 SharedException 핸들러가
APIResponse.fail(code="UNAUTHORIZED")와 WWW-Authenticate: Bearer 헤더를 생성한다.
라우터·의존성에서 인증 예외를 HTTPException으로 변환하지 않는다.

로그아웃은 Authorization: Bearer 헤더만 사용한다. get_current_user를 먼저 호출하지 않아
같은 토큰의 중복 로그아웃과 탈퇴 후 로그아웃을 허용한다. 만료·위조 토큰은 401이다.
성공 응답 204에는 본문이 없다. 실제 앱 연결 시 DB commit 성공 후 응답해야 차단이 유지된다.

provide_auth_service는 구성 전에는 503으로 차단한다. wiring에서 실제 AuthService로 주입해야 한다.
요청 세션·실제 비밀번호 해시 구현체·JWT 설정 준비 없이 임시 인증으로 대체하지 않는다.

## 실제 해시 구현 및 주입

users의 기존 PasswordHasher를 구현하는 BcryptPasswordHasher를 auth 내부에 작성했다.
사용자 승인 후 bcrypt 5.x를 pyproject.toml/uv.lock에 추가했다.
실제 해시 생성·비교와 PostgreSQL 저장소·JWT·HTTP의 통합 검증을 완료했다.

기본 비용은 12이고, 비밀번호를 UTF-8로 처리한다. bcrypt의 72바이트 초과 입력은
자르거나 임의로 사전 해싱하지 않고 거절한다. 실제 회원가입 API 연결 시 이 제한을 안내해야 한다.
빈 입력·잘못된 저장 해시는 거절하고, 라이브러리가 없으면 설정 오류를 발생시킨다.
현재 앱이나 회원가입에 적용하지 않았다.

`infrastructure/factory.py`의 create_auth_service는 세션·토큰 공급자·해시 구현체를 받아
실제 저장소와 상태 검사를 조립한다. 비밀번호 해시 구현체는 필수 인자이며 기본 대체 구현은 없다.

```python
from auth.infrastructure.factory import create_auth_service

from auth.infrastructure.password_hasher import BcryptPasswordHasher

service = create_auth_service(session, provider, password_hasher=BcryptPasswordHasher())
```

이는 앱 등록 함수가 아니며 wiring/main.py/users 폴더를 변경하지 않는다.

## 내부 구현 검증 완료 범위

- 실제 bcrypt 해시 생성/비교, 랜덤 salt, 72바이트 경계, 기본 비용 12
- users 엔티티 생성·비밀번호 변경과 해시 호환성
- PostgreSQL 회원 조회 → 자격 검증 → JWT 발급 → 인증 → 로그아웃·블랙리스트 거절
- 탈퇴 후 기존 토큰 접근 및 재로그인 거절
- HTTP 스키마·응답·인증 의존 함수와 서비스 조립
- 격리된 PostgreSQL 테스트 스키마와 데이터의 전체 롤백

## 통합 단계의 후속 작업

- 회원가입·비밀번호 변경 API에 동일한 해시 구현체 주입
- 앱·wiring 연결

현재 JWT 구현은 앱에 연결하지 않았다. DB 구조도 변경하지 않았다.
