# domain/repository: DB에 시킬 일(메서드) 목록(틀)
# infrastructure/repositories: 실제 SQL로 DB에 물어봄 (구현체)

from abc import ABC, abstractmethod
from festivals.domain.festival import Festival
from datetime import date

class FestivalRepository(ABC):
    @abstractmethod
    async def find_by_id(self, festival_id: int) -> Festival | None:
        """
        페스티벌 id기준으로 페스티벌 단건 조회,
        없으면 None,
        상세 조회, 수정/취소 전 기존 값 조회, 공연 도메인의 축제 존재 확인 때 사용(페스티벌이 있어야 공연 추가)
        """

    @abstractmethod
    async def find_all(self, offset: int, limit: int) -> list[Festival]:
        """
        모든 페스티벌 목록 조회
        정렬: 축제 시작일(starts_on) 오름차순, 같으면 id 오름차순
        pagination: offset(앞에서부터 몇 개 건너뛸지), limit("한번에 몇개 가져올지") 설정
        페스티벌 수가 많아질수록 응답량이 많아져 나눠서 보여준다.
        결과는 PageResponse.items 로 사용
        """

    @abstractmethod
    async def count(self) -> int:
        """
        전체 페스티벌 개수 조회 (shared/core/schemas/PageResponse.total 용)
        Pagination할 때 페스티벌 전체 개수를 계산하고 PageResponse.total 값으로 넣는 용도
        infra 구현: SELECT COUNT(*) FROM festivals
        repository에서는 PageResponse를 모르는 상태임
        이후 service와 연결 -> PageResponse.total 값으로 count() 넣어짐
        """

    @abstractmethod
    async def save(self, festival: Festival) -> Festival:
        """
        페스티벌 생성, 수정, 취소 모두 처리 (DB 반영 목적)
        id = None이면 새로 생성
        있으면 기존 행을 수정함
        DB가 채운 id, created_at등이 반영된 Festival 반환
        commit은 하지 않음 (요청 단위 세션(get_db)에서 처리)
        """

    @abstractmethod
    async def exists_overlapping(self, venue: str, starts_on: date, ends_on: date, exclude_id: int | None = None)-> bool:
        """
        같은 장소에 기간이 겹치는 축제가 있는지 확인 (있으면 True)
        취소된 축제는 제외함.
        축제 생성 시: 생성할 축제는 아직 DB에 없으므로 exclude_id는 기본값 None.
        축제 수정 시: 수정할 축제는 이미 DB에 있는 상태이므로, exclude_id=festival_id(수정할 대상 축제)
        exclude_id로 만들지 않으면 수정할 때 자기 자신을 다른 축제로 착각할 수 있음 (11/10-11/12 축제를 11/10-11/13 으로 변경할 경우)
        """
        
