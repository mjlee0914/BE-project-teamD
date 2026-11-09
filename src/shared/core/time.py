from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

# 한국 시간대 : "몇 월 며칠 / 무슨 요일" 판단할 때만 사용 (저장·비교는 UTC)
KST = ZoneInfo("Asia/Seoul")


def now_utc() -> datetime:
    """현재 시각 (UTC). 호출할 때마다 새로 계산"""
    return datetime.now(UTC)


def today_kst() -> date:
    """오늘 날짜 (한국 기준)"""
    return now_utc().astimezone(KST).date()
