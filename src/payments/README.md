# 결제 API 연결 준비

## 모델 공통 규칙

- 상태 컬럼은 PaymentStatus와 SQLEnum(native_enum=False, create_constraint=True)으로 정의한다.
  허용 상태의 CHECK 제약은 Enum에서 생성하며 별도의 문자열 목록을 관리하지 않는다.
- 생성·수정 시각은 공통 DateTimeMixin을 사용한다. 새 결제의 updated_at은 NULL이고 변경 시 시각을 기록한다.
  도메인과 API 응답도 updated_at의 null을 허용한다.
- 이 모델 수정만으로 기존 DB 테이블이 변경되지는 않는다. 이미 생성된 payments 테이블은
  상태 컬럼 타입·CHECK 및 updated_at의 NULL 허용·기본값 변경을 별도 마이그레이션으로 반영해야 한다.
- 취소 시각은 팀 명칭인 canceled_at으로 통일한다. 도메인·DB 컬럼·API 응답 모두 같은 이름을 사용한다.
  기존 DB 컬럼의 이름 변경과 API를 사용하는 클라이언트의 필드명 변경은 별도로 반영해야 한다.

## API 목록

`presentation/routers/v1/router.py`에는 다음 API가 준비되어 있다.

| 메서드 | 경로 | 기능 |
| --- | --- | --- |
| GET | /v1/payments?reservation_id=... | 본인 예매의 결제 시도 목록 |
| GET | /v1/payments/{payment_id} | 본인 결제 조회 |
| POST | /v1/payments | 본인 PENDING 예매 기반 결제 생성 |
| POST | /v1/payments/{payment_id}/approve | 결제 승인 |
| POST | /v1/payments/{payment_id}/cancel | 결제 전액 취소 |
| POST | /v1/payments/{payment_id}/reconcile | 본인 결제의 결제사 결과 재조회·복구 |

결제 생성 요청은 `reservation_id`만 받는다. 서버가 예매 소유자, 상태, 만료 시각과 금액을 확인해 READY 결제를 만든다. 유효한 READY 결제가 이미 있으면 같은 결제를 반환해 결제창 재시도를 지원한다. 생성 후 클라이언트 결제창에서 받은 `paymentKey`와 금액으로 승인 API를 호출한다. 승인 API는 승인 시점에도 예매가 PENDING이고 만료되지 않았는지 확인한 뒤 Toss 승인 요청을 수행한다.

최종 결제 금액이 0원인 예매는 결제 시도를 만들지 않는다. 무료 예매의 확정 처리는 예약 모듈의 별도 흐름에서 다뤄야 한다.

승인 본문:

```json
{"payment_key": "결제창 인증 후 받은 키", "amount": 1000}
```

취소 본문(입금된 가상계좌는 refund_account 필요):

```json
{
  "reason": "고객 요청",
  "refund_account": {
    "bank": "088",
    "account_number": "1234567890",
    "holder_name": "예금주"
  }
}
```

## 앱 연결 시 필요한 작업

현재 라우터는 main.py에 등록하지 않았다. 다른 모듈·공통 파일 수정 전 확인을 받기 위한 상태다.

1. main.py에서 결제 라우터를 include_router로 등록한다.
2. wiring에서 presentation/dependencies.py의 세 공급 함수를 실제 구현체로 바인딩한다.
   - auth.presentation.dependencies.provide_auth_service: 실제 JWT·블랙리스트를 검증하는 AuthService
   - provide_payment_service: PaymentService(TossPaymentProcessor, SQLAlchemyPaymentRepository)
   - provide_payment_access_checker: SQLAlchemyPaymentAccessChecker
3. 저장소와 소유자 검사는 같은 요청의 AsyncSession을 사용한다.

결제의 현재 사용자 확인은 auth.presentation.dependencies.get_current_user를 재사용한다.
payments의 provide_auth_service는 auth의 동일 함수를 재노출하므로 한 번의 의존성 바인딩을 공유한다.
auth 구현체의 앱 연결 전에는 임의로 토큰을 신뢰하거나 검사를 우회하지 않는다.
미연결 공급 함수는 503으로 차단한다. 인증 토큰이 없으면 401이다.
모든 조회·승인·취소에서 예매의 user_id와 검증된 TokenPayload.user_id를 비교한다.

토스 통신 오류는 502와 outcome_unknown 정보로 전달하며 원문 오류·결제 로그·환불 계좌를 응답하지 않는다.
공통 SharedException·요청 검증 예외 처리는 기존 앱의 전역 핸들러를 사용한다.

## 가상계좌 입금 웹훅과 재조회

`presentation/routers/v1/webhook_router.py`는 `POST /v1/payments/webhooks/deposit`를 제공한다.
앱에는 등록되어 있다. 실제 입금 알림을 받으려면 토스 개발자센터에도 웹훅 URL을 등록해야 한다.
별도 라우터로 관리해 일반 결제 경로와 분리했다.

토스 DEPOSIT_CALLBACK 본문은 최상위 orderId, secret, transactionKey, status를 사용한다.
PAYMENT_STATUS_CHANGED의 data 객체나 일반 사용자 JWT로 대신 검증하지 않는다.

처리 순서:

1. orderId로 저장된 결제를 조회한다.
2. 승인 응답의 secret을 SHA-256으로 저장한 값과 웹훅 secret의 해시를 상수 시간으로 비교한다.
3. transactionKey와 status 조합이 이미 처리됐으면 상태·로그를 다시 변경하지 않는다.
4. 저장된 payment_key로 토스 GET 조회를 수행해 최신 주문번호·금액·상태를 확인한다.
5. 확인한 상태와 처리 이벤트를 같은 결제 행에 저장한다. 수신 본문의 상태로 직접 덮어쓰지 않는다.

검증 실패는 403, 재조회 실패는 503이다. 성공·중복 알림은 204이며 응답 본문이 없다.
**향후 wiring에서는 DB commit 성공 후에 204가 전송되도록 요청 트랜잭션 종료 순서를 보장해야 한다.**
저장소는 flush만 하므로 서비스 반환만으로 commit이 완료된 것은 아니다.

가상계좌는 입금 오류로 DONE → WAITING_FOR_DEPOSIT 전환이 일어날 수 있어 paid_at을 비운다.
예매·티켓의 확정 취소나 재처리는 여기서 하지 않으며 해당 모듈과 정책 합의가 필요하다.

승인 응답 유실 시 `PaymentService.reconcile(payment_id, payment_key)`로 서버 조회 결과를
반영할 수 있다. 금액과 주문번호가 맞지 않으면 저장하지 않는다. 소유자 검사가 포함된
POST /v1/payments/{payment_id}/reconcile API도 준비했다. 본문은 저장된 키를 쓰면 {},
응답 유실로 키가 저장되지 않았으면 {"payment_key": "인증 결과의 키"}다.
미승인·없는 결제를 임의로 승인하는 기능은 아니다.

웹훅 검증값 원문은 로그·엔티티 repr·API 응답에 포함하지 않는다.
비밀값 해시와 처리 이벤트도 일반 결제 응답에서는 제외한다.

### ERD를 유지하는 저장 방식

추가 DB 컬럼은 없다. 주문번호, 검증값 해시, 처리한 이벤트 목록은 기존 payment_log JSONB의
첫 항목 `_payment_metadata` 안에 저장한다. 그 뒤 항목은 결제 처리 로그다.
이 메타데이터는 일반 로그·API 응답에 노출하지 않는다. 주문번호는 JSON 표현식 유일 인덱스로 보호한다.
이는 JSON 내부 구조에 대한 규칙이며 ERD 테이블·컬럼은 늘리지 않는다.

DB 버전 컬럼 대신 조회한 행의 상태 지문을 메모리에 보관하고, 저장 시 SELECT FOR UPDATE로
최신 행을 읽어 비교한다. 충돌은 409이며 요청 트랜잭션을 rollback한 뒤 재조회해야 한다.
서비스의 승인·취소는 먼저 예매 행을 잠가 동일 예매의 결제 작업을 직렬화한다.
다른 결제 시도가 IN_PROGRESS/WAITING_FOR_DEPOSIT/DONE이면 새 승인을 거절한다.
다른 진입점에서 어댑터만 직접 호출하면 이 보호를 받을 수 없다.
웹훅과 승인 저장이 겹친 경우 토스의 재전송 또는 운영 재조회로 복구해야 한다.

승인 요청 전 IN_PROGRESS와 결제 키를 저장한다. 예상한 결제 연동 실패를 API가 502로
반환할 때도 요청 트랜잭션을 commit해야 재조회용 키가 보존된다. 호출자가 예외 때문에
전체 트랜잭션을 rollback하거나 프로세스가 중단되면 이 기록도 취소되므로,
토스 결과 조회에 의한 운영 복구가 필요하다. 예외 발생 시 DB가 스스로 commit하지는 않는다.

동일 키·금액의 이미 승인된 요청과 이미 완료된 취소 요청은 기존 결과를 반환한다.
입금 전 가상계좌는 환불 계좌 없이 전액 취소하며, 입금된 가상계좌에는 환불 계좌가 필요하다.

공식 규격:
- https://docs.tosspayments.com/reference/using-api/webhook-events
- https://docs.tosspayments.com/reference

## 내부 구현 완료 기준

- [x] 양의 정수 금액 검증, 결제 상태 전이, 입금 대기/완료 구분
- [x] 승인·취소·재조회·입금 웹훅 처리와 사용자별 접근 검사
- [x] 같은 예매의 다른 진행 중/완료 결제 차단과 반복 요청의 결과 재사용
- [x] HTTP 인증·타임아웃·멱등키·응답 식별자/금액 검증
- [x] 원본 비밀값·결제 로그의 API 응답 노출 방지
- [x] ERD 12개 컬럼 유지 및 JSONB 메타데이터 저장
- [x] PostgreSQL/asyncpg에서 저장·조회·수정·중복·상태 충돌·웹훅 흐름 검증
- [x] 테스트 종료 후 격리 스키마·테이블·데이터 롤백 검증

PostgreSQL 검증 실행(기본 실행에서는 생략):

```powershell
$env:PYTHONPATH = 'src'
$env:RUN_PAYMENT_POSTGRES_TESTS = '1'
uv run python -m unittest discover -s tests -v
Remove-Item Env:RUN_PAYMENT_POSTGRES_TESTS
```

PAYMENTS_TEST_DATABASE_URL이 있으면 그 DB를 사용하고, 없으면 로컬 .env의 DATABASE_URL을 사용한다.
테스트마다 임시 스키마를 트랜잭션 안에서 생성하고 마지막에 rollback한다. public 테이블은 수정하지 않는다.

## 통합·운영 단계에 남은 작업

- 개발·운영 환경에 실제 테이블 적용
- 인증 서비스 구현·의존성 연결
- 예매 만료·취소 기한·상태와 결제 작업의 연동
- 토스 성공 후 DB 실패의 자동 복구 작업·모니터링, 프로세스 중단 후 재처리
- 실제 토스 테스트 결제와 웹훅 검증
- 웹훅 실제 등록·통합 검증 및 예매 확정·티켓 발급 연결

현재 API는 결제 객체의 금액·상태와 소유자를 검사하지만 예매의 전체 운영 정책까지 검증하지 않는다.
실서비스 공개 전 위 항목을 완료해야 한다. 외부 토스 결제는 테스트에서 실행하지 않는다.
