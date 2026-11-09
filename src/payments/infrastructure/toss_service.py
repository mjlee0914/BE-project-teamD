# 파일 역할: PaymentProcessor를 httpx 비동기 HTTP 통신으로 구현한다. 토스 응답을 검사해 도메인 결과 객체로 변환한다.

import hashlib
import json
import math
import os
import re
from datetime import datetime
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

from payments.domain.entities import PaymentLog
from payments.domain.enums import PaymentStatus
from payments.domain.exceptions import PaymentProcessingError
from payments.domain.service import (
    PaymentApprovalResult,
    PaymentCancellationResult,
    PaymentProcessor,
    PaymentSnapshot,
    RefundAccount,
)


# 토스 전용 URL·인증·응답 형식을 다룬다. 엔티티 상태를 직접 바꾸지 않고 결과 객체를 반환한다.
class TossPaymentProcessor(PaymentProcessor):
    """토스 결제 승인·전액 취소 어댑터. 자동 재시도나 결제 상태 확정은 하지 않는다."""

    BASE_URL = "https://api.tosspayments.com/v1/payments"

    # 시크릿 키와 제한 시간을 검증하고 Basic 인증을 준비한다. 비동기 클라이언트는 외부에서 주입할 수도 있다.
    def __init__(
        self,
        secret_key: str,
        *,
        timeout: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ):
        if not secret_key or not secret_key.strip():
            raise ValueError("TOSS_SECRET_KEY가 필요합니다.")
        if timeout <= 0 or not math.isfinite(timeout):
            raise ValueError("토스 요청 제한 시간은 양수여야 합니다.")
        # 시크릿 키가 Basic 인증의 사용자명이고 비밀번호는 빈 문자열이다. 브라우저에 보내지 않는다.
        self._auth = httpx.BasicAuth(secret_key.strip(), "")
        self._timeout = timeout
        # 주입된 클라이언트의 종료는 호출자가 담당한다.
        self._client = client

    # 환경변수에서 시크릿 키·제한 시간을 읽어 어댑터를 생성한다. 키 값을 코드에 고정하지 않는다.
    @classmethod
    def from_env(
        cls, *, client: httpx.AsyncClient | None = None
    ) -> "TossPaymentProcessor":
        load_dotenv()
        return cls(
            os.getenv("TOSS_SECRET_KEY", ""),
            timeout=float(os.getenv("TOSS_TIMEOUT_SECONDS", "15")),
            client=client,
        )

    # POST /confirm으로 승인하고 응답의 결제 키·주문번호·금액·상태를 검사해 승인 결과로 변환한다.
    async def approve(
        self, payment_key: str, order_id: str, amount: int
    ) -> PaymentApprovalResult:
        self._validate_payment_key(payment_key)
        if not re.fullmatch(r"[A-Za-z0-9_=-]{6,64}", order_id):
            raise ValueError("order_id는 영문·숫자·_=-로 구성된 6~64자여야 합니다.")
        if type(amount) is not int or amount <= 0:
            raise ValueError("결제 금액은 양의 정수여야 합니다.")
        # 승인에는 결제창에서 받은 키와 서버가 보관한 주문번호·금액을 함께 전송한다.
        data = await self._post(
            "/confirm",
            {"paymentKey": payment_key, "orderId": order_id, "amount": amount},
        )
        if (
            data.get("paymentKey") != payment_key
            or data.get("orderId") != order_id
            or type(data.get("totalAmount")) is not int
            or data["totalAmount"] != amount
        ):
            raise self._invalid_response()
        try:
            status = PaymentStatus(data.get("status"))
        except ValueError:
            raise self._invalid_response() from None
        if status not in (PaymentStatus.DONE, PaymentStatus.WAITING_FOR_DEPOSIT):
            raise self._invalid_response()
        paid_at = (
            self._parse_time(data.get("approvedAt"))
            if status == PaymentStatus.DONE
            else None
        )
        method = data.get("method")
        if method is not None and not isinstance(method, str):
            raise self._invalid_response()
        secret_hash = self._secret_hash(data)
        # 가상계좌 발급은 입금 완료가 아니다. 후속 입금 알림을 검증할 secret도 필요하다.
        if status == PaymentStatus.WAITING_FOR_DEPOSIT and secret_hash is None:
            raise self._invalid_response()
        return PaymentApprovalResult(
            status, paid_at, self._payment_log(data), method, secret_hash
        )

    # 결제 키로 GET 조회하고 상태별 완료·취소 시각을 해석해 동기화용 결과를 반환한다.
    async def retrieve(self, payment_key: str) -> PaymentSnapshot:
        self._validate_payment_key(payment_key)
        data = await self._request("GET", f"/{quote(payment_key, safe='')}")
        if (
            data.get("paymentKey") != payment_key
            or not isinstance(data.get("orderId"), str)
            or not re.fullmatch(r"[A-Za-z0-9_=-]{6,64}", data["orderId"])
            or type(data.get("totalAmount")) is not int
            or data["totalAmount"] <= 0
        ):
            raise self._invalid_response()
        try:
            status = PaymentStatus(data.get("status"))
        except ValueError:
            raise self._invalid_response() from None
        method = data.get("method")
        if method is not None and not isinstance(method, str):
            raise self._invalid_response()
        paid_at = None
        if status == PaymentStatus.DONE or (
            status == PaymentStatus.CANCELED and data.get("approvedAt") is not None
        ):
            paid_at = self._parse_time(data.get("approvedAt"))
        cancelled_at = None
        if status == PaymentStatus.CANCELED:
            cancels = data.get("cancels")
            if not isinstance(cancels, list):
                raise self._invalid_response()
            completed = [
                item
                for item in cancels
                if isinstance(item, dict) and item.get("cancelStatus") == "DONE"
            ]
            if not completed:
                raise self._invalid_response()
            cancelled_at = max(
                self._parse_time(item.get("canceledAt")) for item in completed
            )
        return PaymentSnapshot(
            payment_key,
            data["orderId"],
            data["totalAmount"],
            status,
            paid_at,
            cancelled_at,
            self._payment_log(data),
            method,
            self._secret_hash(data),
        )

    # 웹훅 검증용 secret의 SHA-256 값만 만든다. 원문 secret을 일반 거래 이력에 저장하지 않는다.
    @classmethod
    def _secret_hash(cls, data: dict[str, object]) -> str | None:
        secret = data.get("secret")
        if secret is None:
            return None
        if not isinstance(secret, str) or not secret:
            raise cls._invalid_response()
        return hashlib.sha256(secret.encode()).hexdigest()

    # 환불 계좌를 필요 시 포함해 전액 취소한다. 취소 완료 상태와 잔액 0까지 확인한 뒤 결과를 반환한다.
    async def cancel(
        self,
        payment_key: str,
        *,
        reason: str = "고객 요청",
        refund_account: RefundAccount | None = None,
    ) -> PaymentCancellationResult:
        self._validate_payment_key(payment_key)
        if not reason.strip() or len(reason) > 200:
            raise ValueError("취소 사유는 1~200자여야 합니다.")
        body: dict[str, object] = {"cancelReason": reason}
        if refund_account is not None:
            if (
                not refund_account.bank.strip()
                or not re.fullmatch(r"[0-9]{1,20}", refund_account.account_number)
                or not refund_account.holder_name.strip()
                or len(refund_account.holder_name) > 60
            ):
                raise ValueError("환불 계좌 정보가 올바르지 않습니다.")
            body["refundReceiveAccount"] = {
                "bank": refund_account.bank,
                "accountNumber": refund_account.account_number,
                "holderName": refund_account.holder_name,
            }
        # cancelAmount를 지정하지 않는 전액 취소 요청이다. 부분 취소 기능은 제공하지 않는다.
        data = await self._post(f"/{quote(payment_key, safe='')}/cancel", body)
        if (
            data.get("paymentKey") != payment_key
            or data.get("status") != "CANCELED"
            or type(data.get("balanceAmount")) is not int
            or data["balanceAmount"] != 0
        ):
            raise self._invalid_response()
        cancels = data.get("cancels")
        if not isinstance(cancels, list) or not cancels:
            raise self._invalid_response()
        # 부분 취소·환불 대기 결과를 전액 취소 완료로 반영하지 않는다.
        completed = [
            item
            for item in cancels
            if isinstance(item, dict) and item.get("cancelStatus") == "DONE"
        ]
        if not completed:
            raise self._invalid_response()
        cancelled_at = max(
            self._parse_time(item.get("canceledAt")) for item in completed
        )
        return PaymentCancellationResult(cancelled_at, self._payment_log(data))

    # POST 작업도 공통 요청 메서드를 통하게 해 인증·멱등키·오류 변환 규칙을 일관되게 적용한다.
    async def _post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        return await self._request("POST", path, body)

    # HTTP 호출 → JSON 해석 → 성공 여부 확인 순서다. 통신 오류·결과 불명을 구분하며 자동 재시도하지 않는다.
    async def _request(
        self, method: str, path: str, body: dict[str, object] | None = None
    ) -> dict[str, object]:
        # 같은 작업·본문의 재요청은 같은 멱등키를 사용한다. 자동 재시도는 하지 않는다.
        material = path + json.dumps(body, sort_keys=True, ensure_ascii=True)
        headers = (
            {"Idempotency-Key": hashlib.sha256(material.encode()).hexdigest()}
            if method == "POST"
            else {}
        )
        try:
            if self._client is not None:
                response = await self._client.request(
                    method,
                    self.BASE_URL + path,
                    json=body,
                    auth=self._auth,
                    headers=headers,
                    timeout=self._timeout,
                    follow_redirects=False,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method,
                        self.BASE_URL + path,
                        json=body,
                        auth=self._auth,
                        headers=headers,
                        timeout=self._timeout,
                        follow_redirects=False,
                    )
        # 서버가 응답을 받지 못해도 토스는 처리했을 수 있다. 실패로 확정하지 않고 결과 불명으로 알린다.
        except httpx.RequestError:
            raise PaymentProcessingError(
                "토스 통신에 실패했습니다. 결제 결과를 조회한 뒤 재처리해야 합니다.",
                code="TOSS_NETWORK_ERROR",
                outcome_unknown=True,
            ) from None
        try:
            data = response.json()
        except ValueError:
            raise self._invalid_response(response.status_code) from None
        if not isinstance(data, dict):
            raise self._invalid_response(response.status_code)
        # 외부 오류 원문은 그대로 노출하지 않고 허용 형식의 코드와 결과 불명 여부만 전달한다.
        if not response.is_success:
            code = data.get("code")
            if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,100}", code):
                code = "TOSS_HTTP_ERROR"
            raise PaymentProcessingError(
                "토스가 결제 요청을 처리하지 못했습니다.",
                code=code,
                http_status=response.status_code,
                outcome_unknown=response.status_code >= 500
                or response.status_code in (408, 409, 429)
                or code in ("ALREADY_PROCESSED_PAYMENT", "ALREADY_CANCELED_PAYMENT"),
            )
        return data

    # 경로·승인 본문에 사용할 결제 키의 길이와 공백 없는 ASCII 형식을 검사한다.
    @staticmethod
    def _validate_payment_key(payment_key: str) -> None:
        if not 1 <= len(payment_key) <= 200 or any(
            ord(char) < 33 or ord(char) > 126 for char in payment_key
        ):
            raise ValueError(
                "payment_key는 공백 없는 ASCII 문자열이어야 합니다(최대 200자)."
            )

    # 해석 불가능한 응답은 결과 불명 오류로 바꾼다. 외부에서 처리됐을 수도 있으므로 재조회가 필요하다.
    @staticmethod
    def _invalid_response(http_status: int | None = None) -> PaymentProcessingError:
        return PaymentProcessingError(
            "토스 응답을 확인할 수 없습니다. 결제 결과를 재조회해야 합니다.",
            code="TOSS_INVALID_RESPONSE",
            http_status=http_status,
            outcome_unknown=True,
        )

    # ISO 형식 시각을 datetime으로 바꾼다. 시간대가 없는 값은 TIMESTAMPTZ 저장 기준에 맞지 않아 거절한다.
    @classmethod
    def _parse_time(cls, value: object) -> datetime:
        if not isinstance(value, str):
            raise cls._invalid_response()
        try:
            result = datetime.fromisoformat(value)
        except ValueError:
            raise cls._invalid_response() from None
        if result.tzinfo is None or result.utcoffset() is None:
            raise cls._invalid_response()
        return result

    # 필요한 거래 필드만 허용 목록으로 추린다. 웹훅 비밀값·카드 원문·환불 계좌는 이력에서 제외한다.
    @staticmethod
    def _payment_log(data: dict[str, object]) -> PaymentLog:
        # 응답 원문에는 웹훅 secret과 개인정보가 있어 필요한 거래 필드만 보관한다.
        keys = (
            "paymentKey",
            "orderId",
            "status",
            "totalAmount",
            "balanceAmount",
            "approvedAt",
        )
        log = {key: data[key] for key in keys if key in data}
        if isinstance(data.get("cancels"), list):
            cancel_keys = (
                "cancelAmount",
                "canceledAt",
                "cancelStatus",
                "transactionKey",
            )
            log["cancels"] = [
                {key: item[key] for key in cancel_keys if key in item}
                for item in data["cancels"]
                if isinstance(item, dict)
            ]
        return PaymentLog(log)
