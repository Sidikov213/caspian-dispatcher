class ApiError(Exception):
    """Ошибка API → {"error": {"code", "message"}} с HTTP-статусом."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
