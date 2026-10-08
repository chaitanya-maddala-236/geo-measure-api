"""Typed application errors that can be returned safely to API clients."""


class APIError(Exception):
    """An expected error with a public message and HTTP status code."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ProcessingError(Exception):
    """An expected failure while validating or reading an uploaded file."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
