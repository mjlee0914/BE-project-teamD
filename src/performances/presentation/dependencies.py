from performances.application.service import PerformanceService


def get_performance_service() -> PerformanceService:
    raise NotImplementedError("wiring/performance.py에서 연결되지 않았습니다.")