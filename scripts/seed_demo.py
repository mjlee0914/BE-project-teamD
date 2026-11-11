"""
데모용 DB 시드 스크립트 (기존 데이터를 모두 지우고 다시 넣음 — 주의)

- 모든 테이블 생성 (없으면 생성, 있으면 그대로)
- 기존 데이터를 비우고 ERD 기준으로 실제 서비스처럼 보이는 데모 데이터 입력
  · 회원 : 관리자 1 + 일반 9 (탈퇴 회원 1명 포함), 비밀번호는 모두 DEMO_PASSWORD
  · 축제 5개 : 예매 중 / 매진 임박 / 오픈 예정 / 종료 / 취소 — 상태별로 하나씩
  · 회차 : 축제마다 토·일 2회차
  · 예매·티켓·결제 : 확정/대기/취소/만료/사용완료 등 상태가 섞이도록 생성
    → 예매된 수량만큼 회차 remaining_count 차감

실행 (레포 루트에서)
    uv run python scripts/seed_demo.py
"""

import asyncio
import importlib
import sys
import uuid
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from sqlalchemy import insert, text, update  # noqa: E402

from auth.infrastructure.password_hasher import BcryptPasswordHasher  # noqa: E402
from shared.core.database import engine  # noqa: E402
from shared.core.models import Base  # noqa: E402
from shared.core.time import KST  # noqa: E402

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

# 로컬 데모 전용 비밀번호 (회원 규칙: 영문·숫자·특수문자 포함 8자 이상)
DEMO_PASSWORD = "Demo1234!"

# (email, name, phone, role, withdrawn)
DEMO_USERS = [
    ("admin@demo.com", "관리자", None, "ADMIN", False),
    ("minsu@demo.com", "김민수", "010-2481-3357", "USER", False),
    ("jiyoung@demo.com", "이지영", "010-7712-0941", "USER", False),
    ("seojun@demo.com", "박서준", "010-3305-8826", "USER", False),
    ("haeun@demo.com", "최하은", "010-9046-1173", "USER", False),
    ("doyun@demo.com", "정도윤", "010-5528-6490", "USER", False),
    ("yerin@demo.com", "강예린", "010-6631-2085", "USER", False),
    ("jiho@demo.com", "윤지호", "010-1194-7702", "USER", False),
    ("sua@demo.com", "한수아", "010-8857-4419", "USER", False),
    ("left@demo.com", "탈퇴회원", None, "USER", True),
]

# key: (name, venue, description, 주말 오프셋(주), 토요일가, 일요일가, 정원, 모드)
# 모드: open(예매중) / hot(매진 임박) / soon(오픈 예정) / past(종료) / canceled(취소)
FESTIVALS = [
    (
        "open",
        "2026 KANT 가을 음악 페스티벌",
        "올림픽공원 88잔디마당",
        "가을밤을 채우는 인디·밴드·R&B 라인업. 토요일은 밴드 데이, 일요일은 어쿠스틱 데이로 진행됩니다.",
        1, 55000, 60000, 300,
    ),
    (
        "hot",
        "서울 재즈 나잇 2026",
        "잠실 한강공원 수변무대",
        "한강 야경과 함께하는 재즈 공연. 좌석 소진이 빠르니 서둘러 주세요.",
        2, 70000, 70000, 40,
    ),
    (
        "soon",
        "윈터 일렉트로닉 위크엔드",
        "인천 송도 컨벤시아 야외광장",
        "겨울 시즌 오프닝 EDM 페스티벌. 예매는 공연 2주 전 오픈됩니다.",
        5, 88000, 88000, 500,
    ),
    (
        "past",
        "2026 KANT 여름 록 페스티벌",
        "난지 한강공원 젊음의광장",
        "올여름을 뜨겁게 달군 록 페스티벌. 성황리에 종료되었습니다.",
        -10, 65000, 65000, 200,
    ),
    (
        "canceled",
        "부산 바다 뮤직 위크엔드",
        "부산 광안리 해수욕장 특설무대",
        "기상 악화(태풍 예보)로 공연이 취소되었습니다. 결제 금액은 전액 환불됩니다.",
        3, 60000, 60000, 150,
    ),
]

DAY_TITLES = {
    "open": ("DAY 1 - 밴드 데이", "DAY 2 - 어쿠스틱 데이"),
    "hot": ("DAY 1 - 스윙 나잇", "DAY 2 - 블루스 나잇"),
    "soon": ("DAY 1 - 하우스", "DAY 2 - 테크노"),
    "past": ("DAY 1 - 헤드라이너", "DAY 2 - 피날레"),
    "canceled": ("DAY 1 - 오프닝", "DAY 2 - 클로징"),
}

# 예매 시나리오: (축제 모드, 회원 email, 권종, 수량, 할인, 상태)
RESERVATIONS = [
    ("open", "minsu@demo.com", "BOTH", 2, "NONE", "CONFIRMED"),
    ("open", "jiyoung@demo.com", "SAT", 1, "KANT", "CONFIRMED"),
    ("open", "seojun@demo.com", "SUN", 2, "NONE", "CONFIRMED"),
    ("open", "haeun@demo.com", "SAT", 2, "NONE", "PENDING"),
    ("open", "doyun@demo.com", "SUN", 1, "SENIOR", "CANCELED"),
    ("open", "yerin@demo.com", "BOTH", 1, "NONE", "EXPIRED"),
    ("hot", "minsu@demo.com", "SAT", 2, "NONE", "CONFIRMED"),
    ("hot", "jiho@demo.com", "BOTH", 2, "NONE", "CONFIRMED"),
    ("hot", "sua@demo.com", "SUN", 2, "VETERAN", "CONFIRMED"),
    ("hot", "yerin@demo.com", "SAT", 1, "DISABLED", "CONFIRMED"),
    ("past", "minsu@demo.com", "BOTH", 1, "NONE", "USED"),
    ("past", "jiyoung@demo.com", "SAT", 2, "NONE", "USED"),
    ("past", "haeun@demo.com", "SUN", 1, "NONE", "NOSHOW"),
    ("canceled", "seojun@demo.com", "SAT", 2, "NONE", "REFUNDED"),
    ("canceled", "jiho@demo.com", "BOTH", 1, "NONE", "REFUNDED"),
]

DISCOUNT_RATE = {"NONE": 0, "DISABLED": 60, "VETERAN": 70, "SENIOR": 80, "KANT": 90}
METHODS = ["카드", "가상계좌", "간편결제"]
WEEKDAY = {"SAT": [0], "SUN": [1], "BOTH": [0, 1]}


def weekend(today: date, weeks: int) -> tuple[date, date]:
    """오늘 기준 weeks번째 토·일 (음수면 과거)"""
    days_to_sat = (5 - today.weekday()) % 7 or 7
    saturday = today + timedelta(days=days_to_sat) + timedelta(weeks=weeks - 1)
    return saturday, saturday + timedelta(days=1)


def payment_log(order_id: str) -> list[dict]:
    return [
        {
            "_payment_metadata": {
                "order_id": order_id,
                "webhook_secret_hash": None,
                "processed_deposit_events": [],
            }
        }
    ]


async def seed() -> dict:
    t = Base.metadata.tables
    now = datetime.now(UTC)
    today = datetime.now(KST).date()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        names = ", ".join(tb.name for tb in reversed(Base.metadata.sorted_tables))
        await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))

        # ── 회원
        password_hash = BcryptPasswordHasher().hash(DEMO_PASSWORD)
        user_ids: dict[str, int] = {}
        for i, (email, name, phone, role, withdrawn) in enumerate(DEMO_USERS):
            user_ids[email] = await conn.scalar(
                insert(t["users"])
                .values(
                    email=email,
                    name=name,
                    phone=phone,
                    password_hash=password_hash,
                    role=role,
                    status="WITHDRAWN" if withdrawn else "ACTIVE",
                    created_at=now - timedelta(days=60 - i * 5),
                    deleted_at=now - timedelta(days=3) if withdrawn else None,
                )
                .returning(t["users"].c.id)
            )

        # ── 축제 + 회차
        fest: dict[str, dict] = {}
        for mode, name, venue, desc, weeks, sat_price, sun_price, cap in FESTIVALS:
            sat, sun = weekend(today, weeks)
            fid = await conn.scalar(
                insert(t["festivals"])
                .values(
                    name=name,
                    venue=venue,
                    description=desc,
                    starts_on=sat,
                    ends_on=sun,
                    canceled_at=now - timedelta(days=2) if mode == "canceled" else None,
                )
                .returning(t["festivals"].c.id)
            )
            perfs = []
            for day, title, price in (
                (sat, DAY_TITLES[mode][0], sat_price),
                (sun, DAY_TITLES[mode][1], sun_price),
            ):
                starts_at = datetime.combine(day, time(17, 0), tzinfo=KST).astimezone(UTC)
                if mode == "soon":
                    open_at = starts_at - timedelta(days=14)
                elif mode == "past":
                    open_at = starts_at - timedelta(days=30)
                else:
                    open_at = now - timedelta(days=3)
                status = {
                    "open": "OPEN",
                    "hot": "OPEN",
                    "soon": "SCHEDULED",
                    "past": "COMPLETED",
                    "canceled": "CANCELED",
                }[mode]
                pid = await conn.scalar(
                    insert(t["performances"])
                    .values(
                        festival_id=fid,
                        title=title,
                        starts_at=starts_at,
                        ends_at=starts_at + timedelta(hours=5),
                        booking_open_at=open_at,
                        booking_close_at=starts_at - timedelta(hours=2),
                        cancel_deadline_at=starts_at - timedelta(days=1),
                        capacity=cap,
                        remaining_count=cap,
                        price=price,
                        status=status,
                        version=1,
                    )
                    .returning(t["performances"].c.id)
                )
                perfs.append(
                    {"id": pid, "title": title, "price": price, "starts_at": starts_at, "cap": cap}
                )
            fest[mode] = {"id": fid, "name": name, "venue": venue, "perfs": perfs, "open_at": perfs[0]["starts_at"] - timedelta(days=30) if mode == "past" else now - timedelta(days=3)}

        # ── 예매 · 티켓 · 결제
        sold: dict[int, int] = {}
        for i, (mode, email, ttype, qty, discount, scenario) in enumerate(RESERVATIONS):
            f = fest[mode]
            perfs = [f["perfs"][d] for d in WEEKDAY[ttype]]
            total = sum(p["price"] for p in perfs) * qty
            disc = total * DISCOUNT_RATE[discount] // 100
            created = (
                now - timedelta(minutes=3)
                if scenario == "PENDING"
                else f["open_at"] + timedelta(hours=2 + i * 7)
            )

            res_status = {
                "CONFIRMED": "CONFIRMED", "USED": "CONFIRMED", "NOSHOW": "CONFIRMED",
                "PENDING": "PENDING", "CANCELED": "CANCELED", "REFUNDED": "CANCELED",
                "EXPIRED": "EXPIRED",
            }[scenario]
            paid = scenario in ("CONFIRMED", "USED", "NOSHOW", "CANCELED", "REFUNDED")
            confirmed_at = created + timedelta(minutes=2) if paid else None
            canceled_at = None
            if scenario == "CANCELED":
                canceled_at = created + timedelta(days=1)
            elif scenario == "REFUNDED":
                canceled_at = now - timedelta(days=2)

            rid = await conn.scalar(
                insert(t["reservations"])
                .values(
                    quantity=qty,
                    status=res_status,
                    total_price=total,
                    discount_amount=disc,
                    discount_type=discount,
                    final_price=total - disc,
                    ticket_type=ttype,
                    expires_at=created + timedelta(minutes=10),
                    confirmed_at=confirmed_at,
                    canceled_at=canceled_at,
                    created_at=created,
                    festival_name=f["name"],
                    venue=f["venue"],
                    user_id=user_ids[email],
                    festival_id=f["id"],
                )
                .returning(t["reservations"].c.id)
            )

            ticket_status = {
                "CONFIRMED": "ISSUED", "USED": "USED", "NOSHOW": "EXPIRED",
                "PENDING": "PENDING", "CANCELED": "CANCELED", "REFUNDED": "CANCELED",
                "EXPIRED": "EXPIRED",
            }[scenario]
            for p in perfs:
                if scenario in ("CONFIRMED", "USED", "NOSHOW", "PENDING"):
                    sold[p["id"]] = sold.get(p["id"], 0) + qty
                for _ in range(qty):
                    await conn.execute(
                        insert(t["tickets"]).values(
                            reservation_id=rid,
                            performance_id=p["id"],
                            status=ticket_status,
                            ticket_code=uuid.uuid4(),
                            cancel_deadline_at=p["starts_at"] - timedelta(days=1),
                            performance_start_at=p["starts_at"],
                            performance_end_at=p["starts_at"] + timedelta(hours=5),
                            performance_title=p["title"],
                            issued_at=confirmed_at,
                            used_at=p["starts_at"] + timedelta(minutes=40) if ticket_status == "USED" else None,
                            canceled_at=canceled_at if ticket_status == "CANCELED" else None,
                            created_at=created,
                            price=p["price"],
                            version=1,
                        )
                    )

            if scenario == "EXPIRED":
                pay_status = "EXPIRED"
            elif scenario == "PENDING":
                pay_status = "WAITING_FOR_DEPOSIT"
            elif scenario in ("CANCELED", "REFUNDED"):
                pay_status = "CANCELED"
            else:
                pay_status = "DONE"
            order_id = f"KANT-{created:%Y%m%d}-{rid:05d}"
            await conn.execute(
                insert(t["payments"]).values(
                    reservation_id=rid,
                    status=pay_status,
                    method="가상계좌" if pay_status in ("WAITING_FOR_DEPOSIT", "EXPIRED") else METHODS[i % 3],
                    amount=total - disc,
                    payment_key=f"tgen_{uuid.uuid4().hex[:20]}" if paid else None,
                    paid_at=confirmed_at,
                    canceled_at=canceled_at if pay_status == "CANCELED" else None,
                    created_at=created,
                    payment_log=payment_log(order_id),
                )
            )

        # 매진 임박 축제는 남은 좌석을 한 자릿수로 맞춘다 (다른 사람 예매분 가정)
        for p in fest["hot"]["perfs"]:
            sold[p["id"]] = p["cap"] - (3 if p is fest["hot"]["perfs"][0] else 7)
        for f in fest.values():
            for p in f["perfs"]:
                if p["id"] in sold:
                    await conn.execute(
                        update(t["performances"])
                        .where(t["performances"].c.id == p["id"])
                        .values(remaining_count=p["cap"] - sold[p["id"]])
                    )

    return {k: v["id"] for k, v in fest.items()} | {"reservations": len(RESERVATIONS)}


if __name__ == "__main__":
    print(asyncio.run(seed()))
