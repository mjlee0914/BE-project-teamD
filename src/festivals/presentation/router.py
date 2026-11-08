from dataclasses import asdict
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from festivals.application.service import FestivalService
from festivals.domain.festival import Festival
from festivals.presentation.dependencies import get_festival_service
from festivals.presentation.schemas import (
    FestivalCreate,
    FestivalResponse,
    FestivalUpdate,
)
from shared.core.schemas import APIResponse, PageResponse

KST = ZoneInfo("Asia/Seoul")


router = APIRouter(prefix="/v1/festivals", tags=["festivals"])

# FastAPI가 넣어주는 service (FastAPI가 wiring 등록부를 보고 진짜 service를 넣어준다.)
# Annotated[타입, Depends(...)]: 타입은 FestivalService, 값은 FastAPI가 Depends로 채움
# 기본값 자리(= Depends(...))에 쓰지 않으므로 ruff B008 경고가 나지 않고, 5개 API에서 같은 이름으로 재사용
FestivalServiceDep = Annotated[FestivalService, Depends(get_festival_service)]

# 응답 만드는 helper 함수
# 축제 응답에 계산된 status가 들어갈 수 있도록 추가함.
def _to_response(festival: Festival) -> FestivalResponse:
    today = datetime.now(KST).date()

    return FestivalResponse.model_validate(
        {
            **asdict(festival),
            "status": festival.status(today)
        }
    )

# 축제 생성
@router.post("", status_code=201, response_model=APIResponse[FestivalResponse])
async def create_festival(
    body: FestivalCreate, # 사용자가 보낸 JSON, FestivalCreate 스키마로 검사한 뒤 넣어준다. (형식 틀리면 함수 실행 전 422)
    service: FestivalServiceDep,
):
    # body에 값을 하나씩 꺼내서 넘김.
    # 엔티티 검사, 겹침 검사, 저장은 전부 서비스에서
    # 라우터는 값을 넘기기만 한다.
    festival = await service.create_festival(
        name=body.name,
        venue=body.venue,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        description=body.description
    )

    # 엔티티를 응답 스키마로 바꿈.
    # APIResponse.ok(data=...)로 팀 공통 모양으로 응답 스키마 감싸기
    return APIResponse.ok(data=_to_response(festival))


# 축제 목록 불러오기
# 응답은 축제 하나가 아닌 축제목록+전체개수+page+size의 페이지의 여러개이므로,
# PageResponse로 받는다.
@router.get("", response_model=APIResponse[PageResponse[FestivalResponse]])
async def list_festivals(
    service: FestivalServiceDep,
    # Annotated[타입, Query(검사 규칙)] = 기본값
    # 기본값이 없는 service가 기본값이 있는 page·size보다 앞에 와야 함 (파이썬 인자 순서 규칙)
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    
    festivals, total = await service.list_festivals(page, size)

    # 리스트를 통째로 model_validate에 넣지 않고, for문으로 하나씩 꺼낸다.
    # list comprehension:
    # festivals에서 하나씩 꺼내고, 그것을 _to_response하여 하나씩 리스트로 담는다.
    items = [_to_response(f) for f in festivals]
    # PageResponse.create로 4개 값을 하나로 묶어 페이지 응답 하나를 만든다.
    page_data = PageResponse.create(items=items, total=total, page=page, size=size)
    
    return APIResponse.ok(data=page_data)


# 축제 상세 불러오기
@router.get("/{festival_id}", response_model=APIResponse[FestivalResponse])
async def get_festival(
    festival_id: int,
    service: FestivalServiceDep,
):
    festival = await service.get_festival(festival_id)
    return APIResponse.ok(data=_to_response(festival))

# 축제 정보 수정
@router.patch("/{festival_id}", response_model=APIResponse[FestivalResponse])
async def update_festival(
    festival_id: int,
    body: FestivalUpdate,
    service: FestivalServiceDep,
):
    festival = await service.update_festival(
        festival_id=festival_id,
        name= body.name,
        venue=body.venue,
        description=body.description,
        starts_on=body.starts_on,
        ends_on=body.ends_on
    )
    return APIResponse.ok(data=_to_response(festival))

# 축제 취소
@router.post("/{festival_id}/cancel", response_model=APIResponse[FestivalResponse])
async def cancel_festival(
    festival_id: int,
    service: FestivalServiceDep,
):
    festival = await service.cancel_festival(
        festival_id=festival_id
    )
    return APIResponse.ok(data=_to_response(festival))

