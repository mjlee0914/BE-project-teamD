"""
Performance 규칙

[기본 정보]
1. 공연은 반드시 하나의 축제(festival_id)에 소속되어야 한다.
2. 공연 제목은 1자 이상 50자 이하로 구성되어야 한다.
   (같은 축제 안 제목 중복 금지는 규칙 20 참고)

[일정]
3. 공연 시작 시각은 종료 시각보다 반드시 빨라야 한다.
   (starts_at < ends_at, 같으면 허용하지 않는다)
4. 예매 시작 시각은 예매 종료 시각보다 빨라야 하고,
   예매 종료 시각은 공연 시작 시각보다 늦을 수 없다.
   (booking_open_at < booking_close_at <= starts_at)
5. 취소 마감 시각은 공연 시작 24시간 전으로 서버가 자동 계산한다. (클라이언트 입력 없음)
   계산된 값은 예매 시작 이후여야 한다.
   (booking_open_at <= cancel_deadline_at <= starts_at)
   일정 수정으로 공연 시작이 바뀌면 다시 계산한다.
6. 공연 일정은 소속 축제 기간 안에 있어야 한다.
   - 축제 기간은 Festival 객체가 아닌 starts_on, ends_on(date)으로 전달받는다.
     (performances 도메인이 festivals 도메인을 import하지 않기 위함)
   - 공연 시각은 KST 기준 날짜로 변환하여 비교한다.
     축제 starts_on <= 공연 시작일, 공연 종료일 <= 축제 ends_on

[수량·가격]
7. 수용 인원(capacity)은 1명 이상이어야 한다.
8. 잔여 수량(remaining_count)은 0 이상, 수용 인원 이하여야 한다.
9. (삭제) 1인당 최대 수량은 모든 공연 2매 고정이며 reservations의 MAX_QUANTITY_PER_RESERVATION에서 검사한다.
10. 가격(price)은 0원보다 커야 한다. 무료 공연은 허용하지 않는다.
    (reservations의 total_price > 0 규칙 기준)

[생성]
11. 신규 공연 생성 시 잔여 수량은 수용 인원과 같다. (remaining_count = capacity)
    잔여 수량은 클라이언트가 직접 정할 수 없다.
12. 신규 공연의 상태는 SCHEDULED로 시작한다.

[상태]
13. 공연 상태는 status 값으로 저장하며 아래 중 하나이다.
    - SCHEDULED : 예매 시작 전
    - OPEN      : 예매 가능
    - SOLD_OUT  : 잔여 수량 0
    - CANCELED  : 취소됨
    - COMPLETED : 공연 종료
    상태 전이는 아래 경로만 허용하며, 그 외에는 InvalidPerformanceStatus(409)를 던진다.
    - 오픈(open)     : SCHEDULED → OPEN                  (관리자 API)
    - 매진           : OPEN → SOLD_OUT                    (규칙 19, 잔여 수량 0이 될 때 자동)
    - 매진 해제      : SOLD_OUT → OPEN                    (규칙 19, 예매 취소로 재고 복구 시 자동)
    - 종료(complete) : OPEN, SOLD_OUT → COMPLETED         (관리자 API)
    - 취소(cancel)   : CANCELED, COMPLETED 외 → CANCELED (규칙 14/15)
    (시간 경과에 따른 자동 전이(예: 예매 마감, 공연 종료)는 아직 정의하지 않는다)

[취소]
14. 공연 취소 시 상태를 CANCELED로 변경한다.
    별도의 canceled_at 컬럼 없이 상태값으로만 관리한다.
15. 이미 취소된 공연은 다시 취소할 수 없다. (409)
    이미 종료된 공연(현재 시각 >= ends_at)은 취소할 수 없다. (409)

[수정]
16. 일정 수정(PATCH) 시 전달되지 않은 값은 기존 값으로 채운 뒤,
    합쳐진 결과로 규칙 3~6을 다시 검증한다.
17. 취소(CANCELED)되었거나 종료(COMPLETED)된 공연은 일정을 수정할 수 없다. (409)

[예매]
18. 공연은 아래 조건을 모두 만족할 때만 예매 가능하다. (is_bookable)
    - 상태가 OPEN이다.
    - 잔여 수량이 1 이상이다.
    - 현재 시각이 예매 기간 안이다. (booking_open_at <= now < booking_close_at)
    현재 시각은 인자로 전달받는다. (테스트에서 시각을 고정하기 위함)
19. 예매 시 잔여 수량을 차감하고, 예매 취소 시 복구한다.
    - 차감 결과가 0이면 SOLD_OUT으로 바꾼다.
    - SOLD_OUT 상태에서 복구되면 OPEN으로 되돌린다.
    - 잔여 수량은 0 미만이 되거나 수용 인원을 넘을 수 없다. (규칙 8)

[제목 중복]
20. 같은 축제 안에서는 공연 제목이 중복될 수 없다. (409)
    다른 축제의 공연과는 제목이 같아도 된다.
    ex) A 축제 "1회차", B 축제 "1회차" → 허용
        A 축제 안에 "1회차" 두 개 → 불가
    엔티티 혼자서는 다른 공연을 알 수 없으므로 __post_init__에서 검사하지 않는다.
    → service가 repository.exists_duplicated_title()로 확인 후 PerformanceTitleDuplicated를 던진다.
    (DB의 uq_performances_festival_title 제약이 마지막 안전장치)
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from performances.domain.enums import PerformanceStatus
from performances.domain.exceptions import (
    InvalidPerformanceCapacity,
    InvalidPerformancePrice,
    InvalidPerformanceStatus,
    InvalidPerformanceTime,
    InvalidPerformanceTitle,
)
from shared.core.time import (
    KST,  # 규칙 6에서 공연 시각을 KST 기준 날짜로 변환하여 비교할 때 사용
)

CANCEL_DEADLINE_BEFORE_START = timedelta(hours=24)

@dataclass
class Performance:
    # 생성시 직접 넣어야 하는 필수값
    festival_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    booking_open_at: datetime
    booking_close_at: datetime
    capacity: int
    price: int

    # 기본값이 있는 필드
    id: int | None = None
    remaining_count: int | None = None
    version: int | None = None
    cancel_deadline_at: datetime | None = None
    # 신규 공연의 상태는 SCHEDULED로 시작한다.
    status: PerformanceStatus = PerformanceStatus.SCHEDULED
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.cancel_deadline_at is None:
            self.cancel_deadline_at = self.starts_at - CANCEL_DEADLINE_BEFORE_START

        # 규칙 3~5
        self._validate_schedule(
        self.starts_at, self.ends_at,
        self.booking_open_at, self.booking_close_at,
        self.cancel_deadline_at,
        )

        # 규칙 2
        self.title=self.title.strip()
        if not (1 <= len(self.title) <= 50):
            raise InvalidPerformanceTitle("공연 제목은 1자 이상 50자 이하여야 합니다.")

        # 규칙 7
        if self.capacity <= 0:
            raise InvalidPerformanceCapacity("수용 인원은 1명 이상이어야 합니다.")

        # 규칙 11: 새로 만들 때는 잔여 수량 = 수용 인원
        # 새 공연을 만들 때 remaining_count가 capacity로 채워진다.
        if self.remaining_count is None:
            self.remaining_count = self.capacity

        # 규칙 8 잔여 수량(remaining_count)은 0 이상, 수용 인원 이하여야 한다
        if not (0 <= self.remaining_count <= self.capacity):
            raise InvalidPerformanceCapacity("잔여 수량은 0 이상, 수용 인원 이하여야 합니다.")

        # 규칙 10
        if not self.price > 0:
            raise InvalidPerformancePrice("가격은 0원보다 커야 합니다.")

    @staticmethod
    def _validate_schedule(
        starts_at: datetime, 
        ends_at: datetime, 
        booking_open_at: datetime, 
        booking_close_at: datetime,
        cancel_deadline_at: datetime
        ) -> None:
        # 규칙 3
        if starts_at >= ends_at:  
            raise InvalidPerformanceTime("공연 시작 시간은 종료 시간보다 빨라야 합니다.")
        # 규칙 4
        if not (booking_open_at < booking_close_at <= starts_at):
            raise InvalidPerformanceTime("예매 기간이 올바르지 않습니다. 예매는 공연 시작 전에 끝나야 합니다.")
        # 규칙 5
        if not (booking_open_at <= cancel_deadline_at <= starts_at):
            raise InvalidPerformanceTime("예매 시작 시각은 공연 시작 24시간 전보다 빨라야 합니다.")

    # 규칙 6
    @staticmethod
    def _validate_within_festival(
            festival_starts_on:date, 
            festival_ends_on: date,
            starts_at: datetime,
            ends_at: datetime,
            ) -> None:
        # 공연 시각을 한국 달력 날짜로 바꿔서 축제 날짜와 같은 기준으로 맞춘다.
        # festival date: 시간대가 없음 -> 한국 날짜로 읽기로 약속
        # performance datetime: 시간대가 있음 -> 한국 날짜로 변환해야 함.
        # ex)
        # 변환 전 starts_at -> 2026-11-05 16:00 UTC
        # 변환 후:
        # astimezone(KST) -> 2026-11-06 01:00 KST
        # astimezone(KST).date() -> 2026-11-06
        KST_starts_at = starts_at.astimezone(KST).date()
        KST_ends_at = ends_at.astimezone(KST).date()
        if not (festival_starts_on <= KST_starts_at and KST_ends_at <= festival_ends_on):
            raise InvalidPerformanceTime("공연 일정은 축제 기간 안에 있어야 합니다.")

    @classmethod
    def create(
        cls,
        festival_id: int,
        title: str,
        starts_at: datetime,
        ends_at: datetime, 
        booking_open_at: datetime,
        booking_close_at: datetime,
        capacity: int,
        price: int,
        festival_starts_on: date,
        festival_ends_on: date,                
        ) -> "Performance": # 줄을 읽는 시점에 Performance객체가 아직 다 안만들어짐 -> 따옴표로 감싸서 글자 그대로 우선 저장.
        performance = cls(
            festival_id=festival_id,
            title=title,
            starts_at=starts_at,
            ends_at=ends_at,
            booking_open_at=booking_open_at,
            booking_close_at=booking_close_at,
            capacity=capacity,
            price=price,
        )      
        performance._validate_within_festival(festival_starts_on=festival_starts_on, festival_ends_on=festival_ends_on, starts_at=starts_at, ends_at=ends_at)
        
        return performance
    
    # 규칙 13 : SCHEDULED → OPEN
    def open(self) -> None:
        if self.status == PerformanceStatus.SCHEDULED:
            self.status = PerformanceStatus.OPEN
        else: 
            raise InvalidPerformanceStatus("예매 시작 전 공연만 오픈할 수 있습니다.")

    # 규칙 13 : OPEN, SOLD_OUT → COMPLETED
    # 공연 종료 시간이 지난 공연만 COMPLETED (현재 시각이 ends_at 전이면 409) -> 현재 시간으로 시간 검사 필요
    # now를 인자로 밖에서 받기 : test할때 시간 바꾸기 가능
    def complete(self, now: datetime) -> None:
        if self.status not in (PerformanceStatus.OPEN, PerformanceStatus.SOLD_OUT):
            raise InvalidPerformanceStatus("예매가 열렸거나 매진된 공연만 종료할 수 있습니다.")
        if now < self.ends_at:
            raise InvalidPerformanceStatus("아직 공연이 끝나지 않았습니다. 공연 종료 시간이 지난 뒤에 종료해 주세요.")
        self.status = PerformanceStatus.COMPLETED

    # 규칙 14/15 : 공연 취소 시 상태값 CANCELED로 변경
    def cancel(self) -> None:
        if self.status == PerformanceStatus.CANCELED:
            raise InvalidPerformanceStatus("이미 취소된 공연입니다.")
        if self.status == PerformanceStatus.COMPLETED:
            raise InvalidPerformanceStatus("이미 종료된 공연입니다.")

        self.status = PerformanceStatus.CANCELED

    # 공연 날짜 수정(공연시작/종료시간, 예약오픈/마감시간, 취소데드라인)
    def change_schedule(self,
                        festival_starts_on: date,
                        festival_ends_on: date,
                        starts_at: datetime | None = None,
                        ends_at: datetime | None = None,
                        booking_open_at: datetime | None = None,
                        booking_close_at: datetime | None = None,
                        ) -> None:
        # CANCELED, COMPLETED 공연은 일정 수정 불가 (규칙 17)
        if self.status in (PerformanceStatus.CANCELED, PerformanceStatus.COMPLETED):
            raise InvalidPerformanceStatus("취소되었거나 종료된 공연은 스케줄을 변경할 수 없습니다.")
        
        # PATCH => change_schedule()에 인자로 넣는 값만 바꾸기
        # 바꾸지 않는 값은 원래 있던 값(self.)으로 넣기
        new_starts = starts_at if starts_at is not None else self.starts_at
        new_ends = ends_at if ends_at is not None else self.ends_at
        new_booking_open = booking_open_at if booking_open_at is not None else self.booking_open_at
        new_booking_close = booking_close_at if booking_close_at is not None else self.booking_close_at
        new_cancel_deadline = new_starts - CANCEL_DEADLINE_BEFORE_START

        self._validate_schedule(starts_at=new_starts, ends_at=new_ends, booking_open_at=new_booking_open, booking_close_at=new_booking_close, cancel_deadline_at=new_cancel_deadline)
        # 수정된 일정으로 축제 기간 재검사
        self._validate_within_festival(festival_starts_on=festival_starts_on, festival_ends_on=festival_ends_on, starts_at=new_starts, ends_at=new_ends)
        self.starts_at = new_starts
        self.ends_at = new_ends
        self.booking_open_at = new_booking_open
        self.booking_close_at = new_booking_close
        self.cancel_deadline_at = new_cancel_deadline

    # 새롭게 변경하는 수량(new_capacity)는 이미 팔린 수량(capacity - remaining_count)보다 작게 줄일 수 없음
    # remaining_count 재계산 필요
    def change_capacity(self, new_capacity: int)-> None:
        if self.status in (PerformanceStatus.CANCELED, PerformanceStatus.COMPLETED):
            raise InvalidPerformanceStatus("취소되었거나 이미 끝난 공연은 수용 인원을 바꿀 수 없습니다.")
        
        # 좌석 0개짜리 공연 생성 막기
        if new_capacity < 1:
            raise InvalidPerformanceCapacity("수용 인원은 1명 이상이어야 합니다.")
        
        # 이미 팔린 수량 정의
        sold = self.capacity - self.remaining_count

        # 새 수량은 이미 팔린 수량보다 적게 정의할 수 없다.
        # ex) 총 100석에서 80석 팔렸고 20석 남은 상황.
        # 120석으로 총 좌석을 늘리기 가능: 이미 80석은 확보
        # 80석으로 총 좌석 줄이기 가능: 나머지 20석은 안팔거다
        # 만약 70석으로 총 좌석 줄이기? 불가능. : 이미 80명이 표를 샀으니까 그보다 줄일 수는 없다.
        if new_capacity < sold:
            raise InvalidPerformanceCapacity(f"이미 {sold}장이 판매되어 수용 인원을 {sold}명보다 적게 줄일 수 없습니다.")

        # remaining_count 재계산:
        self.remaining_count = new_capacity - sold
        self.capacity = new_capacity

        # 수량이 바뀌었으니 매진 상태 맞추기!
        if self.status == PerformanceStatus.SOLD_OUT and self.remaining_count > 0:
            self.status = PerformanceStatus.OPEN
        elif self.status == PerformanceStatus.OPEN and self.remaining_count == 0:
            self.status = PerformanceStatus.SOLD_OUT


    # 규칙 18 : 예매 가능 여부
    def is_bookable(self, now:datetime) -> bool:
        return (
            self.status == PerformanceStatus.OPEN and
            self.remaining_count > 0 and
            self.booking_open_at <= now < self.booking_close_at
        )

    # 규칙 19: 예매시 잔여 좌석 차감
    # 흐름(quantity를 인자로 받는 이유)
    # 사용자가 "공연 5번 2장 예매" 요청
    # ReservationService: "2장" 을 받음 (예매 정보는 지금 누가 몇장을 사려는지 알고 있음.)
    # performance.decrease_remaining(2) 로 인자 넘겨줌.
    def decrease_remaining(self, quantity: int) -> None:
        # 1. 오픈한 공연만 잔여 좌석 차감
        if self.status != PerformanceStatus.OPEN:
            raise InvalidPerformanceStatus("예매 가능한 공연이 아닙니다.")
        # 2. 0장 이하는 예매 안됨 or 잔여수량보다 더 많이 예매할 수 없음
        if quantity <= 0 or quantity > self.remaining_count:
            raise InvalidPerformanceCapacity("예매 수량이 잔여 수량 범위를 벗어났습니다.")
        # 3. 잔여 수량 차감
        self.remaining_count -= quantity
        # 4. 잔여 수량이 0이 되면 매진 상태로 처리
        if self.remaining_count == 0:
            self.status = PerformanceStatus.SOLD_OUT

    # 규칙 19: 예매 취소 시 잔여 수량 복구 (reservations 서비스에서 예매 취소 시 호출)
    def increase_remaining(self, quantity: int) -> None:
        # 1. 상태 검사: OPEN, SOLD_OUT에 해당하지 않으면 InvalidPerformanceStatus (409)
        #    (CANCELED/COMPLETED 공연은 재고를 되돌릴 의미가 없음)        
        if self.status not in (PerformanceStatus.OPEN, PerformanceStatus.SOLD_OUT):
            raise InvalidPerformanceStatus("취소되었거나 종료된 공연은 잔여 수량을 복구할 수 없습니다.")
        
        # 2. 0장 이하는 취소 안됨 or 잔여수량 + 취소수량이 capacity보다 클 수 없음
        if quantity <= 0 or self.remaining_count + quantity > self.capacity:
            raise InvalidPerformanceCapacity("복구 수량이 수용 인원 범위를 벗어났습니다.")

        # 3. 잔여 수량 increase
        self.remaining_count += quantity
        # 4. 복구 전 상태가 SOLD_OUT이었다면 status = OPEN (취소표가 생겨 다시 예매 가능)
        #    ex) 잔여 0(SOLD_OUT), 2장 취소 → 잔여 2, OPEN으로 변경
        if self.status == PerformanceStatus.SOLD_OUT:
            self.status = PerformanceStatus.OPEN
        


        

