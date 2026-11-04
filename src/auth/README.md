# auth — 교안에 맞춘 구성과 이름

[프로젝트 용어 사전 — 쉬운 뜻과 용어 사이의 관계](GLOSSARY.md)

2026-11-04 기준 문서입니다. [인증/인가 도메인(Auth) 교안](https://app.notion.com/p/40e23642356f80af9615d17333f2e903)과 비교하기 쉽도록 파일·클래스·메서드 이름을 맞췄습니다. 기존 블랙리스트 서비스는 AuthService로 통합했습니다.

## 1. 현재 파일 구조

```text
auth/
├─ domain/
│  ├─ entities.py          # TokenPayload, BlacklistToken, UnauthorizedException
│  ├─ repository.py        # TokenBlacklistRepository 인터페이스
│  └─ service.py           # TokenProvider, TransactionManager 인터페이스
├─ application/
│  └─ service.py           # AuthService: 인증·로그아웃·재발급·커밋 조율
├─ infrastructure/
│  ├─ models.py            # TokenBlacklistModel
│  ├─ repositories.py      # SqlAlchemyTokenBlacklistRepository
│  ├─ security.py          # JwtTokenProvider
│  └─ transactions.py      # SqlAlchemyTransactionManager
├─ presentation/
│  ├─ dependencies.py      # provide_auth_service, get_current_token
│  ├─ schemas.py           # TokenResponse, RefreshTokenRequest, LogoutResponse
│  └─ routers/
│     └─ v1/
│        └─ router.py      # /v1/auth/logout, /v1/auth/refresh
├─ wiring.py              # 실제 구현체 조립·바인딩
├─ tests/
├─ GLOSSARY.md            # 계층·문법·도구·DB·인증 용어 사전
└─ README.md
```

각 패키지에는 `__init__.py`가 있습니다. 별도의 domain/tokens.py와 application/blacklist_service.py는 통합 후 제거했습니다.

## 2. 이름과 배치 변경표

| 이전 | 현재 | 교안과 연결 |
| --- | --- | --- |
| TokenClaims | [TokenPayload](domain/entities.py) | 검증된 토큰 정보를 표현. 만료 시각 exp도 전달 |
| TokenBlacklistEntry | [BlacklistToken](domain/entities.py) | 차단할 토큰의 정보와 검증 |
| JWTTokenProvider | [JwtTokenProvider](infrastructure/security.py) | 교안과 같은 클래스 표기 |
| decode_access_token / decode_refresh_token | TokenProvider.decode_token() | 검증 메서드 이름 통합. expected_type으로 토큰 용도 검사 유지 |
| save() | TokenBlacklistRepository.add() | 차단 기록 추가. 현재 ERD에 맞춰 jti·user_id를 받음 |
| exists_by_jti() | TokenBlacklistRepository.is_blacklisted() | 차단 여부 조회 |
| authenticate_access_token() | AuthService.authenticate_token() | 보호 API용 인증 처리 |
| get_auth_service() | [provide_auth_service()](presentation/dependencies.py) | 구체 구현을 모르는 주입 명세 |
| AccessTokenResponse | [TokenResponse](presentation/schemas.py) | 토큰 응답 스키마 이름 통일 |
| TokenValidationError | UnauthorizedException | 인증 오류 이름 통일. 공유 예외 파일은 수정 범위 밖이므로 entities.py에 정의 |
| TokenBlacklistService | [AuthService](application/service.py) 내부로 통합 | 교안처럼 인증·차단 흐름을 응용 서비스 한 곳에서 조율 |
| presentation/router.py | [presentation/routers/v1/router.py](presentation/routers/v1/router.py) | 교안의 실제 예제 경로에 맞춰 이동 |
| /auth/logout, /auth/refresh | /v1/auth/logout, /v1/auth/refresh | 버전 접두사 적용. 이전 주소는 별칭으로 제공하지 않음 |

과거 이름은 비교표의 이력 설명입니다. 실행 코드는 새 이름을 사용합니다. 구형 import 경로에 대한 호환 래퍼는 두지 않았습니다.

## 3. 도메인과 인터페이스

[domain/entities.py](domain/entities.py)는 TokenPayload와 BlacklistToken을 함께 정의합니다. TokenPayload는 회원 ID·jti·만료 시각·토큰 종류를 담고, BlacklistToken은 현재 DB에 저장할 jti·회원 ID를 검증합니다. JWT 문자열을 도메인 객체로 변환했다고 해서 임의의 객체가 인증된 것은 아니며, 실제 요청은 JwtTokenProvider의 검증을 거칩니다.

[domain/repository.py](domain/repository.py)는 add()·is_blacklisted() 계약을 정의합니다. 기존 상세 조회 기능은 find_by_jti()로 유지했습니다. 구체 구현은 ORM 객체를 상위로 노출하지 않고 BlacklistToken 또는 bool을 반환합니다.

[domain/service.py](domain/service.py)는 토큰 발급·검증과 트랜잭션의 계약을 정의합니다. domain과 application은 SQLAlchemy·PyJWT·FastAPI를 import하지 않습니다.

## 4. AuthService로 통합한 흐름

```text
AuthService.logout(token, refresh_token)
  → decode_token(token)
  → decode_token(refresh_token, expected_type="refresh")
  → 두 회원 ID가 같은지 검사
  → BlacklistToken 생성·검증
  → _blacklist_repo.add(access의 jti, user_id)
  → _blacklist_repo.add(refresh의 jti, user_id)
  → _transaction.commit()
  → 성공 반환
```

저장·커밋 오류는 rollback 후 다시 전달합니다. SQLAlchemy 구현체는 같은 AsyncSession을 공유합니다. 중복 jti는 ON CONFLICT DO NOTHING으로 기존 기록을 유지합니다. 차단 등록을 백그라운드로 미루지 않습니다.

authenticate_token()은 액세스 토큰을 검증하고 is_blacklisted()를 조회합니다. refresh_access_token()은 리프레시 토큰 용도를 명시적으로 검사하고 차단되지 않은 경우 새 액세스 토큰을 발급합니다.

## 5. 교안과 동일하게 맞춘 부분 / 유지한 차이

| 항목 | 현재 선택과 이유 |
| --- | --- |
| 4계층·클래스·핵심 메서드 이름 | 교안과 같은 책임은 같은 이름으로 통일 |
| 도메인 객체 배치 | entities.py로 통합 |
| 객체 조립 | provide_auth_service 주입 명세를 wiring.py의 create_auth_service에 바인딩 |
| wiring 위치 | 교안의 src/wiring/auth.py 대신 auth/wiring.py. 현재 수정 허용 범위에 맞춘 배치 |
| 회원 ID | 교안 UUID 대신 팀 ERD의 BIGINT/int 유지 |
| JWT | 기존 HS256, 액세스 30분·리프레시 7일 유지. create_access_token()은 기존처럼 문자열 반환이며 교안의 메타데이터 포함 튜플 반환과 다름 |
| decode_token() | 교안 이름으로 통일하되 expected_type 인자를 추가해 두 종류 구분 |
| 차단 테이블 | token_blacklist 이름과 jti·user_id 유지. expired_at 컬럼 추가 안 함 |
| 트랜잭션 | 공통 get_db가 자동 커밋하지 않으므로 TransactionManager를 유지 |
| 예외 위치 | 공유 파일 수정 없이 auth/domain/entities.py의 UnauthorizedException 사용 |
| 로그아웃 API | 교안의 204·액세스 토큰 한 개 대신 기존 200·두 토큰 차단 유지 |
| TokenResponse | 이름은 교안과 동일. 기존 access_token·token_type 응답 유지, expires_in 필드는 아직 없음 |
| 로그인·해싱 | 아직 미구현. 회원 저장소·비밀번호 검증 연동은 별도 단계 |
| cleanup_expired() | DB 만료 컬럼을 유지하지 않기로 한 현재 정책에서는 미구현 |

교안의 모든 기능을 완성했다고 표시한 것은 아닙니다. 이번에는 파일·이름 정렬과 서비스 통합을 수행했고, 로그인 연동과 인증 정책 변경은 남겨 두었습니다.

## 6. 의존성 주입과 payments 연결

[wiring.py](wiring.py)의 build_auth_service()는 저장소·토큰 발급기·트랜잭션 구현체를 조립합니다. wire_auth_dependencies(app)는 다음 바인딩을 적용합니다.

```python
app.dependency_overrides[provide_auth_service] = create_auth_service
```

provide_auth_service()의 NotImplementedError는 의도된 주입 명세입니다. 실제 요청 전에 wiring을 연결해야 합니다. [결제 라우터](../payments/presentation/router.py)는 auth.domain.entities의 TokenPayload와 auth.presentation.dependencies의 get_current_token을 사용합니다.

추후 수정 범위가 넓어지면 실제 앱 초기화에서 아래 연결이 필요합니다. 현재 main.py에 적용한 코드는 아닙니다.

```python
from auth.presentation.routers.v1.router import router as auth_router
from auth.wiring import wire_auth_dependencies
from payments.presentation.router import router as payment_router

wire_auth_dependencies(app)
app.include_router(auth_router)
app.include_router(payment_router)
```

## 7. 검증·남은 작업

인증 37개·결제 62개, 총 99개 테스트가 있습니다. 이름·경로 변경에 맞춰 테스트를 갱신했습니다. JWT 만료·종류·서명 검증, 두 토큰 차단·커밋·롤백, 객체 조립, 결제 인증을 확인합니다. 실제 JWT와 테스트 앱을 사용하지만 DB는 모의 세션입니다.

[결제 README의 테스트 명령](../payments/README.md#8-테스트와-재현-방법)은 그대로 사용할 수 있습니다. 인증만 검사하려면 roots를 `['src/auth/tests']`로 지정하세요.

실제 앱 라우터·wiring·모델 등록, 정식 의존성·환경 변수 설정, 실제 DB 통합 검증은 아직 별도 작업입니다. 로그인·UserCredentialVerifier 구현과 회원 연동, 만료 차단 기록 정리도 이번 단계에 포함하지 않았습니다.
