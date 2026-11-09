# 토스페이먼츠 HTTP 연동

현재 범위는 `httpx.AsyncClient`를 사용하는 승인·전액 취소 어댑터와 응용 서비스의 연결이다.
ORM 모델과 저장소도 구현했다. 결제 라우터, 웹훅, 결제창 연결은 아직 구현하지 않았다.

## 설정과 생성

로컬 `.env`에 개발자센터의 테스트 시크릿 키를 설정한다. 키를 코드나 문서에 넣지 않는다.

```dotenv
TOSS_SECRET_KEY=<개발자센터의 테스트 시크릿 키>
TOSS_TIMEOUT_SECONDS=15
```

```python
from payments.infrastructure.toss_service import TossPaymentProcessor

processor = TossPaymentProcessor.from_env()
```

기본적으로 호출마다 클라이언트를 열고 닫는다. 앱 수명 동안 클라이언트를 재사용하려면
`TossPaymentProcessor.from_env(client=client)`로 주입하고 앱 종료 때 호출자가 닫는다.

## 승인 흐름과 주문번호

1. 서버에서 `Payment.create()` 후 저장한다.
2. 생성된 `payment.order_id`와 서버에서 계산한 금액을 결제창에 전달한다.
3. 결제창의 인증 결과로 받은 paymentKey를 서버의 `PaymentService.approve()`에 전달한다.
4. 응용 서비스는 저장된 금액과 상태를 검사하고 저장된 order_id로 토스 승인을 요청한다.
5. 응답의 paymentKey·orderId·금액·상태·시각을 검증한 뒤 결과를 저장한다.

order_id는 결제 시도마다 생성하는 UUID 문자열이다. 하나의 예매에 여러 결제가 있으므로
reservation_id를 주문번호로 재사용하지 않는다. 클라이언트가 보낸 별도 주문번호로 덮어쓰지 않는다.

주문번호는 기존 payment_log JSONB의 첫 항목 `_payment_metadata.order_id`에 보관·복원한다.
추가 컬럼 없이 조회 시에도 같은 값을 사용한다.

## 결제 테이블과 저장소

- PostgreSQL에서 id는 BIGINT, 결제 로그는 JSONB, 시각은 TIMESTAMPTZ로 생성된다.
- reservation_id에는 UNIQUE를 두지 않아 예매별 여러 결제 시도를 허용한다.
- JSON 내부 주문번호는 유일 표현식 인덱스, payment_key는 UNIQUE로 보호한다. 미발급 payment_key는 NULL이다.
- status는 현재 토스 명칭인 DONE/ABORTED를 사용한다. 이전 PAID/FAILED 데이터는 별도 변환이 필요하다.
- method는 인증 전 NULL이며 승인 응답의 문자열(예: 가상계좌)을 저장한다.
- 도메인의 failed_reason은 ERD의 fail_reason 컬럼에 매핑한다.
- festival_name은 예매 스냅샷을 조회한다. payments에 중복 컬럼을 추가하지 않는다.
- 저장소는 새 결제 INSERT, 기존 결제 UPDATE, flush/refresh를 수행한다. commit은 호출자가 담당한다.
- 기존 결제의 reservation_id/order_id/amount를 변경하면 PaymentIdentityConflict가 발생한다.
- 주문번호·결제 키 중복 등 DB 제약조건 오류는 IntegrityError로 전달된다. 요청 세션에서 rollback해야 한다.

```python
from payments.infrastructure.sqlalchemy_repository import SQLAlchemyPaymentRepository

repository = SQLAlchemyPaymentRepository(session)
# PaymentService(processor, repository)로 연결한다.
```

### 테이블 적용

먼저 프로젝트 루트에서 DDL을 확인한다. 이 명령은 DB에 접속하지 않는다.

```powershell
$env:PYTHONPATH = 'src'
uv run python -m payments.infrastructure.schema
```

부모 테이블 reservations가 이미 생성된 개발 DB에 적용할 때만 다음을 실행한다.

```powershell
uv run python -m payments.infrastructure.schema --apply
```

이 명령은 payments 테이블과 인덱스만 생성한다. 기존 테이블을 삭제·변경하지 않으며,
payments가 이미 있으면 중단한다. 기존 테이블에 대한 ALTER/데이터 마이그레이션은 별도 작업이다.
애플리케이션 시작 시 자동으로 테이블을 생성하지 않는다.

입금 대기(WAITING_FOR_DEPOSIT)는 paid_at이 없는 상태로 보관한다. 실제 입금 이후의 결제 완료와
예매 확정·티켓 발급은 인증된 웹훅 또는 서버 재조회 흐름에서 별도로 구현해야 한다.

## 전액 취소

`PaymentService.cancel(payment_id, reason=..., refund_account=...)`로 호출한다.
현재 도메인은 DONE 결제의 전액 취소만 허용한다. 입금 전 취소·부분 취소는 아직 지원하지 않는다.

입금된 가상계좌의 환불 계좌는 다음 객체로 전달한다.

```python
from payments.domain.service import RefundAccount

account = RefundAccount(
    bank="088",
    account_number="환불받을 계좌번호(숫자만)",
    holder_name="예금주",
)
```

토스 응답이 CANCELED이고 취소 기록이 DONE인 경우에만 완료 시각을 반환한다.
이는 취소 승인 결과이며, 실제 환불 입금 완료까지 의미하지는 않는다.

## 오류·재처리

- 예상한 HTTP·통신·응답 오류는 PaymentProcessingError로 전달한다.
- code, http_status, outcome_unknown으로 오류의 종류를 구분한다.
- 타임아웃이나 응답 불일치에서는 결제가 이미 처리됐을 수 있다. 실패 상태로 단정하지 않는다.
- 같은 작업·본문은 같은 Idempotency-Key를 사용한다. 어댑터는 자동 재시도하지 않는다.
- 토스 성공 후 DB 저장이 실패하는 경우에 대비한 조회·복구, 중복 웹훅 처리, 동시성 제어는 후속 작업이다.
- 오류는 응용 서비스 밖으로 전달된다. 현재 get_db는 예외 발생 시 rollback하므로
  같은 트랜잭션에서 실패 기록을 저장한 뒤 예외를 던지면 그 기록도 rollback된다.
- 응답 원문의 secret·환불계좌·카드 정보를 payment_log에 저장하지 않는다.
  웹훅 검증용 secret은 향후 별도의 보호된 저장 방식이 필요하다.

## 검증

실제 토스 요청 없이 httpx.MockTransport로 요청과 응답을 검증한다.
저장소는 격리된 SQLite 메모리 DB와 비동기 세션 어댑터로 실제 SQL·제약조건·롤백을 검사하고,
PostgreSQL DDL도 별도로 컴파일해 확인한다. 운영 PostgreSQL/asyncpg 통합 테스트를 대체하지는 않는다.

```powershell
$env:PYTHONPATH = 'src'
uv run python -m unittest discover -s tests -v
uv run ruff check src/payments tests
```

## 공식 문서

- https://docs.tosspayments.com/reference
- https://docs.tosspayments.com/reference/using-api/authorization
- https://docs.tosspayments.com/guides/v2/cancel-payment
- https://www.python-httpx.org/async/
