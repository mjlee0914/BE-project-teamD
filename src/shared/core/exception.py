class SharedException(Exception):
    """모든 도메인에서 재사용할 공통 예외. 영상의 구조를 재구성."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)  # 실행용 보완
        self.status_code = status_code
        self.message = message

    def __str__(self) -> str:
        return self.message
