class DomainError(Exception):
    def __init__(self, code: str, status: int, message: str):
        super().__init__(message)
        self.code = code
        self.status = status

    @property
    def body(self) -> dict:
        return {"error": {"code": self.code, "message": str(self)}}
