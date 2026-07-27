"""Foreground loopback HTTP server for the read-only v0.5 workbench."""

from __future__ import annotations

import re
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.resources import files
from typing import Any

from tiny_corpus_workbench.canonical_json import canonical_json
from tiny_corpus_workbench.domain import InputError, IntegrityError, sanitize_message
from tiny_corpus_workbench.schema_catalog import validate_document
from tiny_corpus_workbench.workbench_projection import WorkbenchProjection
from tiny_corpus_workbench.workbench_records import (
    MAX_ARTIFACT_CONTENT,
    AdmittedRecords,
)


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MIN_PORT = 1024
MAX_PORT = 65535
MAX_TARGET = 8 * 1024
MAX_HEADER_FIELDS = 32
MAX_HEADER_BYTES = 32 * 1024
MAX_STRUCTURED_RESPONSE = 4 * 1024 * 1024
KEY = re.compile(r"[0-9a-f]{64}\Z")
FIELD_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+\Z")

SECURITY_HEADERS = (
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("X-Frame-Options", "DENY"),
    (
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
    ),
)

ERRORS = {
    "BAD_REQUEST": (400, "request is invalid"),
    "HOST_REJECTED": (403, "host is not allowed"),
    "ORIGIN_REJECTED": (403, "origin is not allowed"),
    "NOT_FOUND": (404, "resource was not found"),
    "METHOD_NOT_ALLOWED": (405, "method is not allowed"),
    "ARTIFACT_CHANGED": (409, "authorized artifact changed"),
    "REQUEST_TOO_LARGE": (413, "request exceeds the allowed limit"),
    "RESPONSE_TOO_LARGE": (413, "response exceeds the allowed limit"),
    "INTERNAL_ERROR": (500, "request could not be completed"),
}


@dataclass(frozen=True)
class Response:
    status: int
    content_type: str
    body: bytes
    extra_headers: tuple[tuple[str, str], ...] = ()


def _error(code: str) -> Response:
    status, message = ERRORS[code]
    document = {
        "schema_version": "tcw.workbench-error/v0.5",
        "status": status,
        "error": {"code": code, "message": message},
    }
    validate_document("tcw.workbench-error/v0.5", document)
    headers = (("Allow", "GET, HEAD"),) if status == 405 else ()
    return Response(
        status,
        "application/json; charset=utf-8",
        canonical_json(document),
        headers,
    )


def validate_port(value: str | int) -> int:
    """Return one allowed non-privileged TCP port."""

    try:
        port = int(value)
    except (TypeError, ValueError) as error:
        raise InputError("port must be an integer from 1024 through 65535") from error
    if isinstance(value, str) and (not value.isdecimal() or str(port) != value):
        raise InputError("port must be an integer from 1024 through 65535")
    if not MIN_PORT <= port <= MAX_PORT:
        raise InputError("port must be an integer from 1024 through 65535")
    return port


def startup_document(projection: WorkbenchProjection, port: int) -> dict[str, Any]:
    value = projection.projection
    counts = value["counts"]
    document = {
        "schema_version": "tcw.workbench-startup/v0.5",
        "status": "READY",
        "session_id": value["session_id"],
        "url": f"http://{HOST}:{port}/",
        "api_url": f"http://{HOST}:{port}/api/v0.5/workbench",
        "record_count": counts["record_count"],
        "top_level_record_count": counts["top_level_record_count"],
        "contained_record_count": counts["contained_record_count"],
        "runtime": value["runtime"],
    }
    validate_document("tcw.workbench-startup/v0.5", document)
    return document


class WorkbenchApplication:
    """Frozen routing state over an admitted record set."""

    def __init__(
        self, records: AdmittedRecords, projection: WorkbenchProjection, port: int
    ) -> None:
        self.records = records
        self.projection = projection
        self.port = validate_port(port)
        asset_root = files("tiny_corpus_workbench").joinpath("workbench_assets")
        self.static = {
            "/": (
                "text/html; charset=utf-8",
                asset_root.joinpath("index.html").read_bytes(),
            ),
            "/assets/workbench.css": (
                "text/css; charset=utf-8",
                asset_root.joinpath("workbench.css").read_bytes(),
            ),
            "/assets/workbench.js": (
                "text/javascript; charset=utf-8",
                asset_root.joinpath("workbench.js").read_bytes(),
            ),
        }
        self.artifacts = {
            descriptor["artifact_key"]: descriptor
            for detail in projection.details.values()
            for descriptor in [detail["manifest"], *detail["artifacts"]]
        }
        structured = [
            projection.projection_bytes(),
            *(projection.detail_bytes(key) for key in projection.details),
        ]
        if any(len(item) > MAX_STRUCTURED_RESPONSE for item in structured):
            raise IntegrityError(
                "workbench structured response exceeds the allowed limit"
            )

    @property
    def authority(self) -> str:
        return f"{HOST}:{self.port}"

    @property
    def origin(self) -> str:
        return f"http://{self.authority}"

    def route(self, target: str) -> Response:
        if target in self.static:
            content_type, body = self.static[target]
            return Response(200, content_type, body)
        if target == "/api/v0.5/workbench":
            return Response(
                200,
                "application/json; charset=utf-8",
                self.projection.projection_bytes(),
            )
        prefix = "/api/v0.5/records/"
        if target.startswith(prefix):
            key = target[len(prefix) :]
            if not KEY.fullmatch(key) or key not in self.projection.details:
                return _error("NOT_FOUND")
            return Response(
                200,
                "application/json; charset=utf-8",
                self.projection.detail_bytes(key),
            )
        prefix = "/api/v0.5/artifacts/"
        if target.startswith(prefix):
            key = target[len(prefix) :]
            if not KEY.fullmatch(key) or key not in self.artifacts:
                return _error("NOT_FOUND")
            descriptor = self.artifacts[key]
            try:
                body = self.records.recheck_artifact(descriptor)
            except (IntegrityError, OSError):
                return _error("ARTIFACT_CHANGED")
            if (
                descriptor["availability"] == "TOO_LARGE"
                or descriptor["size"] > MAX_ARTIFACT_CONTENT
            ):
                return _error("RESPONSE_TOO_LARGE")
            return Response(200, "text/plain; charset=utf-8", body)
        return _error("NOT_FOUND")


class WorkbenchHandler(BaseHTTPRequestHandler):
    """One sequential request handler with an explicit validation pipeline."""

    protocol_version = "HTTP/1.1"
    server_version = "tiny-corpus-workbench"
    sys_version = ""

    @property
    def application(self) -> WorkbenchApplication:
        return self.server.application  # type: ignore[attr-defined,no-any-return]

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        if code == 501 and hasattr(self, "headers"):
            self._handle()
            return
        self._send(_error("BAD_REQUEST"), head=self.command == "HEAD")

    def do_GET(self) -> None:
        self._handle()

    def do_HEAD(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_OPTIONS(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def do_PATCH(self) -> None:
        self._handle()

    def do_TRACE(self) -> None:
        self._handle()

    def _handle(self) -> None:
        try:
            response = self._validate()
            if response is None:
                response = self.application.route(self.path)
        except Exception:
            response = _error("INTERNAL_ERROR")
        self._send(response, head=self.command == "HEAD")

    def _validate(self) -> Response | None:
        host = self.headers.get_all("Host", failobj=[])
        if len(host) != 1:
            return _error("BAD_REQUEST")
        if host[0].strip(" \t") != self.application.authority:
            return _error("HOST_REJECTED")

        origins = self.headers.get_all("Origin", failobj=[])
        if len(origins) > 1:
            return _error("BAD_REQUEST")
        if origins and origins[0].strip(" \t") != self.application.origin:
            return _error("ORIGIN_REJECTED")

        target_error = self._validate_target()
        if target_error is not None:
            return target_error

        header_error = self._validate_headers()
        if header_error is not None:
            return header_error

        lengths = self.headers.get_all("Content-Length", failobj=[])
        if len(lengths) > 1:
            return _error("BAD_REQUEST")
        if lengths:
            if not lengths[0].isdecimal():
                return _error("BAD_REQUEST")
            if int(lengths[0]) > 0:
                return _error("REQUEST_TOO_LARGE")

        if self.command not in {"GET", "HEAD"}:
            return _error("METHOD_NOT_ALLOWED")
        return None

    def _validate_target(self) -> Response | None:
        raw = self.path
        try:
            encoded = raw.encode("iso-8859-1")
        except UnicodeEncodeError:
            return _error("BAD_REQUEST")
        if len(encoded) > MAX_TARGET:
            return _error("REQUEST_TOO_LARGE")
        if (
            not raw.startswith("/")
            or raw.startswith("//")
            or "?" in raw
            or "#" in raw
            or "\\" in raw
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in raw)
        ):
            return _error("BAD_REQUEST")
        index = 0
        decoded = bytearray()
        while index < len(encoded):
            if encoded[index] != ord("%"):
                decoded.append(encoded[index])
                index += 1
                continue
            if index + 2 >= len(encoded):
                return _error("BAD_REQUEST")
            pair = encoded[index + 1 : index + 3]
            if not all(chr(value) in "0123456789abcdefABCDEF" for value in pair):
                return _error("BAD_REQUEST")
            decoded.append(int(pair.decode("ascii"), 16))
            index += 3
        if (
            b"%" in decoded
            or b"\\" in decoded
            or b"?" in decoded
            or b"#" in decoded
            or any(value < 0x20 or value == 0x7F for value in decoded)
        ):
            return _error("BAD_REQUEST")
        try:
            path = decoded.decode("utf-8")
        except UnicodeDecodeError:
            return _error("BAD_REQUEST")
        if any(part in {".", ".."} for part in path.split("/")):
            return _error("BAD_REQUEST")
        if path != raw:
            return _error("BAD_REQUEST")
        return None

    def _validate_headers(self) -> Response | None:
        if self.headers.defects:
            return _error("BAD_REQUEST")
        fields = list(self.headers.raw_items())
        total = sum(
            len(name.encode("ascii", "replace"))
            + len(value.encode("iso-8859-1", "replace"))
            + 4
            for name, value in fields
        )
        if len(fields) > MAX_HEADER_FIELDS or total > MAX_HEADER_BYTES:
            return _error("REQUEST_TOO_LARGE")
        for name, value in fields:
            lower = name.lower()
            if (
                not FIELD_NAME.fullmatch(name)
                or "\r" in value
                or "\n" in value
                or lower == "forwarded"
                or lower.startswith("x-forwarded-")
                or lower == "transfer-encoding"
            ):
                return _error("BAD_REQUEST")
        return None

    def _send(self, response: Response, *, head: bool) -> None:
        try:
            self.close_connection = True
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.send_header("Connection", "close")
            for name, value in SECURITY_HEADERS:
                self.send_header(name, value)
            for name, value in response.extra_headers:
                self.send_header(name, value)
            self.end_headers()
            if not head:
                self.wfile.write(response.body)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True


class WorkbenchHTTPServer(HTTPServer):
    application: WorkbenchApplication


def create_server(
    records: AdmittedRecords, projection: WorkbenchProjection, port: int
) -> WorkbenchHTTPServer:
    """Bind one sequential server to the fixed IPv4 loopback address."""

    checked_port = validate_port(port)
    try:
        server = WorkbenchHTTPServer((HOST, checked_port), WorkbenchHandler)
    except OSError as error:
        raise InputError("workbench port is unavailable") from error
    try:
        server.application = WorkbenchApplication(records, projection, checked_port)
    except Exception:
        server.server_close()
        raise
    return server


def open_browser(url: str) -> str | None:
    """Attempt a non-authoritative browser open and return a warning if needed."""

    try:
        if webbrowser.open(url):
            return None
    except Exception as error:
        return f"browser could not be opened: {sanitize_message(error)}"
    return "browser could not be opened"
