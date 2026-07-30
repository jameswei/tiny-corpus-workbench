"""Foreground loopback HTTP server for the read-only local Workbench."""

from __future__ import annotations

import re
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.resources import files

from tiny_corpus_workbench.canonical_json import canonical_json
from tiny_corpus_workbench.application.workbench import WorkbenchState
from tiny_corpus_workbench.domain import InputError, StableError
from tiny_corpus_workbench.workbench_projection import WorkbenchProjection
from tiny_corpus_workbench.workbench_records import MAX_ARTIFACT_CONTENT


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MIN_PORT = 1024
MAX_PORT = 65535
MAX_STRUCTURED_RESPONSE = 4 * 1024 * 1024
KEY = re.compile(r"[0-9a-f]{64}\Z")

ERRORS = {
    "INVALID_REQUEST": (400, "request body must be empty"),
    "NOT_FOUND": (404, "resource was not found"),
    "METHOD_NOT_ALLOWED": (405, "method is not allowed"),
    "WORKSPACE_REFRESH_FAILED": (409, "workspace refresh failed"),
    "RESPONSE_TOO_LARGE": (413, "response exceeds the allowed limit"),
    "INTERNAL_ERROR": (500, "request could not be completed"),
}


@dataclass(frozen=True)
class Response:
    status: int
    content_type: str
    body: bytes
    headers: tuple[tuple[str, str], ...] = ()


def _error(
    code: str, *, allow: str | None = None, message: str | None = None
) -> Response:
    status, default_message = ERRORS[code]
    headers = (("Allow", allow),) if allow is not None else ()
    return Response(
        status,
        "application/json; charset=utf-8",
        canonical_json(StableError(code, message or default_message).to_dict()),
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


def serving_url(port: int) -> str:
    return f"http://{HOST}:{validate_port(port)}/"


class WorkbenchApplication:
    """Routing over one transactionally refreshed workspace state."""

    def __init__(self, state: WorkbenchState) -> None:
        self.state = state
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
        structured = [
            state.projection_bytes(),
            *(state.projection.detail_bytes(key) for key in state.projection.details),
        ]
        if any(len(value) > MAX_STRUCTURED_RESPONSE for value in structured):
            raise InputError("workbench response exceeds the allowed limit")

    @property
    def projection(self) -> WorkbenchProjection:
        return self.state.projection

    def route(self, target: str, *, method: str = "GET", body: bytes = b"") -> Response:
        if target == "/api/workbench/refresh":
            if method != "POST":
                return _error("METHOD_NOT_ALLOWED", allow="POST")
            if body:
                return _error("INVALID_REQUEST")
            result = self.state.refresh()
            if result.succeeded:
                return Response(204, "application/json; charset=utf-8", b"")
            return _error(
                "WORKSPACE_REFRESH_FAILED",
                message=result.message,
            )
        if method not in {"GET", "HEAD"}:
            return _error("METHOD_NOT_ALLOWED", allow="GET, HEAD")
        if target in self.static:
            content_type, body = self.static[target]
            return Response(200, content_type, body)
        if target == "/api/workbench":
            return Response(
                200,
                "application/json; charset=utf-8",
                self.state.projection_bytes(),
            )
        for prefix, values in (
            ("/api/records/", self.projection.details),
            ("/api/artifacts/", self.projection.artifact_contents),
        ):
            if not target.startswith(prefix):
                continue
            key = target[len(prefix) :]
            if not KEY.fullmatch(key) or key not in values:
                return _error("NOT_FOUND")
            if prefix == "/api/records/":
                return Response(
                    200,
                    "application/json; charset=utf-8",
                    self.projection.detail_bytes(key),
                )
            body = self.projection.artifact_contents[key]
            if len(body) > MAX_ARTIFACT_CONTENT:
                return _error("RESPONSE_TOO_LARGE")
            return Response(200, "text/plain; charset=utf-8", body)
        return _error("NOT_FOUND")


class WorkbenchHandler(BaseHTTPRequestHandler):
    """Sequential GET/HEAD handler for the trusted-local learning tool."""

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
        self._send(
            _error("METHOD_NOT_ALLOWED", allow="GET, HEAD"),
            head=self.command == "HEAD",
        )

    def do_GET(self) -> None:
        self._send(self.application.route(self.path, method="GET"), head=False)

    def do_HEAD(self) -> None:
        self._send(self.application.route(self.path, method="HEAD"), head=True)

    def do_POST(self) -> None:
        if self.path == "/api/workbench/refresh":
            lengths = self.headers.get_all("Content-Length", [])
            transfers = self.headers.get_all("Transfer-Encoding", [])
            if transfers or len(lengths) > 1 or (lengths and lengths[0] != "0"):
                self._send(_error("INVALID_REQUEST"), head=False)
                return
        self._send(
            self.application.route(self.path, method=self.command),
            head=False,
        )

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST

    def _send(self, response: Response, *, head: bool) -> None:
        self.close_connection = True
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.send_header("Connection", "close")
        for name, value in response.headers:
            self.send_header(name, value)
        self.end_headers()
        if not head:
            self.wfile.write(response.body)


class WorkbenchHTTPServer(HTTPServer):
    application: WorkbenchApplication


def create_server(
    state: WorkbenchState, port: int
) -> WorkbenchHTTPServer:
    server = WorkbenchHTTPServer((HOST, validate_port(port)), WorkbenchHandler)
    server.application = WorkbenchApplication(state)
    return server


def open_browser(url: str) -> str | None:
    try:
        opened = webbrowser.open(url)
    except Exception:
        opened = False
    if opened:
        return None
    return f"could not open a browser; visit {url}"
