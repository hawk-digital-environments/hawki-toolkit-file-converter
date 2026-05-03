from __future__ import annotations

from enum import Enum

from pydantic import ValidationError


class FailureCategory(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"


class WorkerError(Exception):
    pass


class TransientWorkerError(WorkerError):
    pass


class PermanentWorkerError(WorkerError):
    pass


class InvalidSchemaError(PermanentWorkerError):
    pass


class UnsupportedFileTypeError(PermanentWorkerError):
    pass


class MissingLocalFileError(PermanentWorkerError):
    pass


class UnsafePathError(PermanentWorkerError):
    pass


class CorruptedFileError(PermanentWorkerError):
    pass


class EmptyOutputError(PermanentWorkerError):
    pass


class TemporaryFileSystemLockError(TransientWorkerError):
    pass


class TemporaryRabbitMQError(TransientWorkerError):
    pass


class DownstreamStorageUnavailableError(TransientWorkerError):
    pass


class TemporaryTimeoutError(TransientWorkerError):
    pass


def classify_failure(error: Exception) -> FailureCategory:
    if isinstance(error, (TransientWorkerError, TimeoutError)):
        return FailureCategory.TRANSIENT

    if isinstance(
        error,
        (
            PermanentWorkerError,
            ValidationError,
            ValueError,
            FileNotFoundError,
            PermissionError,
        ),
    ):
        return FailureCategory.PERMANENT

    message = str(error).lower()
    transient_markers = [
        "timeout",
        "tempor",
        "connection reset",
        "connection refused",
        "service unavailable",
        "resource busy",
        "file is locked",
    ]
    if any(marker in message for marker in transient_markers):
        return FailureCategory.TRANSIENT

    return FailureCategory.PERMANENT
