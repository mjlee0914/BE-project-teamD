# 프로젝트 용어 사전 — auth · payments

처음 배우는 사람이 코드를 읽고 팀원과 설명할 때 사용할 공통 용어를 정리합니다. **최종 업데이트: 2026-11-04 / 초안 v1**

- [Auth 구조·교안 비교](README.md)
- [Payments 구조·교안 비교](../payments/README.md)
- 뜻은 두 문장 이내로 작성하고, 마지막 열에서 실제 코드와 다른 용어를 연결합니다.
- 이 문서의 예시는 현재 코드 기준입니다. 교안에 있어도 아직 구현하지 않은 기능은 구현 완료로 표시하지 않습니다.

## 목차

1. [프로젝트를 이해하는 기본 용어](#1-프로젝트를-이해하는-기본-용어)
2. [4계층별 용어](#2-4계층별-용어)
3. [파이썬 기본 문법](#3-파이썬-기본-문법)
4. [사용 도구와 라이브러리](#4-사용-도구와-라이브러리)
5. [DB와 인증 관련 용어](#5-db와-인증-관련-용어)
6. [헷갈리기 쉬운 용어 비교](#6-헷갈리기-쉬운-용어-비교)
7. [팀원에게 설명할 때 쓸 수 있는 문장](#7-팀원에게-설명할-때-쓸-수-있는-문장)
8. [업데이트 방법과 기록](#8-업데이트-방법과-기록)

## 1. 프로젝트를 이해하는 기본 용어

| 용어 | 쉬운 뜻 | 프로젝트에서의 관계·예시 |
| --- | --- | --- |
| 도메인(Domain) | 프로그램이 해결하려는 업무 영역입니다.<br>인증·결제처럼 각각 다루는 문제와 규칙이 있습니다. | `auth`는 인증, `payments`는 결제 영역이며 각 폴더 안에 4계층이 있음 |
| 계층(Layer) | 역할이 비슷한 코드를 모아 나눈 구역입니다.<br>구역마다 책임을 정해 변경의 영향을 줄입니다. | `presentation`·`application`·`domain`·`infrastructure` |
| 책임(Responsibility) | 어떤 코드가 맡아서 처리해야 할 일입니다.<br>역할이 분명하면 수정할 위치를 찾기 쉽습니다. | 요청 형식 검사 → 스키마 / 결제 승인 규칙 → `Payment` |
| 의존성(Dependency) | 어떤 코드가 동작하기 위해 다른 코드의 기능이나 정의를 필요로 하는 관계입니다.<br>코드에서는 import나 생성자 인자 등으로 드러납니다. | `AuthService`는 `TokenProvider`의 발급·검증 기능을 필요로 함 |
| 순환 의존(Circular Dependency) | A가 B를 필요로 하고 B도 다시 A를 필요로 하는 연결입니다.<br>이 관계가 길게 이어져 원래 코드로 돌아오는 경우도 포함합니다. | 현재 `auth`·`payments` 내부 모듈에서는 검사 시 순환 import가 발견되지 않음 |
| 캡슐화(Encapsulation) | 관련된 정보와 처리 규칙을 한곳에 모으고, 정해진 방법으로 다루게 하는 설계입니다.<br>규칙을 여러 곳에 반복해서 쓰는 것을 줄입니다. | `Payment.approve()`에 금액·승인 가능 상태 검사 배치. 현재 공개 필드의 직접 대입까지 막는 구조는 아님 |

### 관계를 읽는 방법

| 관계 종류 | 현재 프로젝트의 연결 | 읽는 방법 |
| --- | --- | --- |
| 요청 처리 흐름 | 라우터 → 응용 서비스 → 도메인 검사·레포지토리 → 응답 | 한 요청이 어떤 작업을 거치는지 나타냄 |
| 코드 의존 방향 | Auth의 표현 → 응용 → 도메인, 인프라 → 도메인 | 어떤 계층의 정의를 import하는지 나타냄. 위의 실행 순서와 다름 |
| 계약과 구현 | `TokenProvider` ← 구현하는 클래스: `JwtTokenProvider` | 인터페이스의 약속을 구체 클래스가 실제로 수행함 |
| 데이터 변환 | `PaymentModel` → `Payment.restore()` → `Payment` | DB 형태의 정보를 업무 규칙을 가진 객체로 바꿈 |

## 2. 4계층별 용어

### 2.1 Domain — 업무 정보와 규칙

주로 볼 파일: [Auth entities.py](domain/entities.py), [Auth repository.py](domain/repository.py), [Auth service.py](domain/service.py), [Payment entities.py](../payments/domain/entities.py)

| 용어 | 쉬운 뜻 | 프로젝트에서의 관계·예시 |
| --- | --- | --- |
| 도메인 객체(Domain Object) | 업무에서 다루는 정보나 규칙을 파이썬 객체로 표현한 것입니다.<br>DB 테이블이나 HTTP 요청 형식과 별도로 정의할 수 있습니다. | `Payment`, `TokenPayload`, `BlacklistToken` |
| 엔티티(Entity) | ID 등으로 다른 대상과 구분하면서 상태를 관리하는 객체입니다.<br>정보뿐 아니라 그 대상을 다루는 규칙도 담을 수 있습니다. | `Payment`는 결제 ID·상태를 가지며 `approve()`·`cancel()`로 상태 변경 |
| 업무 규칙 / 비즈니스 규칙 | 해당 서비스에서 반드시 지켜야 하는 조건입니다.<br>형식이 올바른 데이터라도 업무 규칙에는 맞지 않을 수 있습니다. | 요청 금액은 정수여도 예매의 실제 결제 금액과 다르면 승인 불가 |
| 상태(State) | 대상이 현재 어떤 단계에 있는지 나타내는 값입니다.<br>상태에 따라 가능한 작업이 달라집니다. | `PaymentStatus`: `READY`·`PAID`·`FAILED`·`CANCELED` |
| 상태 전이(State Transition) | 정해진 조건에 따라 상태가 바뀌는 것입니다.<br>허용하지 않는 변경은 거절해야 합니다. | `READY → PAID`, `PAID → CANCELED` / `FAILED → PAID`는 같은 결제 객체에서 거절 |
| 인터페이스(Interface) / 계약(Contract) | 어떤 기능을 제공해야 하는지 정한 약속입니다.<br>실제로 처리하는 방법은 구현체가 결정합니다. | `TokenProvider` → `create_access_token()`·`decode_token()` 약속 |
| 레포지토리 인터페이스 | 데이터를 저장하고 찾을 때 필요한 기능을 정한 약속입니다.<br>DB 종류나 SQL 작성 방법은 이 약속에 포함하지 않습니다. | `TokenBlacklistRepository` → `add()`·`find_by_jti()`·`is_blacklisted()` |
| 서비스 인터페이스 | 어떤 처리 기능을 제공해야 하는지 정한 서비스의 계약입니다.<br>현재 도메인의 service.py에는 이러한 계약을 정의했습니다. | `TokenProvider`는 토큰 처리, `TransactionManager`는 커밋·롤백의 계약 |
| 도메인 서비스(Domain Service) | 업무 규칙 중 특정 객체 하나에 두기 어려운 처리를 맡는 역할입니다.<br>파일 이름이 service.py라고 해서 모두 실제 도메인 서비스 구현인 것은 아닙니다. | 현재 `auth/domain/service.py`는 주로 인터페이스 정의. `AuthService`는 응용 서비스 |
| 복원(Reconstitution) | 저장된 정보로 객체의 기존 상태를 다시 만드는 것입니다.<br>조회할 때마다 새 객체의 초기 상태로 돌아가지 않도록 합니다. | `Payment.restore()`는 DB의 `PAID`·`FAILED`·`CANCELED` 상태를 유지하며 검증 |
| 정보 전달 객체 / DTO | 다른 코드에 필요한 정보를 묶어서 전달하는 객체입니다.<br>그 객체를 만들었다는 사실만으로 인증이나 DB 저장이 완료되는 것은 아닙니다. | 검증 결과인 `TokenPayload`, 결제 판단용 예매 정보인 `ReservationPaymentInfo` |

### 2.2 Application — 작업 순서와 저장 확정

주로 볼 파일: [AuthService](application/service.py), [PaymentService](../payments/application/service.py)

| 용어 | 쉬운 뜻 | 프로젝트에서의 관계·예시 |
| --- | --- | --- |
| 응용 서비스(Application Service) | 하나의 요청을 처리하기 위해 필요한 작업을 순서대로 연결합니다.<br>조회·규칙 검사·저장 등을 조율합니다. | `AuthService`, `PaymentService` |
| 유스케이스(Use Case) | 사용자가 시스템을 통해 이루려는 작업 하나입니다.<br>여러 객체의 처리가 모여 하나의 유스케이스를 완성할 수 있습니다. | 로그아웃하기, 결제하기, 본인 결제 조회하기 |
| 흐름 조율(Orchestration) | 필요한 객체를 호출하고 결과에 따라 다음 작업을 결정하는 것입니다.<br>각 객체가 가진 세부 규칙을 실행 순서로 연결합니다. | `PaymentService.pay()` → 예매 조회 → 조건 검사 → 결제 승인·실패 → 저장 |
| 트랜잭션(Transaction) | 여러 DB 작업을 하나의 처리 단위로 묶는 것입니다.<br>아직 확정되지 않은 작업을 함께 확정하거나 취소할 수 있습니다. | 로그아웃 시 액세스·리프레시 토큰 차단 기록 두 개를 함께 처리 |
| 커밋(Commit) | 트랜잭션의 변경을 DB에 최종 확정하는 것입니다.<br>현재 로그아웃은 커밋이 완료된 뒤 성공을 반환합니다. | `AuthService` → `TransactionManager.commit()` → DB 세션의 `commit()` |
| 롤백(Rollback) | 트랜잭션에서 아직 확정하지 않은 변경을 취소하는 것입니다.<br>이미 완료된 다른 트랜잭션이나 외부 작업까지 되돌리는 기능은 아닙니다. | 결제 DB 저장·커밋 오류 → `rollback()` 후 예외 전달 |

### 2.3 Infrastructure — DB와 외부 기술의 실제 구현

주로 볼 파일: [Auth 저장소 구현](infrastructure/repositories.py), [JWT 구현](infrastructure/security.py), [Payment 모델](../payments/infrastructure/models.py), [Payment 저장소 구현](../payments/infrastructure/repositories.py)

| 용어 | 쉬운 뜻 | 프로젝트에서의 관계·예시 |
| --- | --- | --- |
| 인프라(Infrastructure) | DB나 외부 시스템 같은 기술을 이용해 기능을 실제로 처리하는 영역입니다.<br>업무 규칙이 구체적인 기술에 묶이는 것을 줄이도록 분리합니다. | SQLAlchemy 저장·조회, PyJWT 발급·검증 |
| 구현체(Implementation) | 인터페이스의 약속을 실제 동작으로 만든 클래스입니다.<br>같은 약속을 지키면 다른 구현체로 바꿔 연결할 수 있습니다. | `TokenProvider`의 구현체 → `JwtTokenProvider` |
| ORM 모델 | 파이썬 클래스와 DB 테이블을 연결하는 정의입니다.<br>어떤 컬럼과 자료형으로 저장할지 표현합니다. | `PaymentModel` → `payments`, `TokenBlacklistModel` → `token_blacklist` |
| 레포지토리(Repository) / 저장소 | 데이터 저장·조회 작업을 모아 다른 코드에서 사용하게 하는 역할입니다.<br>인터페이스와 실제 DB 구현체를 구분해서 부르기도 합니다. | 계약: `TokenBlacklistRepository` / 구현: `SqlAlchemyTokenBlacklistRepository` |
| 매핑(Mapping) | 한 형태의 정보를 다른 형태에 맞춰 연결하거나 옮기는 것입니다.<br>DB 모델과 도메인 객체의 변환도 매핑에 해당합니다. | `PaymentRepository._to_domain()` → `PaymentModel`에서 `Payment`로 변환 |
| 세션(Session) / AsyncSession | SQLAlchemy에서 DB 조회·변경과 트랜잭션을 다루는 작업 창구입니다.<br>여기서 말하는 세션은 사용자의 로그인 세션과 다른 뜻입니다. | 레포지토리와 트랜잭션 구현체가 같은 DB 세션을 공유 |
| 플러시(Flush) | 변경 내용을 SQL로 DB에 보내는 작업입니다.<br>트랜잭션을 최종 확정하는 커밋과는 다릅니다. | 결제 `save()` → `flush()` → 아직 롤백 가능 |
| 리프레시(Refresh) | DB에서 현재 값을 다시 읽어 ORM 객체에 반영하는 작업입니다.<br>자동 생성된 값 등을 다시 확인할 때 사용합니다. | 결제 저장 후 `refresh()` → ID·생성 시각을 도메인 객체에 반영 |
| 어댑터(Adapter) | 다른 구성 요소의 정보를 필요한 형태로 바꿔 연결하는 역할입니다.<br>서로 다른 코드의 세부 구조가 직접 퍼지는 것을 줄입니다. | `ReservationPaymentRepository` → 예매 ORM을 결제용 정보로 변환 |

### 2.4 Presentation — HTTP 요청과 응답

주로 볼 파일: [Auth 라우터](presentation/routers/v1/router.py), [Auth 의존성](presentation/dependencies.py), [Payment 스키마](../payments/presentation/schemas.py), [Payment 라우터](../payments/presentation/router.py)

| 용어 | 쉬운 뜻 | 프로젝트에서의 관계·예시 |
| --- | --- | --- |
| 라우터(Router) | 요청 주소와 HTTP 메서드를 처리 함수에 연결합니다.<br>요청을 받은 함수는 서비스를 호출해 결과를 반환합니다. | `POST /payments` → `create_payment()` |
| 엔드포인트(Endpoint) | 클라이언트가 특정 작업을 요청하는 API의 접점입니다.<br>주소가 같아도 HTTP 메서드가 다르면 다른 작업일 수 있습니다. | `POST /payments`, `GET /payments/{payment_id}` |
| 요청(Request) / 응답(Response) | 요청은 클라이언트가 서버에 보내는 내용이고, 응답은 서버가 돌려주는 결과입니다.<br>둘의 데이터 형식은 따로 정할 수 있습니다. | 입력 `PaymentCreate` / 출력 `PaymentResponse` |
| 스키마(Schema) | 데이터의 모양과 허용 조건을 정한 규격입니다.<br>현재 표현 계층에서는 요청·응답 데이터 규격을 뜻합니다. | `PaymentCreate`, `TokenResponse` / DB 스키마와는 문맥이 다름 |
| 유효성 검증(Validation) | 값이 정해진 조건을 만족하는지 확인하는 것입니다.<br>입력 형식 검증과 업무 규칙 검증은 담당 위치가 다를 수 있습니다. | 스키마: 정수·0 이상 / 도메인: 실제 결제 금액과 일치 |
| 직렬화(Serialization) | 객체의 정보를 JSON처럼 전달할 수 있는 형태로 바꾸는 것입니다.<br>응답 스키마에 없는 내부 정보는 응답에서 제외할 수 있습니다. | `PaymentResponse`에는 `payment_log` 필드가 없음 |
| 경로 매개변수(Path Parameter) | 요청 주소의 일부로 전달하는 값입니다.<br>현재는 조회·취소할 결제 ID를 받는 데 사용합니다. | `/payments/{payment_id}`의 `payment_id` |
| HTTP 상태 코드 | 요청 처리 결과를 숫자로 알려주는 약속입니다.<br>상태 코드의 뜻과 업무 데이터의 상태를 함께 봐야 할 때도 있습니다. | 401 인증 실패, 403 권한 없음, 404 미존재, 422 입력 오류 |
| 예외 변환 | 코드에서 발생한 예외를 HTTP 상태와 메시지로 바꾸는 것입니다.<br>업무 코드가 HTTP 응답을 직접 만들지 않도록 경계에서 처리합니다. | `PermissionError` → 결제 라우터의 403 응답 |

### 2.5 계층을 연결하는 용어

주로 볼 파일: [Auth wiring.py](wiring.py), [Auth dependencies.py](presentation/dependencies.py)

| 용어 | 쉬운 뜻 | 프로젝트에서의 관계·예시 |
| --- | --- | --- |
| 의존성 주입(DI) | 필요한 객체를 사용하는 쪽에 외부에서 전달하는 방식입니다.<br>객체를 만드는 코드와 사용하는 코드를 분리할 수 있습니다. | `AuthService` 생성자에 저장소·토큰 발급기·트랜잭션 객체 전달 |
| 의존성 역전(DIP) | 핵심 코드가 구체 기술 대신 약속인 인터페이스에 의존하도록 하는 원칙입니다.<br>구체 구현체도 그 인터페이스를 따라 연결됩니다. | `AuthService`와 `JwtTokenProvider`가 모두 `TokenProvider` 계약을 기준으로 연결 |
| 객체 조립 / Wiring | 필요한 구현체를 만들고 서로 전달해 연결하는 작업입니다.<br>현재 Auth에서는 이 작업을 wiring.py에 모았습니다. | `build_auth_service()`가 저장소·토큰 발급기·트랜잭션을 연결 |
| 조립 지점(Composition Root) | 실제 객체의 생성과 연결을 맡는 위치입니다.<br>여러 계층의 구현을 알아야 하므로 일반 업무 코드와 분리합니다. | `auth/wiring.py`는 4계층 밖에서 구현체와 주입 명세를 함께 참조 |
| 주입 명세 / 플레이스홀더 | 나중에 실제 생성 함수를 연결할 자리입니다.<br>아직 연결하지 않은 상태에서 호출하면 오류를 내도록 만들 수 있습니다. | `provide_auth_service()`의 `NotImplementedError` |
| 바인딩(Binding) | 어떤 요청이나 이름을 실제 구현에 연결하는 것입니다.<br>현재는 서비스 주입 명세를 객체 생성 함수에 연결합니다. | `dependency_overrides[provide_auth_service] = create_auth_service` |

현재 Auth는 인터페이스·wiring 구조를 적용했습니다. Payments는 아직 응용 서비스가 구체 레포지토리와 AsyncSession을 참조하므로 두 도메인의 구조가 완전히 같지는 않습니다.

## 3. 파이썬 기본 문법

| 용어 | 쉬운 뜻 | 프로젝트에서의 관계·예시 |
| --- | --- | --- |
| 모듈(Module) / 패키지(Package) | 모듈은 코드를 나눈 단위이며 보통 .py 파일 하나입니다.<br>패키지는 여러 모듈을 묶어 관리하는 단위입니다. | `entities.py`는 모듈 / `auth.domain`은 패키지 |
| 클래스(Class) | 비슷한 객체가 가질 정보와 동작을 정의하는 틀입니다.<br>클래스로 실제 사용할 객체를 만들 수 있습니다. | `Payment` 클래스 → 결제 객체 생성 |
| 객체(Object) / 인스턴스(Instance) | 프로그램이 다루는 실제 값이나 대상입니다.<br>클래스로 만든 객체를 그 클래스의 인스턴스라고 부릅니다. | `payment = Payment(...)`의 `payment` |
| 속성(Attribute) | 객체가 가지고 있는 정보입니다.<br>메서드는 이 정보를 읽거나 바꿀 수 있습니다. | `payment.amount`, `payment.status` |
| 함수(Function) / 메서드(Method) | 함수는 특정 처리를 묶어 이름을 붙인 코드입니다.<br>클래스에 정의해 객체나 클래스와 연결된 함수는 메서드라고 부릅니다. | 함수 `utc_now()` / 메서드 `Payment.approve()` |
| 생성자 / 초기화 메서드 | 객체를 만들 때 필요한 정보를 받아 초기 상태를 설정하는 코드입니다.<br>파이썬에서는 보통 __init__을 초기화 메서드로 사용합니다. | `AuthService.__init__()`이 주입된 객체를 보관 |
| 타입 힌트(Type Hint) | 변수나 함수에 기대하는 자료형을 표시한 것입니다.<br>힌트만 붙였다고 실행 중 값이 자동으로 검증되는 것은 아닙니다. | `user_id: int` / 실제 검증은 별도 코드나 Pydantic이 수행 |
| 데코레이터(Decorator) | 함수나 클래스 위에 @로 붙여 기능을 적용하는 문법입니다.<br>무엇을 적용하는지는 데코레이터마다 다릅니다. | `@dataclass`, `@abstractmethod`, `@router.post()` |
| dataclass | 데이터를 담는 클래스에 초기화·출력 등의 기본 코드를 만들어 주는 기능입니다.<br>frozen=True이면 일반적인 속성 대입을 제한합니다. | `TokenPayload`, `BlacklistToken`, `Payment` / 결제 객체에는 frozen 미사용 |
| Enum / 열거형 | 사용할 값에 이름을 붙여 정해진 목록으로 표현하는 방식입니다.<br>문자열을 여러 곳에서 직접 입력하는 실수를 줄일 수 있습니다. | `PaymentStatus.PAID`의 값은 `"PAID"` |
| ABC / 추상 메서드 | ABC는 추상 인터페이스를 정의할 때 쓰는 기반 클래스입니다.<br>추상 메서드는 구체 클래스가 구현해야 할 기능을 표시합니다. | `TokenProvider(ABC)`와 `@abstractmethod` |
| async / await | async def는 비동기 함수를 정의하고, await는 비동기 작업의 결과를 기다립니다.<br>기다리는 동안 실행 환경이 다른 작업을 처리할 수 있지만 자동으로 백그라운드 작업이 되는 것은 아닙니다. | `await repository.add(...)` 다음에 `await transaction.commit()` |
| 예외(Exception) / raise | 정상 처리를 계속할 수 없는 상황을 알리는 방법입니다.<br>raise로 예외를 발생시키거나, 잡은 예외를 다시 전달할 수 있습니다. | `UnauthorizedException`, `ValueError`, `try/except` 뒤의 `raise` |

## 4. 사용 도구와 라이브러리

| 용어 | 쉬운 뜻 | 프로젝트에서의 관계·예시 |
| --- | --- | --- |
| FastAPI | HTTP 요청을 받아 파이썬 코드로 처리하는 웹 프레임워크입니다.<br>라우팅·입력 검증 연결·API 문서 생성 등을 지원합니다. | `APIRouter`, `Depends`, `HTTPException` |
| APIRouter | 관련 API 경로를 묶어 별도 파일에 정의하는 FastAPI 도구입니다.<br>실제 앱에 등록해야 해당 경로를 사용할 수 있습니다. | Auth의 `prefix="/v1/auth"`, 결제의 `prefix="/payments"` |
| Depends | 함수가 필요한 의존성을 FastAPI에 요청하는 표시입니다.<br>요청 처리 때 해당 의존성 함수를 평가해 값을 전달합니다. | `Depends(provide_auth_service)`, `Depends(get_current_token)` |
| Annotated | 타입에 추가 정보를 함께 붙이는 파이썬 표기입니다.<br>현재는 FastAPI에 주입이나 경로 검증 정보를 전달합니다. | `Annotated[int, Path(gt=0)]` |
| Pydantic | 데이터의 형태와 값을 검사하는 라이브러리입니다.<br>현재 요청·응답 스키마 작성에 사용합니다. | `BaseModel`, `Field`, `ConfigDict` |
| BaseModel / Field | BaseModel은 Pydantic 스키마를 만드는 기반 클래스입니다.<br>Field는 각 항목의 범위·설명 같은 조건을 지정합니다. | `PaymentCreate`의 `requested_amount = Field(strict=True, ge=0)` |
| SQLAlchemy | 파이썬에서 DB를 다루는 라이브러리입니다.<br>현재 ORM 모델·비동기 세션·조회와 저장에 사용합니다. | `Mapped`, `mapped_column`, `select`, `AsyncSession` |
| PostgreSQL / asyncpg | PostgreSQL은 데이터를 저장하는 DB 시스템입니다.<br>asyncpg는 파이썬에서 PostgreSQL에 비동기로 연결하는 드라이버입니다. | 공통 DATABASE_URL의 `postgresql+asyncpg` |
| PyJWT | 파이썬에서 JWT를 발급하고 검증하는 라이브러리입니다.<br>발급된 토큰을 자동으로 DB에 저장해 주는 기능은 아닙니다. | `JwtTokenProvider` 내부의 `jwt.encode()`·`jwt.decode()` |
| uv | 파이썬 실행 환경과 패키지를 관리하는 도구입니다.<br>현재 실행·의존성 관리·임시 테스트 환경에 사용합니다. | `uv run`, `uv sync`, `--no-project --with ...` |
| Ruff | 파이썬 코드의 문제를 검사하고 코드 모양을 정리하는 도구입니다.<br>검사와 포맷 정리는 서로 다른 작업입니다. | `ruff check` / `ruff format` |
| unittest / 모의 객체(Mock) | unittest는 파이썬 표준 테스트 도구입니다.<br>모의 객체는 실제 구성 요소 대신 제어 가능한 대역을 넣어 검사하게 합니다. | `AsyncMock`으로 DB 응답·오류·커밋 호출을 검사. 실제 DB 통합 테스트와는 다름 |

## 5. DB와 인증 관련 용어

### 5.1 DB

| 용어 | 쉬운 뜻 | 프로젝트에서의 관계·예시 |
| --- | --- | --- |
| 테이블·행·컬럼 | 테이블은 비슷한 데이터를 모은 표이고, 행은 기록 하나입니다.<br>컬럼은 각 기록이 가지는 항목입니다. | payments 테이블 / 결제 시도 한 행 / amount 컬럼 |
| 기본키(PK) | 테이블에서 각 행을 구분하는 기준입니다.<br>같은 기본키 값을 가진 행을 중복 저장할 수 없습니다. | 결제의 `id`, 블랙리스트의 `jti` |
| 외래키(FK) | 다른 테이블의 기록을 참조하는 연결 항목입니다.<br>서로 관계있는 데이터를 연결하고 잘못된 참조를 막는 데 사용합니다. | `payments.reservation_id` → `reservations.id` |
| 제약조건(Constraint) | DB가 데이터에 강제로 적용하는 규칙입니다.<br>파이썬 검증을 거치지 않은 저장도 이 규칙을 지켜야 합니다. | `amount >= 0`, 승인된 결제의 승인 시각·키 필수 |
| NULL / nullable | NULL은 DB에서 값이 없음을 나타냅니다.<br>nullable은 해당 컬럼에 NULL을 허용할지 정하는 설정입니다. | 승인 전의 `paid_at`은 NULL 가능 |
| JSONB | PostgreSQL에서 JSON 형태의 데이터를 저장하는 자료형입니다.<br>컬럼을 만들었다고 로그 기록 작업까지 자동으로 구현되는 것은 아닙니다. | `PaymentModel.payment_log` / 후처리 기록 기능은 아직 미구현 |
| 인덱스(Index) | 조건에 맞는 데이터를 찾는 데 도움을 주는 DB 구조입니다.<br>읽기를 빠르게 할 수 있지만 추가 저장 공간과 갱신 비용이 듭니다. | `payments.reservation_id`에 인덱스 정의 |
| 비관적 락 / 행 잠금 | 같은 데이터를 동시에 변경하지 않도록 DB 행을 잠그는 방식입니다.<br>경쟁하는 작업은 잠금이 풀릴 때까지 기다릴 수 있습니다. | `with_for_update()` → 같은 예매의 결제 요청을 순서대로 처리하도록 구성 |
| 경합 상태(Race Condition) | 여러 작업의 실행 순서에 따라 결과가 잘못될 수 있는 상황입니다.<br>값을 읽고 판단한 뒤 변경하는 사이에 다른 요청이 끼어들 수 있습니다. | 동시에 기존 승인 없음 확인 → 중복 승인 위험 / 예매 잠금으로 방어하는 구조 |
| 마이그레이션(Migration) | 기존 DB 구조의 변경 내용을 관리하고 적용하는 작업입니다.<br>파이썬 모델을 고치는 것만으로 기존 테이블이 자동 변경되지는 않습니다. | 모델의 컬럼 이름 수정과 실제 DB 컬럼 변경은 별개 |

### 5.2 인증과 인가

| 용어 | 쉬운 뜻 | 프로젝트에서의 관계·예시 |
| --- | --- | --- |
| 인증(Authentication) | 요청한 사람이 누구인지 확인하는 과정입니다.<br>현재 보호 API에서는 JWT 검증 결과로 회원 ID를 얻습니다. | `get_current_token()` → `AuthService.authenticate_token()` |
| 인가(Authorization) | 확인된 사용자가 해당 작업을 해도 되는지 판단하는 과정입니다.<br>인증에 성공해도 다른 사람의 정보에는 접근하지 못하게 할 수 있습니다. | 결제 서비스가 예매 소유자와 JWT의 회원 ID를 비교 |
| JWT | 서버가 서명한 정보를 문자열로 전달하는 토큰 형식입니다.<br>현재 토큰 내용은 암호화되지 않으므로 누구나 읽을 수 있다는 점을 고려해야 합니다. | `sub`, `jti`, `exp`, `iat`, `token_type` 포함 |
| 클레임(Claim) / 페이로드(Payload) | 클레임은 JWT에 담는 개별 정보이고, 페이로드는 그 정보들을 담는 부분입니다.<br>검증 후 필요한 정보를 TokenPayload 객체로 전달합니다. | 회원 ID인 `sub`, 만료 시각인 `exp` |
| 서명(Signature) / 비밀 키 | 서명은 토큰이 변조되지 않았는지 검사하는 데 사용하는 값입니다.<br>현재는 서버의 비밀 키로 HS256 서명을 만들고 검증합니다. | `JWT_SECRET_KEY`를 `JwtTokenProvider`에 전달 |
| 액세스 토큰(Access Token) | 보호된 API를 요청할 때 제시하는 토큰입니다.<br>현재 유효기간은 30분이며 서명·만료·종류·차단 여부를 검사합니다. | 결제 API의 Authorization 헤더에 전달 |
| 리프레시 토큰(Refresh Token) | 다시 로그인하지 않고 액세스 토큰을 새로 발급받는 데 쓰는 토큰입니다.<br>현재 유효기간은 7일이며 일반 결제 API의 인증 토큰으로는 거절합니다. | `POST /v1/auth/refresh`의 본문에 전달 |
| Bearer / Authorization 헤더 | Bearer는 토큰을 제시해 인증하는 HTTP 인증 방식입니다.<br>현재 Authorization 헤더에 Bearer와 토큰 문자열을 함께 보냅니다. | `Authorization: Bearer <access_token>` |
| jti | JWT 한 개를 구분하는 식별자입니다.<br>회원 ID가 같아도 토큰마다 다른 jti를 발급합니다. | `uuid4()`로 생성 → 블랙리스트 기본키로 저장 |
| exp / iat | exp는 토큰 만료 시각이고 iat는 발급 시각입니다.<br>현재 exp는 JWT에서 검사하고 TokenPayload에도 전달합니다. | JWT의 exp 유지 / DB의 만료 컬럼 추가는 별도 결정 |
| 블랙리스트(Blacklist) | 사용을 거절할 토큰 식별자를 모아 둔 목록입니다.<br>등록뿐 아니라 이후 인증 시 조회도 해야 차단이 작동합니다. | `token_blacklist` 테이블의 jti 조회 → 있으면 401 |
| 로그아웃(Logout) | 현재 토큰을 더 이상 사용하지 못하도록 처리하는 작업입니다.<br>현재는 전달된 액세스·리프레시 토큰 두 개의 차단 기록을 커밋합니다. | `POST /v1/auth/logout` / 모든 기기의 토큰 전체를 차단하는 기능은 아님 |
| OAuth2 | 인증 결과를 바탕으로 접근 권한을 위임하는 흐름을 정한 표준입니다.<br>JWT와는 별개이며 HTTPBearer 사용만으로 OAuth2 로그인 구현이 완료되는 것은 아닙니다. | 현재 Bearer 토큰 검사는 구현 / 로그인·비밀번호 검증은 아직 미구현 |

## 6. 헷갈리기 쉬운 용어 비교

| 비교할 용어 | 쉽게 구분하기 | 현재 코드에서 확인할 곳 |
| --- | --- | --- |
| domain 폴더 ↔ 업무 도메인 | domain 폴더는 규칙을 정의하는 계층입니다.<br>업무 도메인인 auth·payments는 각각 네 계층을 포함합니다. | `auth/domain`, `payments/domain` |
| 도메인 객체 ↔ ORM 모델 ↔ 요청·응답 스키마 | 도메인 객체는 업무 정보와 규칙, ORM 모델은 DB 저장 형태를 다룹니다.<br>스키마는 HTTP로 주고받을 데이터의 규격을 다룹니다. | `Payment` / `PaymentModel` / `PaymentCreate`·`PaymentResponse` |
| 인터페이스 ↔ 구현체 | 인터페이스는 제공할 기능의 약속입니다.<br>구현체는 그 약속을 실제 기술로 수행합니다. | `TokenProvider` / `JwtTokenProvider` |
| 도메인의 서비스 인터페이스 ↔ 응용 서비스 | 현재 도메인의 service.py는 기능 계약을 정의합니다.<br>응용의 service.py는 그 계약을 이용해 요청 처리 순서를 조율합니다. | `TokenProvider`·`TransactionManager` / `AuthService` |
| 입력 형식 검증 ↔ 업무 규칙 검증 | 입력 형식 검증은 정수·필수 여부 같은 조건을 확인합니다.<br>업무 규칙 검증은 실제 금액·상태에서 처리 가능한지 확인합니다. | `PaymentCreate` / `Payment.approve()` |
| flush ↔ commit | flush는 변경 SQL을 DB로 보냅니다.<br>commit은 트랜잭션을 최종 확정합니다. | 결제 레포지토리의 flush / 결제 서비스의 commit |
| DB refresh ↔ 토큰 refresh | DB refresh는 저장된 값을 다시 읽는 작업입니다.<br>토큰 refresh는 새 액세스 토큰을 발급받는 작업입니다. | `db.refresh(model)` / `refresh_access_token()` |
| 인증 ↔ 인가 | 인증은 누구인지 확인합니다.<br>인가는 그 사람이 해당 작업을 해도 되는지 확인합니다. | JWT 검사 / 본인 예매 여부 검사 |
| HTTP 401 ↔ 403 | 401은 유효한 인증 정보가 필요하다는 뜻입니다.<br>403은 확인된 사용자에게 해당 작업 권한이 없다는 뜻으로 사용합니다. | 차단된 토큰 → 401 / 다른 사람의 결제 → 403 |
| HTTP 201 ↔ 결제 PAID | 현재 201은 결제 시도 기록 생성 완료를 뜻합니다.<br>실제 승인 여부는 응답의 PAID·FAILED 상태를 확인해야 합니다. | `POST /payments` 응답 |
| 결제 상태 ↔ 예매 상태 | 결제 상태는 결제 시도와 승인 여부를 표현합니다.<br>예매 상태는 예매의 대기·확정·취소·만료 여부를 표현합니다. | 결제 `PAID` / 예매 `CONFIRMED`. 현재 두 상태의 확정 연동은 미완료 |
| 비동기 처리 ↔ 백그라운드 작업 | 비동기 코드는 기다리는 동안 다른 작업이 실행될 수 있게 합니다.<br>응답 이후로 일을 미루는 백그라운드 작업과 같은 뜻은 아닙니다. | 로그아웃 저장은 await로 완료를 기다림 / BackgroundTasks 미사용 |
| 코드의 모델 정의 ↔ 실제 DB 반영 | 모델 정의는 원하는 테이블 구조를 코드로 적은 것입니다.<br>실제 DB 생성·변경·통합 검증은 별도 작업입니다. | 현재 ORM·모의 테스트와 실제 PostgreSQL 연동을 구분 |

## 7. 팀원에게 설명할 때 쓸 수 있는 문장

| 설명하려는 내용 | 사용할 수 있는 문장 |
| --- | --- |
| 도메인 규칙의 위치 | “금액 일치 여부는 라우터가 아니라 Payment.approve()에서 검사합니다.” |
| 인터페이스와 구현체 | “AuthService는 TokenProvider 계약을 사용하고, 실제 JWT 처리는 JwtTokenProvider가 담당합니다.” |
| 객체 조립 | “auth/wiring.py에서 구현체를 만든 뒤 서비스에 주입합니다.” |
| 객체 변환 | “레포지토리가 ORM 모델을 Payment로 복원해서 반환합니다.” |
| 즉시 로그아웃 처리 | “두 토큰의 차단 기록을 같은 트랜잭션에서 커밋한 뒤 로그아웃 성공을 반환합니다.” |
| 본인 정보 보호 | “회원 ID는 요청 본문에서 받지 않고 검증된 JWT에서 가져와 예매 소유자와 비교합니다.” |
| 테스트 범위 | “현재 테스트는 실제 JWT와 모의 DB를 사용하므로 PostgreSQL 동시 요청 검증은 별도로 필요합니다.” |

## 8. 업데이트 방법과 기록

| 규칙 | 적용 방법 |
| --- | --- |
| 용어를 추가할 때 | 해당 계층·주제의 표에 행을 추가하고, 뜻은 최대 두 문장으로 작성합니다. |
| 관계를 설명할 때 | 같이 쓰이는 용어와 실제 클래스·메서드 이름을 마지막 열에 적습니다. |
| 여러 계층에서 쓰일 때 | 가장 관련 있는 표에 뜻을 두고, 다른 표나 비교표에서 관계를 설명합니다. |
| 구현이 바뀌었을 때 | 이름·파일 링크·예시·미구현 표시를 함께 갱신하고 최종 업데이트 날짜를 바꿉니다. |
| 모르는 용어가 생겼을 때 | 아래 추가 후보 표에 먼저 적고, 확인한 뒤 본문으로 옮깁니다. |
| 구현하지 않은 개념 | 미구현·학습 예정이라고 표시하고 현재 동작처럼 설명하지 않습니다. |

### 추가 후보

| 용어 | 궁금한 점 | 확인 후 넣을 위치 |
| --- | --- | --- |
| 예시: 커넥션 풀 | DB 연결을 재사용한다는 뜻과 세션의 차이는? | DB 관련 용어 |
| 예시: 멱등성 | 같은 요청을 반복해도 결과가 같다는 뜻을 어디까지 적용하는가? | 기본 용어·DB·API 비교 |

### 변경 기록

| 날짜 | 변경 내용 |
| --- | --- |
| 2026-11-04 | auth·payments 기준 초안 작성. 계층별 용어, 문법·도구, DB·인증, 비교표와 설명 문장 추가 |
