from __future__ import annotations

import socket
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from tiny_corpus_workbench.application.workbench import WorkbenchState
from tiny_corpus_workbench.workbench_records import admit_records
from tiny_corpus_workbench.workbench_server import create_server


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@dataclass
class RawResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class ServerHarness:
    def __init__(self, root=None, *, workspace=None) -> None:
        self.temporary = None
        self.records = None
        if workspace is not None:
            self.workspace = Path(workspace)
        else:
            if root is None:
                raise ValueError("root or workspace is required")
            self._copy_record_into_workspace(root)
        self.state = WorkbenchState(self.workspace)
        self.projection = self.state.projection
        self.port = available_port()
        self.server = create_server(self.state, self.port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _copy_record_into_workspace(self, root) -> None:
        manifest_names = {
            "manifest.json": "extraction-observatory",
            "diagnosis-manifest.json": "evidence-based-diagnosis",
            "refinement-manifest.json": "controlled-revisions",
            "corpus-manifest.json": "corpus-inspection",
        }
        source = Path(root)
        manifest = next(name for name in manifest_names if (source / name).is_file())
        self.temporary = tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        )
        self.workspace = Path(self.temporary.name)
        copied = self.workspace / manifest_names[manifest] / source.name
        copied.parent.mkdir()
        shutil.copytree(source, copied)
        self.records = admit_records([copied])

    @property
    def authority(self) -> str:
        return f"127.0.0.1:{self.port}"

    @property
    def origin(self) -> str:
        return f"http://{self.authority}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.temporary is not None:
            self.temporary.cleanup()

    def request(
        self,
        target: str = "/",
        *,
        method: str = "GET",
        headers: list[tuple[str, str]] | None = None,
        raw_header_lines: list[bytes] | None = None,
        body: bytes = b"",
    ) -> RawResponse:
        fields = [("Host", self.authority)] if headers is None else headers
        request = (
            f"{method} {target} HTTP/1.1\r\n".encode("ascii")
            + b"".join(
                f"{name}: {value}\r\n".encode("iso-8859-1")
                for name, value in fields
            )
            + b"".join(
                line + b"\r\n" for line in (raw_header_lines or [])
            )
            + b"Connection: close\r\n\r\n"
            + body
        )
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as client:
            client.sendall(request)
            chunks = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        raw = b"".join(chunks)
        head, _, response_body = raw.partition(b"\r\n\r\n")
        lines = head.decode("iso-8859-1").split("\r\n")
        response_headers = {}
        for line in lines[1:]:
            name, value = line.split(":", 1)
            response_headers[name.lower()] = value.strip()
        return RawResponse(
            int(lines[0].split()[1]),
            response_headers,
            response_body,
        )
