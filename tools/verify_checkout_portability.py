from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        arguments,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="tcw-autocrlf-") as directory:
        checkout = Path(directory) / "checkout"
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

    print("verified byte-stable fixtures in a clean core.autocrlf=true checkout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
