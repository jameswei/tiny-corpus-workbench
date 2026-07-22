from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any


DOCLING_DOCUMENT_COMPATIBILITY = (
    "reloadable only with the exact uv.lock environment that created this artifact"
)
_MESSAGE_SEPARATOR_TRANSLATION = str.maketrans(
    {
        codepoint: " "
        for codepoint in (*range(0x20), *range(0x7F, 0xA0), 0x2028, 0x2029)
    }
)


class ExitCode(IntEnum):
    SUCCESS = 0
    INTERNAL = 1
    INPUT = 2
    PARTIAL = 3
    FAILED = 4
    INTEGRITY = 5
    RUNTIME = 6


@dataclass(frozen=True)
class StableError:
    code: str
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", sanitize_message(self.message))

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class WorkbenchError(Exception):
    exit_code = ExitCode.INTERNAL


class InputError(WorkbenchError):
    exit_code = ExitCode.INPUT


class IntegrityError(WorkbenchError):
    exit_code = ExitCode.INTEGRITY


class RuntimeContractError(WorkbenchError):
    exit_code = ExitCode.RUNTIME


@dataclass(frozen=True)
class SourceIdentity:
    path: str
    name: str
    key: str
    media_type: str
    size: int
    sha256: str
    fixture_id: str | None
    capture_method: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sanitize_message(value: BaseException | str) -> str:
    message = str(value).translate(_MESSAGE_SEPARATOR_TRANSLATION)
    return " ".join(message.split())[:500] or "unspecified failure"
