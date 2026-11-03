from pydantic import BaseModel


class APIResponse(BaseModel):
    """영상에는 정의가 보이지 않아 사용부에 맞춰 보완한 최소 스키마."""

    success: bool
    message: str
