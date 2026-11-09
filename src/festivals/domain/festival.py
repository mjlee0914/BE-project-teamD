# 축제 규칙 (기간 검사, 상태 계산, 취소)

"""
Festival 규칙
1. 축제 이름은 1자 이상 50자 이하로 구성되어야 한다.
2. 축제 장소는 1자 이상 50자 이하로 구성되어야 한다.
3. 축제 설명은 필수가 아니며, 설명이 없는 경우 None으로 관리한다.
4. 축제 시작일은 종료일보다 반드시 빨라야 한다.
   시작일과 종료일이 같은 하루짜리 축제는 허용하지 않는다.
   starts_on, ends_on은 한국(KST) 기준 날짜이다.
5. 축제 상태는 별도 컬럼으로 저장하지 않고 starts_on, ends_on,
   canceled_at과 현재 날짜를 기준으로 계산한다.
   - 현재 날짜 < starts_on: SCHEDULED
   - starts_on <= 현재 날짜 <= ends_on: OPEN
   - 현재 날짜 > ends_on: COMPLETED
   - canceled_at이 존재하는 경우: CANCELED
6. 취소 상태는 날짜 상태보다 우선한다.
   starts_on 또는 ends_on과 관계없이 canceled_at이 존재하면
   축제 상태는 CANCELED로 판단한다.
7. 축제 취소 시 canceled_at에 서버의 현재 시각을 기록한다.
   canceled_at은 사용자가 직접 입력하거나 일반 수정 API로 변경할 수 없다.
8. 이미 취소된 축제는 다시 취소할 수 없다.
9. 축제의 생성, 수정, 취소는 관리자 권한을 가진 사용자만 가능하다.
10. 공연은 반드시 하나의 축제에 소속되어야 한다.
    공연 일정은 소속 축제의 시작일과 종료일 범위 안에 있어야 한다.
"""
from dataclasses import dataclass
from datetime import date, datetime

from festivals.domain.enums import FestivalStatus
from festivals.domain.exceptions import (
    FestivalAlreadyCanceled,
    InvalidFestivalName,
    InvalidFestivalPeriod,
    InvalidFestivalVenue,
)


@dataclass
class Festival:
    # 생성할 때 직접 넣어야 하는 필수값
    name: str
    venue: str
    starts_on: date
    ends_on: date

    # 기본값이 있는 필드가 아래쪽 위치
    # DB 저장 전에는 없고, 저장 후 DB가 채워주는 값
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # 실제로 값이 없어도 되는 선택값
    description: str | None = None
    canceled_at: datetime | None = None

    # 규칙을 메서드로
    # 규칙 1, 2, 4
    # 객체 생성시 dataclass로 __init__ 필드 다 채운 뒤 자동 검증
    # -> 잘못된 축제가 아예 존재 불가능함
    def __post_init__(self):
        self._validate_period(self.starts_on, self.ends_on)
        self.name = self._normalize_text(self.name, InvalidFestivalName)
        self.venue = self._normalize_text(self.venue, InvalidFestivalVenue)
        self.description = self._normalize_description(self.description)

    # 축제기간 검증용
    @staticmethod
    def _validate_period(starts_on:date, ends_on: date) -> None:
        if starts_on >= ends_on:
            raise InvalidFestivalPeriod()

    # 축제이름, 축제장소 검증용
    @staticmethod
    def _normalize_text(val: str, error: type[Exception]) -> str:
        val = val.strip()
        if not (1 <= len(val) <= 50):
            raise error()
        return val

    # 축제 설명 정리용
    @staticmethod
    def _normalize_description(description: str | None) -> str | None:
        if not description:
            return None
        description = description.strip()
        if not description:
            return None
        return description

    # 규칙 5/6번: 상태 계산 -> 상태를 저장하지 않고 status(today)로 계산
    # 오늘 날짜를 인자로 받음
    # 안에서 date.today()를 부르면 테스트할 때 날짜를 바꿀 수 없음
    # canceled_at 확인을 제일 먼저 함 (규칙 6)
    def status(self, today: date) -> FestivalStatus:
        if self.canceled_at is not None:
            return FestivalStatus.CANCELED
        if self.starts_on > today:
            return FestivalStatus.SCHEDULED
        if self.ends_on >= today:
            return FestivalStatus.OPEN
        else:
            return FestivalStatus.COMPLETED

    # 규칙 7/8번: 취소
    # 이미 취소되었을 시 : FestivalAlreadyCanceled
    # 아니면 : canceled_at=now
    def cancel(self, now: datetime) -> None:
        if self.canceled_at is not None:
            raise FestivalAlreadyCanceled()
        else:
            self.canceled_at = now

    # PATCH 용
    # None으로 온 값은 기존 값으로 채운 다음 검증
    # 로드맵 step 5 : 기존 값 + 바뀐 값 합쳐서 검증
    def change_period(
            self,
            starts_on: date | None = None,
            ends_on: date | None = None,
    ) -> None:
        if self.canceled_at is not None:
            raise FestivalAlreadyCanceled("취소된 축제의 기간 정보는 바꿀 수 없습니다.")
        new_starts = starts_on if starts_on is not None else self.starts_on
        new_ends = ends_on if ends_on is not None else self.ends_on

        self._validate_period(new_starts, new_ends)
        self.starts_on=new_starts
        self.ends_on=new_ends

    def change_info(
            self,
            name: str | None = None,
            venue: str | None = None,
            description: str | None = None
    ) -> None:
        if self.canceled_at is not None:
            raise FestivalAlreadyCanceled("취소된 축제의 정보는 바꿀 수 없습니다.")

        new_name = name if name is not None else self.name
        new_venue = venue if venue is not None else self.venue

        if description is None:
            new_description = self.description
        else:
            new_description = self._normalize_description(description)

        new_name = self._normalize_text(new_name, InvalidFestivalName)
        new_venue = self._normalize_text(new_venue, InvalidFestivalVenue)
        self.name = new_name
        self.venue = new_venue
        self.description = new_description

