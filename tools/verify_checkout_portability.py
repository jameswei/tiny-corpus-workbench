from __future__ import annotations

import hashlib
import json
import os
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(
    *arguments: str,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            arguments,
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
    except subprocess.CalledProcessError as error:
        if error.stdout:
            sys.stderr.buffer.write(error.stdout)
        raise


def _export_worktree(destination: Path) -> None:
    paths = run(
        "git",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        cwd=ROOT,
    ).stdout.decode("utf-8").splitlines()
    for relative in paths:
        source = ROOT / relative
        if not source.is_file() or source.is_symlink():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _inventory(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def _json_line(completed: subprocess.CompletedProcess[bytes]) -> dict:
    sys.stdout.buffer.write(completed.stdout)
    lines = completed.stdout.decode("utf-8").splitlines()
    if len(lines) != 1:
        raise RuntimeError("documented command did not print one compact JSON line")
    value = json.loads(lines[0])
    if not isinstance(value, dict):
        raise RuntimeError("documented command result is not a JSON object")
    return value


def _record_root(result: dict) -> Path:
    return Path(result["manifest"]).parent


def _run_workflows(export: Path, runtime: Path, env: dict[str, str]) -> Path:
    corpus_command = (sys.executable, "-m", "tiny_corpus_workbench")
    observation = _record_root(
        _json_line(
            run(
                *corpus_command,
                "observe",
                str(export / "fixtures/refinement/whitespace-cleanup.md"),
                "--output-root",
                str(runtime / "observations"),
                cwd=export,
                env=env,
            )
        )
    )
    _json_line(
        run(*corpus_command, "verify", str(observation), cwd=export, env=env)
    )
    diagnosis = _record_root(
        _json_line(
            run(
                *corpus_command,
                "diagnose",
                str(observation),
                "--output-root",
                str(runtime / "diagnoses"),
                cwd=export,
                env=env,
            )
        )
    )
    _json_line(
        run(
            *corpus_command,
            "verify-diagnosis",
            str(diagnosis),
            "--subject",
            str(observation),
            cwd=export,
            env=env,
        )
    )
    finding_set = json.loads((diagnosis / "findings.json").read_text("utf-8"))
    finding_id = next(
        item["finding_id"]
        for item in finding_set["findings"]
        if item["rule_id"] == "TCW-D009"
    )
    proposal = runtime / "proposal.json"
    _json_line(
        run(
            *corpus_command,
            "draft-refinement",
            str(diagnosis),
            "--finding",
            finding_id,
            "--base",
            str(observation),
            "--output",
            str(proposal),
            cwd=export,
            env=env,
        )
    )
    refinement = _record_root(
        _json_line(
            run(
                *corpus_command,
                "resolve-refinement",
                str(proposal),
                "--diagnosis",
                str(diagnosis),
                "--base",
                str(observation),
                "--approve",
                "--output-root",
                str(runtime / "refinements"),
                cwd=export,
                env=env,
            )
        )
    )
    _json_line(
        run(
            *corpus_command,
            "verify-refinement",
            str(refinement),
            "--diagnosis",
            str(diagnosis),
            "--base",
            str(observation),
            cwd=export,
            env=env,
        )
    )

    corpus_inputs = runtime / "corpus-inputs"
    corpus_inputs.mkdir()
    corpus_source = corpus_inputs / "corpus-source.md"
    shutil.copyfile(export / "fixtures/golden/policy-memo.md", corpus_source)
    corpus_spec = corpus_inputs / "corpus.json"
    corpus_spec.write_text(
        json.dumps(
            {
                "corpus_id": "clean-export-corpus",
                "members": [
                    {
                        "family": "policy-memo",
                        "format": "md",
                        "member_id": "policy-memo-md",
                        "source": "corpus-source.md",
                    }
                ],
                "title": "Clean export model-free corpus",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        "utf-8",
    )
    unused_models = runtime / "unused-models"
    unused_models.mkdir()
    corpus = _record_root(
        _json_line(
            run(
                *corpus_command,
                "inspect",
                str(corpus_spec),
                "--output-root",
                str(runtime / "corpora"),
                "--docling-artifacts",
                str(unused_models),
                cwd=export,
                env=env,
            )
        )
    )
    _json_line(
        run(
            *corpus_command,
            "verify-corpus",
            str(corpus),
            "--spec",
            str(corpus_spec),
            cwd=export,
            env=env,
        )
    )
    return corpus


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _inspect_workbench(
    export: Path,
    record: Path,
    env: dict[str, str],
) -> None:
    port = _available_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tiny_corpus_workbench",
            "workbench",
            str(record),
            "--port",
            str(port),
            "--no-open",
        ],
        cwd=export,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 20
        line = ""
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            readable, _, _ = select.select([process.stdout], [], [], 0.2)
            if readable:
                line = process.stdout.readline()
                break
        if not line:
            stderr = process.stderr.read() if process.poll() is not None else ""
            raise RuntimeError(f"workbench did not start from clean export: {stderr}")
        if line != f"http://127.0.0.1:{port}/\n":
            raise RuntimeError("workbench serving address differs from its contract")
        for route, expected_type in (
            ("/", "text/html"),
            ("/api/workbench", "application/json"),
        ):
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}{route}"
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status != 200 or expected_type not in response.headers[
                    "Content-Type"
                ]:
                    raise RuntimeError(f"unexpected workbench response for {route}")
                if not response.read():
                    raise RuntimeError(f"empty workbench response for {route}")
        print(line, end="")
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
        if process.returncode != 0:
            stderr = process.stderr.read()
            raise RuntimeError(f"workbench stopped with {process.returncode}: {stderr}")


def _verify_clean_export(parent: Path) -> None:
    export = parent / "export"
    runtime = parent / "runtime"
    export.mkdir()
    runtime.mkdir()
    export = export.resolve()
    runtime = runtime.resolve()
    _export_worktree(export)
    before = _inventory(export)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(export / "src"), str(export)))
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    commands = (
        (
            "tools/validate_workbench_assets.py",
            "src/tiny_corpus_workbench/workbench_assets",
        ),
        ("tools/validate_site.py", "site"),
        ("tools/verify_fixtures.py",),
        ("tools/verify_corpus_specs.py",),
    )
    for arguments in commands:
        completed = run(sys.executable, *arguments, cwd=export, env=env)
        sys.stdout.buffer.write(completed.stdout)
    corpus = _run_workflows(export, runtime, env)
    _inspect_workbench(export, corpus, env)
    after = _inventory(export)
    if after != before:
        raise SystemExit("clean-export validation changed the exported repository tree")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="tcw-autocrlf-") as directory:
        temporary = Path(directory)
        checkout = temporary / "checkout"
        run(
            "git",
            "-c",
            "core.autocrlf=true",
            "clone",
            "--no-hardlinks",
            "--quiet",
            str(ROOT),
            str(checkout),
            cwd=ROOT,
        )
        run("git", "config", "core.autocrlf", "true", cwd=checkout)

        fixture_paths = run("git", "ls-files", "fixtures", cwd=checkout).stdout.decode(
            "utf-8"
        ).splitlines()
        for relative in fixture_paths:
            blob = run("git", "show", f"HEAD:{relative}", cwd=checkout).stdout
            checked_out = (checkout / relative).read_bytes()
            if checked_out != blob:
                raise SystemExit(
                    f"core.autocrlf checkout changed committed fixture bytes: {relative}"
                )

        commands = (
            ("tools/verify_fixtures.py",),
            ("tools/generate_fixtures.py", "--check"),
            ("tools/generate_diagnosis_fixtures.py", "--check"),
            ("tools/generate_refinement_fixtures.py", "--check"),
        )
        for arguments in commands:
            completed = run(sys.executable, *arguments, cwd=checkout)
            sys.stdout.buffer.write(completed.stdout)

        status = run("git", "status", "--porcelain", cwd=checkout).stdout
        if status:
            raise SystemExit(
                "core.autocrlf portability verification changed the checkout:\n"
                + status.decode("utf-8")
            )

        _verify_clean_export(temporary)

    print(
        "verified byte-stable fixtures plus workflows and workbench startup "
        "in a clean exported tree"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
