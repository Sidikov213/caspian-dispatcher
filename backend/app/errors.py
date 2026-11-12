class ApiError(Exception):
    """Ошибка API → {"error": {"code", "message"}} с HTTP-статусом. fields — необязательный перечень
    полей запроса с ошибкой (document_invalid): тогда в теле ещё и error.fields."""

    def __init__(self, status: int, code: str, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields
