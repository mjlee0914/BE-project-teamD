# payments — 교안과 구현 비교 학습

[프로젝트 용어 사전 — 쉬운 뜻과 용어 사이의 관계](../auth/GLOSSARY.md)

이 문서는 **2026-11-04 현재 로컬 코드**를 기준으로 작성했습니다. [교안 전체 목차](https://app.notion.com/p/40c23642356f80ba82ecdb5fd7676586)의 14개 강의를 확인하고, 현재 결제·토큰 블랙리스트 코드에 반영된 개념을 연결합니다.

- 결제 상세 비교: 이 문서.
- [auth 상세 비교](../auth/README.md): JWT·로그아웃·즉시 차단의 교안 대비 변경점.
- **코드 반영 / 모의 테스트 확인 / 실제 통합 완료는 서로 다릅니다.** 두 폴더의 라우터는 아직 실제 `main.py`에 등록되지 않았습니다.
- 이 문서는 실제 PG 결제나 서비스 운영을 완료했다는 설명이 아닙니다. 현재 결제는 가상 승인입니다.


> **2026-11-04 인증 구조 변경:** 결제 라우터와 테스트의 인증 참조를 `token_blacklist`에서 `auth`로 변경했습니다. Auth는 추상 인터페이스를 사용하고 `auth/wiring.py`에서 구체 객체를 조립합니다. 결제 API·서비스의 업무 규칙은 유지했습니다. 아래 전체 교안 표는 기존 14개 강의를 기준으로 하며, 추가 Auth 교안의 구조 적용은 [auth README](../auth/README.md)에 정리했습니다.


> **교안 이름 정렬:** 인증 객체는 `auth.domain.entities.TokenPayload`, 서비스 주입 명세는 `provide_auth_service`입니다. 인증 주소는 `/v1/auth/logout`·`/v1/auth/refresh`로 변경됐습니다. 결제 API 주소와 결제 업무 규칙은 유지합니다.

## 1. 전체 교안 반영표

아래의 미구현 표시는 **두 담당 폴더 범위**의 판단입니다. 프로젝트 전체에 없다고 단정하는 의미가 아닙니다. 교안 개념은 요약했으며, 예제를 그대로 옮겼다는 뜻은 아닙니다.

| 교안 원문 | 핵심 개념 | auth에 반영 | payments에 반영 | 남아 있는 차이 |
| --- | --- | --- | --- | --- |
| [1장 1강: 환경 설정][L11] | FastAPI, uv, 실행 환경·로깅 | 공통 DB 환경과 라이브러리 사용 | 동일 | PyJWT는 프로젝트 의존성에 미등록. 두 폴더의 독립 배포·로깅 구현은 없음 |
| [1장 2강: HTTP와 라우팅][L12] | 경로·메서드·상태 코드 | POST 로그아웃·재발급 | POST 생성, GET 조회, PATCH 취소 | 교안의 PUT·DELETE 등을 전부 구현할 필요는 없으며, 현재 물리 삭제 API는 없음 |
| [2장 1강: Pydantic 검증][L21] | 타입, BaseModel, Field, 검증 | 리프레시 요청의 길이 검증 | 양수 ID·0 이상 금액·엄격한 타입·공백 처리 | 교안의 모든 validator를 사용하지는 않음. 금액 일치 같은 업무 규칙은 도메인에서 판단 |
| [2장 2강: 응답·자동 문서화][L22] | response_model, 응답 필터링, Swagger | 토큰·로그아웃 응답 분리 | PaymentResponse, 설명·예상 상태 코드 | 교안의 제네릭 APIResponse 공통 래퍼는 미사용. 실제 서버의 문서 등록은 미완료 |
| [3장 1강: 매개변수·예외][L31] | Annotated, Path, Query, HTTPException | 인증 실패 401·Bearer 헤더 | Path(gt=0), 400·403·404 변환 | 목록 검색·Query·페이지네이션은 없음. 전역 핸들러 전체 통합도 미완료 |
| [3장 2강: Jinja2·정적 파일][L32] | 서버 HTML 렌더링 | 미구현 | 미구현 | 두 폴더는 현재 JSON API 중심 |
| [4장 1강: 라우터·미들웨어][L41] | APIRouter, prefix, tags, Depends | `/auth`, 서비스·인증 주입 | `/payments`, 인증·DB·서비스 주입 | 전역 미들웨어는 이 폴더에서 추가하지 않음. main의 include_router 미등록 |
| [4장 2강: 후처리·스트리밍][L42] | BackgroundTasks, StreamingResponse | 미구현. 차단 등록은 응답 전 커밋 | payment_log 컬럼만 있음 | 로그 후처리·파일 다운로드는 미구현. async def 자체가 백그라운드 태스크는 아님 |
| [5장 1강: PostgreSQL·ORM][L51] | 테이블, FK, 제약조건, 저장·조회 | jti 기본키와 회원 FK | 예매 FK, 상태·금액 제약, JSONB, 자동 ID | 교안의 동기 예제 대신 비동기 사용. 테이블 생성·마이그레이션 미실행 |
| [5장 2강: 비동기·동시성][L52] | AsyncSession, 풀, 비관적 락 | 비동기 저장·조회 | 예매 행 잠금, 기존 승인 확인, 잠금 조회 후 상태 복원 | 풀은 공통 DB 설정 사용. 실제 PostgreSQL 동시 요청 검증·즉시 로딩 전략은 미적용 |
| [6장 1강: OAuth2·JWT][L61] | 로그인, 해싱, 토큰, 블랙리스트 | JWT·로그아웃·재발급 반영, 두 토큰 차단으로 확장 | JWT의 회원 ID로 소유권 확인 | OAuth2 폼 로그인·Bcrypt·회원 상태 조회는 미구현 |
| [7장 1강: 4계층][L71] | 순수 도메인, 객체 변환, 서비스 커밋 | 역할별 폴더·레포지토리·서비스 | 상태 변경 도메인, 복원, 저장·서비스·라우터 분리 | 의존성 조립의 인프라 직접 참조 등 엄격한 규칙과의 차이는 아래 별도 설명 |
| [7장 2강: 캐싱·CORS][L72] | TTL 캐시, CORS 미들웨어 | 미구현 | 미구현 | 인메모리 테스트용 데이터는 서비스 캐시 구현이 아님 |
| [7장 3강: 배포][L73] | 환경 변수, Git, EC2·systemd·Nginx | JWT_SECRET_KEY 주입 부분 반영 | 공통 DATABASE_URL 사용 | 실제 클라우드 배포·HTTPS·상시 실행 구성은 두 폴더에서 미구현 |

## 2. 파일 구조와 책임

```text
payments/
├─ README.md
├─ __init__.py
├─ domain/
│  ├─ __init__.py
│  ├─ entities.py                 # 결제 상태·검증·상태 복원
│  └─ reservation.py              # 결제 판단용 예매 정보·규칙
├─ infrastructure/
│  ├─ __init__.py
│  ├─ models.py                   # payments 테이블
│  ├─ repositories.py             # 결제 저장·조회·도메인 변환
│  └─ reservation_repository.py   # 기존 예매 모델 읽기·잠금·변환
├─ application/
│  ├─ __init__.py
│  └─ service.py                  # 생성·조회·취소와 트랜잭션
├─ presentation/
│  ├─ __init__.py
│  ├─ schemas.py                  # 요청·응답 형식
│  ├─ dependencies.py             # DB와 서비스 조립
│  └─ router.py                   # 인증, HTTP 경로·예외 변환
└─ tests/
   ├─ __init__.py
   ├─ test_domain.py
   ├─ test_repositories.py
   ├─ test_service.py
   └─ test_router.py
```

각 `__init__.py`는 패키지 구성용입니다. 테스트·README는 추가 계층이 아닙니다. 교안의 `registration`·`Course` 예제를 결제 업무에 맞게 바꾼 것이므로 이름과 파일 개수가 같을 필요는 없습니다. [7장 1강 프로젝트 구조·도메인·레포지토리 예제][L71]

## 3. 파일별 교안 비교

| 파일·열어볼 식별자 | 교안에서 배우는 내용 | 현재 코드의 반영과 효과 |
| --- | --- | --- |
| [domain/entities.py](domain/entities.py)의 `Payment`, `PaymentStatus` | [7장 1강: 순수 도메인·풍부한 모델][L71] | 표준 라이브러리만 사용합니다. 금액 검증·상태 변경을 객체가 수행합니다. DB 모델과 별개입니다. |
| 같은 파일의 `approve()`, `fail()`, `cancel()` | [7장 1강 도메인 메서드][L71] | 요청 금액 일치, 승인·실패·취소 가능 상태, 승인·취소 시각의 순서를 검사합니다. 업무 규칙이 라우터에 흩어지는 것을 줄입니다. |
| 같은 파일의 `restore()` | [7장 1강 §3.3: 순수 객체 조립][L71] | 저장된 상태와 정보를 검증하며 복원합니다. PAID 기록이 조회 후 READY로 초기화되는 실수를 막습니다. 교안보다 상세한 복원 로직입니다. |
| [domain/reservation.py](domain/reservation.py)의 `ReservationPaymentInfo` | [7장 1강: 외부 모델과 도메인 분리][L71], [6장 1강: 인가][L61] | 결제에 필요한 예매 값만 받고 본인 여부, PENDING, 만료 시각, 취소 완료 여부를 판단합니다. 다른 도메인의 ORM을 서비스에 넘기지 않습니다. |
| [infrastructure/models.py](infrastructure/models.py)의 `PaymentModel` | [5장 1강 §4.2~4.3: 스키마·컬럼][L51] | ERD의 12개 컬럼, 예매 FK, 자동 ID, 상태·금액 제약, 승인 키 유일성, JSONB 로그를 정의합니다. |
| [infrastructure/repositories.py](infrastructure/repositories.py)의 `save()` | [5장 1강: 저장·refresh][L51], [7장 1강 §3.3: 레포지토리][L71] | 새 객체는 add, 기존 객체는 상태 갱신 후 flush·refresh합니다. DB가 만든 ID·시각을 도메인에 반영하고 로그는 덮어쓰지 않습니다. |
| 같은 파일의 `find_by_id()`, `find_by_reservation_id()` | [7장 1강: ORM → 도메인][L71] | `_to_domain()` → `Payment.restore()`로 변환합니다. 같은 예매의 실패·재시도 기록을 ID 순으로 반환합니다. |
| [infrastructure/reservation_repository.py](infrastructure/reservation_repository.py) | [5장 2강 §1.4: 비관적 락][L52], [7장 1강: 변환 격리][L71] | 기존 예매 모델을 읽어 결제용 정보로 변환합니다. `for_update=True`일 때 잠금을 요청합니다. 예매 상태를 변경하지 않습니다. |
| [application/service.py](application/service.py)의 `pay()` | [7장 1강 §4.2: 시나리오·트랜잭션][L71], [5장 2강: 경합 방어][L52] | 예매 잠금 → 조건 확인 → 기존 승인 확인 → 도메인 처리 → 저장 → 커밋을 조율합니다. 금액의 기준은 예매 DB 값입니다. |
| 같은 파일의 `get_payment()`, `cancel()` | [6장 1강: 인가][L61], [7장 1강: 서비스][L71] | 조회도 소유자를 검사합니다. 결제 취소는 예매가 이미 CANCELED일 때만 가능합니다. 오류 시 변경 작업은 롤백합니다. |
| [presentation/schemas.py](presentation/schemas.py)의 `PaymentCreate` | [2장 1강: 타입·Field 검증][L21] | ID 양수, 금액 0 이상, 공백 제거, strict 타입, extra 금지로 HTTP 입력을 검증합니다. `user_id` 주입도 거절합니다. |
| 같은 파일의 `PaymentResponse` | [2장 2강: 응답 필터링][L22], [7장 1강: from_attributes][L71] | 도메인 객체를 `model_validate()`로 응답 모델에 맞춥니다. 내부 로그는 응답 필드에 없습니다. |
| [presentation/dependencies.py](presentation/dependencies.py) | [4장 1강 §1.3: Depends][L41], [5장 1강: get_db][L51] | 공통 DB 세션을 받아 PaymentService를 조립합니다. 별도 엔진을 중복 생성하지 않습니다. |
| [presentation/router.py](presentation/router.py) | [1장 2강][L12], [3장 1강][L31], [4장 1강][L41] | POST·GET·PATCH, prefix·tags, 양수 Path, 서비스 호출, 400·403·404 변환을 정의합니다. JWT 검증 실패는 인증 의존성에서 401로 변환합니다. |

## 4. 교안의 기술을 결제 업무에 적용한 부분

교안은 도서·식료품·수강 신청·콘서트 좌석 등으로 원리를 설명합니다. 아래의 결제 상태·실패 기록·예매 연계 정책은 **팀 ERD 및 이번 구현의 업무 규칙**이며, 교안이 이 결제 설계를 그대로 제시한 것은 아닙니다.

```text
READY ── approve() → PAID ── cancel() → CANCELED
  └──── fail() → FAILED
```

| 업무 규칙 | 구현 위치 | 바뀌는 효과 |
| --- | --- | --- |
| 결제 금액은 예매의 final_price 기준 | `PaymentService.pay()` | 클라이언트가 낮은 금액을 보내도 저장 기준 금액은 바뀌지 않습니다. |
| 요청 금액 불일치 | `Payment.approve()` + 서비스의 실패 처리 | 도메인은 ValueError를 발생시키고, 서비스는 FAILED 기록으로 저장합니다. |
| 가상 승인 실패 | `simulate_failure=True` | FAILED와 실패 사유를 기록합니다. 실제 PG 통신은 없습니다. |
| 실패 후 재시도 | 서비스의 새 Payment 생성 | 이전 FAILED 기록을 유지하고 새 행을 만듭니다. |
| 기존 PAID 또는 CANCELED 기록 존재 | 서비스의 기존 시도 검사 | 같은 예매의 새 결제를 거절합니다. 현재 서비스에 남아 있는 업무 조건문입니다. |
| 예매 취소 후 결제 취소 | `ensure_canceled()` + `Payment.cancel()` | 예매·티켓을 직접 취소하지 않고, 이미 취소된 예매의 승인 결제 상태만 바꿉니다. |
| 기록 생성과 승인 여부 구분 | POST 응답 | HTTP 201은 기록 생성 완료입니다. PAID/FAILED는 응답 status로 구분합니다. |

`0원` 결제는 현재 허용하며 결제 수단 목록은 아직 열려 있습니다. 부분 취소·부분 환불·실제 PG 승인·환불은 구현하지 않았습니다.

## 5. 한 요청의 흐름으로 읽기

### 생성 요청

라우터가 서버에 등록된 뒤 사용할 요청 형태입니다. 현재 실제 main에는 등록하지 않았으므로 아래 예시만으로 실제 서버에서 호출할 수 있다는 뜻은 아닙니다.

```http
POST /payments
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "reservation_id": 1,
  "method": "CARD",
  "requested_amount": 50000
}
```

```text
JWT 검증·블랙리스트 검사 → claims.user_id 획득
요청 스키마 검증 → PaymentService.pay()
  → 예매 행 SELECT ... FOR UPDATE
  → 본인·PENDING·만료 여부 확인
  → 기존 승인 시도 확인
  → 예매 final_price로 Payment 생성
  → approve() 또는 fail()
  → Repository.save(): flush → refresh
  → db.commit()
응답 PaymentResponse → 201
```

인증·다른 의존성은 입력 검증 과정에서도 평가될 수 있습니다. 위 그림은 책임을 이해하기 위한 흐름이며, FastAPI 내부의 모든 검증 실행 순서를 보장하는 설명은 아닙니다.

### flush·refresh·commit의 차이

| 작업 | 담당 | 효과 |
| --- | --- | --- |
| `flush()` | 레포지토리 | 변경 SQL을 DB로 보내지만 트랜잭션을 확정하지 않습니다. |
| `refresh()` | 레포지토리 | DB에서 ID·기본값·시각 등 현재 값을 다시 읽습니다. |
| `commit()` | 서비스 | 트랜잭션을 확정합니다. 성공 반환 전에 기다립니다. |
| `rollback()` | 변경 서비스의 예외 처리 | 오류가 나면 미확정 작업을 취소하고 오류를 다시 전달합니다. |

[5장 1강의 ORM 저장 설명][L51]과 [7장 1강의 서비스 커밋 예제][L71]를 함께 보세요. 현재 구조에서 레포지토리가 먼저 커밋하면 여러 작업을 한 트랜잭션으로 묶기 어렵습니다.

### 동시성 부분

[5장 2강 §1.4의 비관적 락][L52]을 같은 예매의 결제 요청에 적용했습니다. 예매 행을 잠근 뒤 기존 승인 기록을 확인하고, 커밋·롤백 시 잠금을 해제합니다. 대기 후의 현재 시각으로 만료를 검사합니다.

`populate_existing=True`로 이미 세션에 있던 객체도 다시 읽도록 했습니다. 이 옵션은 프로젝트에서 보강한 부분입니다. 실제 동시성 보장은 PostgreSQL과 관련 변경 경로의 잠금 규칙을 함께 검증해야 합니다. 현재 테스트는 SQL 구성과 호출 순서를 확인하며 실제 경합을 재현하지 않습니다.

## 6. API와 오류 비교

| API | 정상 반환 | 교안과 비교할 점 |
| --- | --- | --- |
| `POST /payments` | 201 + PaymentResponse | POST의 생성 의미를 결제 시도 기록에 적용. FAILED도 기록 생성은 성공할 수 있음 |
| `GET /payments/{payment_id}` | 200 + PaymentResponse | 경로 변수·본인 소유 확인 |
| `PATCH /payments/{payment_id}/cancel` | 200 + PaymentResponse | 결제 상태 변경. 기록을 물리 삭제하지 않음 |

| 상태 코드 | 현재 의미 | 처리 위치 |
| --- | --- | --- |
| 400 | 예매 상태·만료·중복 승인·취소 조건 위반 | 도메인/서비스의 ValueError → 라우터 |
| 401 | 누락·만료·잘못된 종류·차단된 JWT | auth의 인증 의존성 |
| 403 | 다른 회원의 예매·결제 | PermissionError → 라우터 |
| 404 | 예매·결제 미존재 | LookupError → 라우터 |
| 422 | 입력 타입·범위·추가 필드 오류 | Pydantic/FastAPI |
| 500 | DB 오류 등 예상하지 못한 실패 | 전파. 실제 앱의 전역 핸들러와 별도 통합 필요 |

[3장 1강의 HTTPException·전역 예외 처리][L31]와 비교하세요. 현재는 라우터별 변환입니다. [2장 2강의 공통 APIResponse 예제][L22]와 같은 래퍼를 사용한 것은 아니며 예상 오류 본문은 `{"detail": "..."}`입니다.

## 7. 아키텍처의 반영 범위와 미완료 항목

- 도메인은 FastAPI·SQLAlchemy를 import하지 않습니다.
- ORM → 도메인 변환을 레포지토리에 모았습니다. 라우터는 PaymentModel을 직접 받지 않습니다.
- 예매 모델 참조는 `payments/infrastructure/reservation_repository.py`에 격리했습니다. 예매 폴더 파일은 수정하지 않습니다.
- 응용은 도메인 처리·저장·커밋을 조율하지만, 기존 승인 여부 같은 업무 조건도 일부 직접 검사합니다. 모든 조건이 도메인으로 옮겨진 완성형은 아닙니다.
- 표현의 `dependencies.py`는 공통 DB의 AsyncSession을 사용합니다. 7장 의존성 표를 아주 엄격히 해석하면 표현→인프라 조립 예외가 남습니다.
- 응용이 구체 AsyncSession과 레포지토리를 참조하므로 DB 기술로부터 완전히 독립한 설계는 아닙니다.
- 현재 결제 도메인은 dataclass의 공개 필드를 사용합니다. 메서드를 통해 변경하는 규칙은 구현했지만, 외부의 직접 속성 대입까지 차단한 모델은 아닙니다.

위 평가는 [7장 1강의 의존성 표·순수 도메인·서비스 예제][L71]와 현재 코드를 대조한 결과입니다. 폴더 구조의 반영과 모든 설계 원칙의 완전 준수는 구분합니다.

| 아직 남은 작업 | 현재 근거·의미 |
| --- | --- |
| 실제 서버 라우터 등록 | 현재 main.py는 예매·회원 라우터만 등록합니다. |
| 모델 등록·테이블 생성·실제 DB 테스트 | ORM 정의와 모의 테스트는 있지만, 이 작업에서 DB를 생성하지 않았습니다. create_all은 기존 테이블 구조를 수정하는 마이그레이션도 아닙니다. [5장 1강 §4.1][L51] |
| 결제 후 예매 확정·티켓 발급 | 현재 PaymentService는 예매·티켓 상태를 변경하지 않습니다. 결제 PAID만으로 예매가 확정되는 것은 아닙니다. |
| 로그인·회원 상태 확인 | JWT 도구·Bearer 검사는 있지만 OAuth2 로그인·해싱·회원 상태 조회는 아직 없습니다. |
| 결제 로그 후처리 | payment_log JSONB 컬럼은 있지만 BackgroundTasks 기록 작업은 없습니다. |
| 캐시·목록·페이지네이션·웹 화면 | 관련 교안 개념 중 아직 두 폴더에 적용하지 않은 기능입니다. |

## 8. 테스트와 재현 방법

| 테스트 파일 | 개수 | 검증 범위 |
| --- | --- | --- |
| [tests/test_domain.py](tests/test_domain.py) | 14 | 상태 전이, 금액, 승인·취소 시각, 재시도 |
| [tests/test_repositories.py](tests/test_repositories.py) | 12 | 상태 복원, ID 반영, 기존 정보 보존, 잠금 SQL |
| [tests/test_service.py](tests/test_service.py) | 21 | 소유자·만료·금액·실패·커밋·취소와 예매 어댑터 |
| [tests/test_router.py](tests/test_router.py) | 15 | HTTP·실제 JWT 검증, 입력·응답·오류 매핑·문서화 |

결제 62개와 인증 37개로 작성 시점 총 99개입니다. 인증 구현·테스트는 auth로 이전했으며 인터페이스·객체 조립 검증 10개가 추가됐습니다. 테스트는 표준 unittest를 사용합니다. DB는 모의 객체이며 실제 PostgreSQL 연동·경합·예매 확정·PG 통신 검증을 뜻하지 않습니다.

프로젝트 루트의 **PowerShell**에서 아래 명령을 실행합니다. 현재 PyJWT 등의 정식 의존성 반영을 보류하고 있어 임시 uv 환경을 사용합니다. 명령은 루트 pyproject.toml·uv.lock을 수정하지 않으며, uv는 패키지 다운로드·캐시를 사용할 수 있습니다.

```powershell
@'
import logging
import os
import sys
import unittest

# 이 파이썬 프로세스에서만 쓰는 테스트용 설정입니다. 실제 DB에는 접속하지 않습니다.
os.environ['DATABASE_URL'] = 'postgresql+asyncpg://test:test@127.0.0.1:5432/test'
sys.path.insert(0, 'src')
logging.disable(logging.CRITICAL)

roots = ['src/auth/tests', 'src/payments/tests']
loader = unittest.TestLoader()
suite = unittest.TestSuite()
for root in roots:
    suite.addTests(loader.discover(root, top_level_dir='src'))
result = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(not result.wasSuccessful())
'@ | uv run --no-project --with 'pyjwt>=2.10,<3' --with 'sqlalchemy>=2,<3' --with fastapi --with httpx --with httpx2 --with python-dotenv --with asyncpg python -B -
```

두 폴더에 모두 `test_service.py`가 있으므로 `top_level_dir='src'`로 패키지 이름을 구분합니다.

`roots`를 `['src/payments/tests']`로 바꾸면 결제만, `['src/auth/tests']`로 바꾸면 인증만 검사합니다. 이 환경 설정은 실제 서버 실행을 완료해 주는 설정이 아닙니다.

## 9. 추천 학습 순서

1. [7장 1강][L71]을 읽고 두 README의 폴더 트리에서 각 계층을 찾습니다.
2. `Payment`와 `PaymentModel`, `BlacklistToken`와 `TokenBlacklistModel`을 비교합니다.
3. 레포지토리의 `_to_domain()`·`restore()`에서 어떤 객체가 반환되는지 확인합니다.
4. [5장 1강][L51]·[5장 2강][L52]을 읽고 flush·refresh·commit·잠금의 위치를 표시합니다.
5. [6장 1강][L61]과 [인증 README의 교안 비교](../auth/README.md#5-교안과-동일하게-맞춘-부분--유지한-차이)을 비교합니다.
6. [2장 1강][L21]·[2장 2강][L22]·[3장 1강][L31]을 읽고 422와 400의 차이를 테스트에서 찾습니다.
7. 요청 하나를 따라 domain → repository → service → router의 책임을 자기 말로 설명합니다.

### 스스로 확인하기

- [ ] 사용자 요청의 금액과 DB 예매 금액 중 어느 것을 저장하는지 설명한다.
- [ ] FAILED를 저장하는 경우와 롤백하는 경우를 구분한다.
- [ ] 201 응답이 결제 승인을 보장하지 않는 이유를 설명한다.
- [ ] 예매 행 잠금이 필요한 이유와 모의 테스트의 한계를 설명한다.
- [ ] 금액 일치 검증이 Pydantic이 아닌 도메인에 있는 이유를 설명한다.
- [ ] HTTPBearer 사용만으로 OAuth2 로그인 완료라고 할 수 없는 이유를 설명한다.
- [ ] PAID 결제가 아직 예매 확정·티켓 발급 완료를 뜻하지 않음을 설명한다.

[L11]: https://app.notion.com/p/40c23642356f80a5959bd5f804f30f70
[L12]: https://app.notion.com/p/40c23642356f80728875c1f04d603800
[L21]: https://app.notion.com/p/40c23642356f80b2bd6cea1c9127ab23
[L22]: https://app.notion.com/p/40c23642356f80b387edcb6a368fb80f
[L31]: https://app.notion.com/p/40c23642356f80528d1ed5eacca183d6
[L32]: https://app.notion.com/p/40c23642356f80eabd75e75fd83ce0d3
[L41]: https://app.notion.com/p/40c23642356f80d49b34cc4b895328da
[L42]: https://app.notion.com/p/40c23642356f80ddadadce7a2070a510
[L51]: https://app.notion.com/p/40c23642356f801a8d97e52a27802eff
[L52]: https://app.notion.com/p/40c23642356f80eb85f3d37e3180bdd2
[L61]: https://app.notion.com/p/40c23642356f8054a741fd0c28bc80e8
[L71]: https://app.notion.com/p/40c23642356f80629181df5a298f6733
[L72]: https://app.notion.com/p/40c23642356f806b8290d4c9e1727021
[L73]: https://app.notion.com/p/40c23642356f80838e61deddb97f8bfe
