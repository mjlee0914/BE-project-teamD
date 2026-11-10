"""
데모용 DB 준비 스크립트 (팀 백엔드 코드는 수정하지 않음)

- 모든 테이블 생성 (없으면 생성, 있으면 그대로)
- 기존 데이터를 비우고 데모 데이터 입력
  · 회원 3명 : 민수(일반), 지영(일반), 관리자(ADMIN)
  · 축제 1개 : 이번 주 토·일
  · 회차 2개 : 토요일 / 일요일 (정원 100, 예매 오픈 상태)

실행 (레포 루트에서)
    uv run python frontend/demo_backend/seed.py
"""

import asyncio
import importlib
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from sqlalchemy import insert, text  # noqa: E402

from shared.core.database import engine  # noqa: E402
from shared.core.models import Base  # noqa: E402
from shared.core.time import KST  # noqa: E402

# 테이블 등록 (init_models()에 tickets가 빠져 있어서 직접 전부 import)
for module in (
    "users",
    "auth",
    "festivals",
    "performances",
    "reservations",
    "payments",
    "tickets",
):
    importlib.import_module(f"{module}.infrastructure.models")

DEMO_USERS = [
    {"email": "minsu@demo.com", "name": "민수", "role": "USER"},
    {"email": "jiyoung@demo.com", "name": "지영", "role": "USER"},
    {"email": "admin@demo.com", "name": "관리자", "role": "ADMIN"},
]


def next_weekend(today: date) -> tuple[date, date]:
    """오늘 이후 가장 가까운 토·일 (오늘이 토·일이면 다음 주)"""
    days_to_sat = (5 - today.weekday()) % 7 or 7
    saturday = today + timedelta(days=days_to_sat)
    return saturday, saturday + timedelta(days=1)


async def seed() -> dict:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # 기존 데이터 비우기 (자식 → 부모 순서는 CASCADE로 처리)
        tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

        users_t = Base.metadata.tables["users"]
        for u in DEMO_USERS:
            await conn.execute(
                insert(users_t).values(
                    email=u["email"],
                    name=u["name"],
                    password_hash="demo-not-a-real-hash",
                    role=u["role"],
                    status="ACTIVE",
                )
            )

        today = datetime.now(KST).date()
        saturday, sunday = next_weekend(today)
        festivals_t = Base.metadata.tables["festivals"]
        festival_id = await conn.scalar(
            insert(festivals_t)
            .values(
                name="KANT 가을 음악 페스티벌",
                venue="올림픽공원 88잔디마당",
                description="토·일 이틀간 열리는 야외 음악 축제",
                starts_on=saturday,
                ends_on=sunday,
            )
            .returning(festivals_t.c.id)
        )

        perf_t = Base.metadata.tables["performances"]
        now = datetime.now(UTC)
        for day, title, price in (
            (saturday, "토요일 공연", 50000),
            (sunday, "일요일 공연", 60000),
        ):
            starts_at = datetime.combine(day, time(18, 0), tzinfo=KST).astimezone(UTC)
            await conn.execute(
                insert(perf_t).values(
                    festival_id=festival_id,
                    title=title,
                    starts_at=starts_at,
                    ends_at=starts_at + timedelta(hours=4),
                    booking_open_at=now - timedelta(days=1),
                    booking_close_at=starts_at - timedelta(hours=1),
                    cancel_deadline_at=starts_at - timedelta(hours=24),
                    capacity=100,
                    remaining_count=100,
                    price=price,
                    status="OPEN",
                    version=1,
                )
            )

    return {"festival_id": festival_id, "saturday": str(saturday), "sunday": str(sunday)}


if __name__ == "__main__":
    print(asyncio.run(seed()))
