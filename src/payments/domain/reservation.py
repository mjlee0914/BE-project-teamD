from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReservationPaymentInfo:
    """결제 판단에 필요한 예매 정보만 담은 읽기 전용 객체."""

    id: int
    user_id: int
    status: str
    final_price: int
    expires_at: datetime | None

    def ensure_owner(self, user_id: int) -> None:
        if type(user_id) is not int or user_id <= 0 or self.user_id != user_id:
            raise PermissionError("본인의 예매만 결제하거나 조회할 수 있습니다.")

    def ensure_payable(self, user_id: int, now: datetime) -> None:
        self.ensure_owner(user_id)
        if self.status != "PENDING":
            raise ValueError("결제 대기 중인 예매만 결제할 수 있습니다.")
        if now.utcoffset() is None:
            raise ValueError("시간대 정보가 포함된 현재 시각이 필요합니다.")
        if self.expires_at is None or self.expires_at.utcoffset() is None:
            raise ValueError("예매 만료 시각이 올바르지 않습니다.")
        if now >= self.expires_at:
            raise ValueError("결제 가능한 예매 시간이 만료되었습니다.")
        if type(self.final_price) is not int or self.final_price < 0:
            raise ValueError("예매의 최종 결제 금액이 올바르지 않습니다.")

    def ensure_canceled(self, user_id: int) -> None:
        self.ensure_owner(user_id)
        if self.status != "CANCELED":
            raise ValueError("예매 취소가 완료된 후에 결제를 취소할 수 있습니다.")
