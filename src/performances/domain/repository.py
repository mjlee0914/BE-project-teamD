# DB에 시킬 일의 목록: 실제 SQL 사용 안함. 어떤 메서드가 있는지, 무엇을 주고 받는지만 정한다.
# 실제 구현: infrastructure/repositories.py
# application/service.py "공연 5번 꺼내 줘"
# PerformanceRepository (목록, domain)
# SqlAlchemyPerformanceRepository(SQL, infrastructure)

from abc import ABC, abstractmethod

from performances.domain.performance import Performance


class PerformanceRepository(ABC):
    @abstractmethod
    async def find_by_id(self, performance_id: int) -> Performance | None:
        """
        공연 id 기준으로 공연 단건 조회
        없으면 None (404 변환은 service가 PerformanceNotFound로 처리)
        상세 조회, 수정·상태 변경(open/complete/cancel) 전 기존 값 조회,
        예매 시 재고 차감·복구 전 공연 조회 때 사용
        """

    @abstractmethod
    async def find_all(self, offset: int, limit: int) -> list[Performance]:
        """
        전체 공연 목록 조회 (축제 구분 없이)
        정렬: 공연 시작 시각(starts_at) 오름차순, 같으면 id 오름차순
        pagination: offset(앞에서부터 몇 개 건너뛸지), limit(한 번에 몇 개 가져올지)
        결과는 PageResponse.items로 사용
        """

    @abstractmethod
    async def find_all_by_festival(self, festival_id: int, offset: int, limit: int) -> list[Performance]:
        """
        특정 축제에 소속된 공연 목록 조회
        정렬·pagination 기준은 find_all과 같음
        축제가 존재하는지는 확인하지 않음 (없는 축제면 빈 리스트)
        → 축제 존재 확인(404)은 service가 FestivalRepository로 먼저 처리
        """

    @abstractmethod
    async def count(self) -> int:
        """
        전체 공연 개수 조회 (PageResponse.total 용)
        find_all과 같은 조건으로 셈
        infra 구현: SELECT COUNT(*) FROM performances
        """

    @abstractmethod
    async def count_by_festival(self, festival_id: int) -> int:
        """
        특정 축제에 소속된 공연 개수 조회 (PageResponse.total 용)
        find_all_by_festival과 같은 조건으로 셈
        infra 구현: SELECT COUNT(*) FROM performances WHERE festival_id = :festival_id
        """

    @abstractmethod
    async def save(self, performance: Performance) -> Performance:
        """
        공연 생성, 수정, 상태 변경, 재고 변경 모두 처리 (DB 반영 목적)
        id = None이면 새로 생성
        있으면 기존 행을 수정함
        DB가 채운 id, created_at 등이 반영된 Performance 반환
        commit은 하지 않음 (요청 단위 세션(get_db)에서 처리)
        수정할 때는 find_by_id 등으로 "꺼내서 → 고치고 → save" 순서로 사용
        (꺼낼 때의 version으로 동시 수정 충돌을 검사함)
        다른 요청이 먼저 수정했으면 PerformanceVersionConflict(409)
        """

    @abstractmethod
    async def exists_duplicated_title(self, festival_id: int, title: str, exclude_id: int | None = None) -> bool:
        """
        같은 축제 안에 같은 제목의 공연이 있는지 확인 (있으면 True) (규칙 20)
        다른 축제의 같은 제목은 중복으로 보지 않음
        취소된 공연도 중복 검사에 포함함 (DB UniqueConstraint가 상태와 관계없이 막기 때문)
        공연 생성 시: 생성할 공연은 아직 DB에 없으므로 exclude_id는 기본값 None
        공연 수정 시: 수정할 공연은 이미 DB에 있으므로 exclude_id=performance_id(수정할 대상 공연)
        exclude_id를 넘기지 않으면 제목을 그대로 두고 수정할 때 자기 자신을 중복으로 착각함
        True면 service가 PerformanceTitleDuplicated(409)를 던짐
        DB의 uq_performances_festival_title은 동시 요청 대비 마지막 안전장치로 유지
        """