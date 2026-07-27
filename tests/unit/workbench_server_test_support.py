from __future__ import annotations

import socket
import threading
from dataclasses import dataclass

from tiny_corpus_workbench.workbench_projection import build_projection
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
    def __init__(self, root) -> None:
        self.records = admit_records([root])
        self.projection = build_projection(self.records)
        self.port = available_port()
        self.server = create_server(self.records, self.projection, self.port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

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
