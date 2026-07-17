"""Structured errors shared by every interface."""


class CoordinatorError(Exception):
    """A safe, serializable coordinator failure."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_dict(self) -> dict[str, object]:
        """Return the public error representation."""
        return {"code": self.code, "message": self.message, **self.details}
