from pydantic import BaseModel


class LogoutResponse(BaseModel):
    message: str = "로그아웃이 완료되었습니다."
