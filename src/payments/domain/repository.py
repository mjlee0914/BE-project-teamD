# 파일 역할: 결제 저장소의 계약이다. 동일 예매의 작업 잠금과 결제 조회·저장을 정의하고 DB 구현과 분리한다.

from abc import ABC, abstractmethod
from datetime import datetime

from payments.domain.entities import Payment


# 서비스가 저장 기술에 의존하지 않도록 잠금·조회·저장의 메서드 모양만 정의한다.
class PaymentRepository(ABC):
    @abstractmethod
    async def find_recovery_candidates(
        self, now: datetime, limit: int = 100
    ) -> list[int]:
        """중단된 승인, 미확정 결제, 취소·만료 예매의 결제 ID를 조회한다."""

    # 같은 예매의 서로 다른 결제 시도도 동시에 진행되지 않게 요청 트랜잭션 동안 잠그는 계약이다.
    @abstractmethod
    async def lock_reservation(self, reservation_id: int) -> None:
        """동일 예매의 결제 작업을 요청 트랜잭션 안에서 직렬화한다."""

    # 토스 주문번호로 결제를 찾는다. 웹훅처럼 내부 결제 ID를 모르는 요청에서 사용한다.
    @abstractmethod
    async def find_by_order_id(self, order_id: str) -> Payment | None: ...

    # 내부 결제 ID로 한 건을 읽고, 없으면 None을 돌려준다.
    @abstractmethod
    async def find_by_id(self, payment_id: int) -> Payment | None: ...

    # 예매 하나에 연결된 모든 결제 시도를 반환한다. 중복 결제 검사와 목록 조회에 사용한다.
    @abstractmethod
    async def find_by_reservation_id(self, reservation_id: int) -> list[Payment]: ...

    # 신규 저장과 기존 상태 갱신을 맡는다. DB가 채운 ID·시각을 포함한 객체를 반환하도록 정의한다.
    @abstractmethod
    async def save(self, payment: Payment) -> Payment: ...
