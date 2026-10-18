"""Application-level errors surfaced to templates and JSON endpoints."""

from __future__ import annotations


class AppError(Exception):
    """User-facing error with an HTTP status (replaces the old SupabaseError)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status
