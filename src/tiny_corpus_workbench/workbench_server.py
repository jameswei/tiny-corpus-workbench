"""Foreground loopback HTTP server for the local Workbench."""

from __future__ import annotations

import re
import secrets
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import unquote_to_bytes

from tiny_corpus_workbench.application.input_store import (
    MAX_UPLOAD_BYTES,
    SUPPORTED_EXTENSIONS,
    store_uploaded_input,
    validate_upload_filename,
)
from tiny_corpus_workbench.application.lifecycle import (
    ActionNotAvailableError,
    LifecycleBusyError,
    LifecycleNotFoundError,
    ResponseTooLargeError,
    WorkbenchLifecycleService,
)
from tiny_corpus_workbench.application.mutation_coordinator import (
    MutationCoordinator,
)
from tiny_corpus_workbench.application.observation_jobs import (
    JobInput,
    ObservationBusyError,
    ObservationJobManager,
)
from tiny_corpus_workbench.application.workbench import (
    WorkbenchState,
    WorkspaceStaleError,
    validate_workspace,
)
from tiny_corpus_workbench.canonical_json import canonical_json
from tiny_corpus_workbench.domain import (
    InputError,
    IntegrityError,
    StableError,
    sanitize_message,
)
from tiny_corpus_workbench.source import validate_source
from tiny_corpus_workbench.workbench_projection import WorkbenchProjection
from tiny_corpus_workbench.workbench_records import MAX_ARTIFACT_CONTENT


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MIN_PORT = 1024
MAX_PORT = 65535
MAX_STRUCTURED_RESPONSE = 4 * 1024 * 1024
KEY = re.compile(r"[0-9a-f]{64}\Z")

ERRORS = {
    "ACTION_TOKEN_INVALID": (403, "lifecycle action token is missing or invalid"),
    "INVALID_REQUEST": (400, "request is invalid"),
    "INVALID_SOURCE": (400, "source is invalid or unsupported"),
    "NOT_FOUND": (404, "resource was not found"),
    "METHOD_NOT_ALLOWED": (405, "method is not allowed"),
    "OBSERVATION_BUSY": (409, "one observation is already active"),
    "LIFECYCLE_BUSY": (409, "background observation is active"),
    "ACTION_NOT_AVAILABLE": (409, "lifecycle action is not available"),
    "WORKSPACE_STALE": (409, "accepted workspace state is stale"),
    "WORKSPACE_UNAVAILABLE": (409, "workspace cannot accept the request"),
    "WORKSPACE_REFRESH_FAILED": (409, "workspace refresh failed"),
    "UPLOAD_TOO_LARGE": (413, "upload exceeds the allowed limit"),
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

    def __init__(
        self,
        state: WorkbenchState,
        model_root: str | Path,
        *,
        jobs: ObservationJobManager | None = None,
    ) -> None:
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
        repository = Path(__file__).resolve().parents[2]
        guided_paths = (
            ("policy-memo-md", repository / "fixtures/golden/policy-memo.md"),
            (
                "whitespace-cleanup-md",
                repository / "fixtures/refinement/whitespace-cleanup.md",
            ),
        )
        self.guided: dict[str, tuple[Path, JobInput]] = {}
        for guided_id, fixture in guided_paths:
            identity = validate_source(fixture)
            self.guided[guided_id] = (
                fixture,
                JobInput(
                    kind="GUIDED",
                    name=identity.name,
                    media_type=identity.media_type,
                    size=identity.size,
                    sha256=identity.sha256,
                ),
            )
        coordinator = jobs.coordinator if jobs is not None else MutationCoordinator()
        self.jobs = jobs or ObservationJobManager(
            state, model_root, coordinator=coordinator
        )
        self.lifecycle = WorkbenchLifecycleService(state, coordinator)
        self.action_token = secrets.token_urlsafe(32)

    @property
    def projection(self) -> WorkbenchProjection:
        return self.state.projection

    def close(self) -> None:
        self.jobs.shutdown()

    def _jobs_response(self) -> Response:
        job = self.jobs.snapshot()
        return Response(
            200,
            "application/json; charset=utf-8",
            canonical_json(
                {
                    "capabilities": {
                        "guided": [
                            {
                                "id": guided_id,
                                "name": input_value.name,
                                "media_type": input_value.media_type,
                            }
                            for guided_id, (_, input_value) in self.guided.items()
                        ],
                        "upload": {
                            "extensions": list(SUPPORTED_EXTENSIONS),
                            "max_bytes": MAX_UPLOAD_BYTES,
                        },
                    },
                    "job": None if job is None else job.to_dict(),
                }
            ),
        )

    def _submit(self, source: Path, input_value: JobInput) -> Response:
        if self.jobs.is_busy():
            return _error("OBSERVATION_BUSY")
        try:
            validate_workspace(self.state.workspace)
        except InputError as error:
            return _error("WORKSPACE_UNAVAILABLE", message=sanitize_message(error))
        try:
            job = self.jobs.accept(source, input_value)
        except ObservationBusyError:
            return _error("OBSERVATION_BUSY")
        return Response(
            202,
            "application/json; charset=utf-8",
            canonical_json({"job": job.to_dict()}),
        )

    def _upload(self, filename: str, body: bytes) -> Response:
        if self.jobs.is_busy():
            return _error("OBSERVATION_BUSY")
        try:
            validate_upload_filename(filename)
        except InputError as error:
            message = sanitize_message(error)
            if message.startswith("unsupported media type"):
                return _error("INVALID_SOURCE", message=message)
            return _error("INVALID_REQUEST", message=message)
        try:
            stored = store_uploaded_input(self.state.workspace, filename, body)
        except InputError as error:
            code = (
                "WORKSPACE_UNAVAILABLE"
                if "workspace" in sanitize_message(error)
                else "INVALID_SOURCE"
            )
            return _error(code, message=sanitize_message(error))
        except (IntegrityError, OSError) as error:
            return _error("WORKSPACE_UNAVAILABLE", message=sanitize_message(error))
        return self._submit(
            stored.path,
            JobInput(
                kind="UPLOAD",
                name=stored.name,
                media_type=stored.media_type,
                size=stored.size,
                sha256=stored.sha256,
            ),
        )

    def route(
        self,
        target: str,
        *,
        method: str = "GET",
        body: bytes = b"",
        upload_filename: str | None = None,
        action_tokens: tuple[str, ...] = (),
    ) -> Response:
        path, separator, _ = target.partition("?")
        if path == "/api/observation-jobs/upload" and separator:
            target = path
        guided_match = re.fullmatch(r"/api/observation-jobs/guided/([^/]+)", target)
        if guided_match is not None:
            guided = self.guided.get(guided_match.group(1))
            if guided is None:
                return _error("NOT_FOUND")
            if method != "POST":
                return _error("METHOD_NOT_ALLOWED", allow="POST")
            if body:
                return _error("INVALID_REQUEST")
            return self._submit(*guided)
        if target == "/api/observation-jobs/guided":
            return _error("NOT_FOUND")
        lifecycle_action = _lifecycle_action(target)
        if lifecycle_action is not None:
            if method != "POST":
                return _error("METHOD_NOT_ALLOWED", allow="POST")
            if body:
                return _error("INVALID_REQUEST")
            if not self._valid_action_token(action_tokens):
                return _error("ACTION_TOKEN_INVALID")
            return self._run_lifecycle(lifecycle_action)
        if (
            path == "/api/lifecycle"
            or (
                path.startswith("/api/lifecycle/")
                and target != "/api/lifecycle/action-token"
            )
        ):
            return _error("NOT_FOUND")
        if target == "/api/observation-jobs/upload":
            if method != "POST":
                return _error("METHOD_NOT_ALLOWED", allow="POST")
            if upload_filename is None or not body:
                return _error("INVALID_REQUEST")
            return self._upload(upload_filename, body)
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
        if target == "/api/lifecycle/action-token":
            return Response(
                200,
                "application/json; charset=utf-8",
                canonical_json({"action_token": self.action_token}),
                (("Cache-Control", "no-store"),),
            )
        if target in self.static:
            content_type, body = self.static[target]
            return Response(200, content_type, body)
        if target == "/api/workbench":
            return Response(
                200,
                "application/json; charset=utf-8",
                self.state.projection_bytes(),
            )
        if target == "/api/observation-jobs":
            return self._jobs_response()
        projection = self.projection
        for prefix, values in (
            ("/api/records/", projection.details),
            ("/api/artifacts/", projection.artifact_contents),
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
                    projection.detail_bytes(key),
                )
            body = projection.artifact_contents[key]
            if len(body) > MAX_ARTIFACT_CONTENT:
                return _error("RESPONSE_TOO_LARGE")
            return Response(200, "text/plain; charset=utf-8", body)
        return _error("NOT_FOUND")

    def _valid_action_token(self, values: tuple[str, ...]) -> bool:
        if len(values) != 1:
            return False
        try:
            candidate = values[0].encode("ascii", errors="strict")
        except UnicodeEncodeError:
            return False
        return secrets.compare_digest(candidate, self.action_token.encode("ascii"))

    def _run_lifecycle(self, action: tuple[str, ...]) -> Response:
        try:
            operation, *arguments = action
            if operation == "diagnose":
                value = self.lifecycle.diagnose(arguments[0])
            elif operation == "proposal":
                value = self.lifecycle.create_proposal(arguments[0], arguments[1])
            elif operation == "approve":
                value = self.lifecycle.approve(arguments[0])
            else:
                value = self.lifecycle.reject(arguments[0])
            body = canonical_json(value)
            if len(body) > MAX_STRUCTURED_RESPONSE:
                return _error("RESPONSE_TOO_LARGE")
            return Response(200, "application/json; charset=utf-8", body)
        except LifecycleBusyError as error:
            return _error("LIFECYCLE_BUSY", message=sanitize_message(error))
        except ActionNotAvailableError as error:
            return _error("ACTION_NOT_AVAILABLE", message=sanitize_message(error))
        except LifecycleNotFoundError as error:
            return _error("NOT_FOUND", message=sanitize_message(error))
        except WorkspaceStaleError as error:
            return _error("WORKSPACE_STALE", message=sanitize_message(error))
        except ResponseTooLargeError as error:
            return _error("RESPONSE_TOO_LARGE", message=sanitize_message(error))
        except Exception:
            return _error("INTERNAL_ERROR")


class WorkbenchHandler(BaseHTTPRequestHandler):
    """Sequential request handler for the trusted-local learning tool."""

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
        unsupported = f"Unsupported method ({self.command!r})"
        if code == HTTPStatus.NOT_IMPLEMENTED and message == unsupported:
            self._send(
                self._route(self.path, method=self.command),
                head=self.command == "HEAD",
            )
            return
        super().send_error(code, message, explain)

    def do_GET(self) -> None:
        self._send(self._route(self.path, method="GET"), head=False)

    def do_HEAD(self) -> None:
        self._send(self._route(self.path, method="HEAD"), head=True)

    def do_POST(self) -> None:
        path, separator, query = self.path.partition("?")
        lengths = self.headers.get_all("Content-Length", [])
        transfers = self.headers.get_all("Transfer-Encoding", [])
        guided_match = re.fullmatch(
            r"/api/observation-jobs/guided/([^/]+)", path
        )
        empty_body_route = (
            path == "/api/workbench/refresh"
            or (
                guided_match is not None
                and guided_match.group(1) in self.application.guided
            )
            or _lifecycle_action(self.path) is not None
        )
        if empty_body_route:
            declared = (
                _bounded_decimal(lengths[0], 0)
                if len(lengths) == 1
                and re.fullmatch(r"[0-9]+", lengths[0])
                else None
            )
            if (
                transfers
                or len(lengths) > 1
                or (lengths and not re.fullmatch(r"[0-9]+", lengths[0]))
                or (lengths and declared != 0)
                or separator
            ):
                self._send(_error("INVALID_REQUEST"), head=False)
                return
            self._send(
                self._route(
                    path,
                    method=self.command,
                    action_tokens=tuple(
                        self.headers.get_all("X-TCW-Action-Token", [])
                    ),
                ),
                head=False,
            )
            return
        if path == "/api/observation-jobs/upload":
            if (
                transfers
                or len(lengths) != 1
                or not re.fullmatch(r"[0-9]+", lengths[0])
            ):
                self._send(_error("INVALID_REQUEST"), head=False)
                return
            length = _bounded_decimal(lengths[0], MAX_UPLOAD_BYTES)
            if length is None:
                self._send(_error("UPLOAD_TOO_LARGE"), head=False)
                return
            if length == 0:
                self._send(_error("INVALID_REQUEST"), head=False)
                return
            if self.application.jobs.is_busy():
                self._send(_error("OBSERVATION_BUSY"), head=False)
                return
            filename = _upload_filename(query) if separator else None
            if filename is None:
                self._send(_error("INVALID_REQUEST"), head=False)
                return
            body = self.rfile.read(length)
            if len(body) != length:
                self._send(_error("INVALID_REQUEST"), head=False)
                return
            self._send(
                self._route(
                    path,
                    method=self.command,
                    body=body,
                    upload_filename=filename,
                ),
                head=False,
            )
            return
        self._send(
            self._route(self.path, method=self.command),
            head=False,
        )

    def _do_non_post(self) -> None:
        self._send(
            self._route(self.path, method=self.command),
            head=False,
        )

    do_PUT = _do_non_post
    do_PATCH = _do_non_post
    do_DELETE = _do_non_post
    do_OPTIONS = _do_non_post

    def _route(self, target: str, **arguments: object) -> Response:
        try:
            return self.application.route(target, **arguments)
        except Exception:
            return _error("INTERNAL_ERROR")

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

    def server_close(self) -> None:
        self.application.close()
        super().server_close()


def create_server(
    state: WorkbenchState,
    port: int,
    model_root: str | Path = Path(".cache/docling/models"),
) -> WorkbenchHTTPServer:
    server = WorkbenchHTTPServer((HOST, validate_port(port)), WorkbenchHandler)
    try:
        server.application = WorkbenchApplication(state, model_root)
    except Exception:
        HTTPServer.server_close(server)
        raise
    return server


def _upload_filename(query: str) -> str | None:
    """Decode exactly one strict UTF-8 filename query field."""

    if not query or "&" in query or query.count("=") != 1:
        return None
    try:
        query.encode("ascii", errors="strict")
    except UnicodeEncodeError:
        return None
    raw_name, raw_value = query.split("=", 1)
    if not raw_name or not raw_value:
        return None
    for raw in (raw_name, raw_value):
        if re.search(r"%(?![0-9A-Fa-f]{2})", raw):
            return None
    try:
        name = unquote_to_bytes(raw_name).decode("utf-8", errors="strict")
        value = unquote_to_bytes(raw_value).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    if name != "filename" or not value:
        return None
    return value


def _bounded_decimal(value: str, maximum: int) -> int | None:
    """Parse decimal framing without converting an unbounded digit string."""

    normalized = value.lstrip("0") or "0"
    limit = str(maximum)
    if len(normalized) > len(limit) or (
        len(normalized) == len(limit) and normalized > limit
    ):
        return None
    return int(normalized)


def _lifecycle_action(target: str) -> tuple[str, ...] | None:
    """Return one exact lifecycle action for a query-free canonical route."""

    if "?" in target:
        return None
    patterns = (
        (
            re.fullmatch(r"/api/lifecycle/diagnoses/([0-9a-f]{64})", target),
            "diagnose",
        ),
        (
            re.fullmatch(
                r"/api/lifecycle/proposals/([0-9a-f]{64})/([0-9a-f]{64})",
                target,
            ),
            "proposal",
        ),
        (
            re.fullmatch(
                r"/api/lifecycle/proposals/([0-9a-f]{64})/(approve|reject)",
                target,
            ),
            "resolution",
        ),
    )
    for match, operation in patterns:
        if match is None:
            continue
        groups = match.groups()
        if operation == "resolution":
            return (groups[1], groups[0])
        return (operation, *groups)
    return None


def open_browser(url: str) -> str | None:
    try:
        opened = webbrowser.open(url)
    except Exception:
        opened = False
    if opened:
        return None
    return f"could not open a browser; visit {url}"
