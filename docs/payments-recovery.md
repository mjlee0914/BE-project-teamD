# 결제·예매 연결과 실습 준비

## 로컬 준비

1. `docker compose up -d db`
2. `.env`에 JWT 설정과 같은 테스트 상점의 `TOSS_CLIENT_KEY`, `TOSS_SECRET_KEY`를 설정한다.
   클라이언트 키는 API 개별 연동 키(`test_ck_`), 시크릿 키는 해당 상점의 `test_sk_`를 사용한다.
3. `uv run python scripts/init_db.py`로 없는 테이블 이름을 확인한다.
4. 신규 로컬 DB라면 `uv run python scripts/init_db.py --create`로 현재 모델 테이블을 생성한다.
   이 명령은 기존 테이블의 컬럼을 변경하는 마이그레이션이 아니다.
5. 회원가입 및 축제·공연 데이터 준비 후 서버를 실행한다.
   `uv run uvicorn main:app --app-dir src --reload`

## Swagger에서 진행

1. 회원가입 → 로그인 → 액세스 토큰을 Authorize에 입력한다.
2. 예매 생성 → POST /v1/payments에 reservation_id를 보내 결제를 생성한다.
3. `/v1/payments/checkout` 페이지에 토큰과 결제 ID를 입력해 토스 결제창을 연다.
4. 가상계좌는 예매 응답의 deposit_due_at(예매 만료 5분 전)을 토스 dueDate에 전달한다.
   SDK 입력은 KST의 yyyy-MM-ddTHH:mm:ss 형식이다. 입금 기한이 지난 계좌는 발급하지 않는다.
5. 결제 인증 후 페이지가 서버 승인 API를 호출한다. 카드 DONE이면 예매 확정과 티켓 발급을 확인한다.
   가상계좌 발급은 WAITING_FOR_DEPOSIT이며 입금 웹훅이 DONE을 재조회한 뒤 확정한다.
6. POST /v1/payments/{id}/cancel은 예매·티켓 취소와 재고 복구를 먼저 확정하고 토스 취소를 처리한다.
   예매취소 API만 호출한 경우에는 30초 주기 작업이 남은 결제를 취소한다.

## 복구 상태

새 테이블이나 컬럼은 추가하지 않는다. 복구 상태·마감·취소 사유는 기존 payment_log 내부 메타데이터에 저장한다.

| recovery_status | 의미 |
|---|---|
| null | 별도 복구 대기 없음 |
| CONFIRMATION_PENDING | 결제 완료, 예매·티켓 확정 재시도 필요 |
| CANCELLATION_PENDING | 결제사 상태 재조회 및 취소 재시도 필요 |
| REFUND_ACCOUNT_REQUIRED | 입금된 가상계좌 환불을 위한 계좌 입력 필요 |

결제 상태 DONE은 실제 결제 완료를 뜻하며 환불 요청만으로 CANCELED로 바꾸지 않는다.
환불계좌가 필요하면 취소 API의 refund_account에 bank/account_number/holder_name을 입력한다.
계좌 원문은 저장하지 않으므로 통신 실패 뒤 계좌 입력이 다시 필요할 수 있다.

외부 승인 전에 IN_PROGRESS와 키를 checkpoint로 확정한다. 승인 성공 후 예매 확정이 실패해도
복구 작업이 키로 실제 결과를 조회할 수 있다. 확정 중 일부 티켓만 저장되면 savepoint가 이를 롤백한다.
예매를 확정할 수 없으면 재고를 복구하고 결제를 취소한다. 취소 의도도 외부 호출 전에 확정한다.
응답 유실 시 취소를 반복하기 전에 토스 현재 상태를 조회한다.

## 재현 가능한 검증

`RUN_PAYMENT_POSTGRES_TESTS=1`을 설정한 뒤 다음 테스트를 실행한다.

```powershell
$env:RUN_PAYMENT_POSTGRES_TESTS = '1'
uv run python -m unittest tests.test_payment_postgres tests.test_payment_workflow -v
Remove-Item Env:RUN_PAYMENT_POSTGRES_TESTS
```

테스트는 임시 PostgreSQL 스키마에서 실제 JWT·bcrypt·저장소·라우터를 사용한다.
토스 HTTP만 모의 처리하며 기존 DB 테이블·회원·예매를 수정하지 않는다.
카드·양일권·가상계좌·중복 요청·확정 실패·취소 응답 유실·만료 후 차단을 확인하고 스키마를 롤백한다.

실제 토스 결제창과 은행 입금은 유효한 테스트 키로 별도 확인해야 한다.

공식 문서: https://docs.tosspayments.com/sdk/v2/js/payment
