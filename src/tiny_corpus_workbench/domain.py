from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sanitize_message(value: BaseException | str) -> str:
    message = str(value).replace("\r", " ").replace("\n", " ")
    return " ".join(message.split())[:500] or "unspecified failure"
