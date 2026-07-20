from __future__ import annotations

from pathlib import Path

from markitdown import MarkItDown, StreamInfo


HINTS = {
    ".md": StreamInfo(extension=".md", mimetype="text/markdown", charset="utf-8"),
    ".txt": StreamInfo(extension=".txt", mimetype="text/plain", charset="utf-8"),
}


def convert(source: Path, destination: Path) -> None:
    kwargs = {"stream_info": HINTS[source.suffix.lower()]} if source.suffix.lower() in HINTS else {}
    result = MarkItDown(enable_plugins=False).convert_local(source, **kwargs)
    if not result.markdown.strip():
        raise RuntimeError("MarkItDown emitted empty Markdown")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "document.md").write_text(result.markdown, "utf-8", newline="\n")
