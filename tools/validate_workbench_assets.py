"""Validate the bundled workbench assets without network or build tools."""

from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


EXPECTED = {"index.html", "workbench.css", "workbench.js"}
REMOTE = re.compile(r"""(?:https?:)?//|url\s*\(\s*['"]?(?!data:)""", re.IGNORECASE)
FORBIDDEN_JS = (
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "document.write",
    "eval(",
    "new Function",
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "serviceWorker",
    "WebSocket",
    "EventSource",
    "window.open",
)


class AssetHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attributes: list[tuple[str, str, str]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.tags.append(tag)
        for name, value in attrs:
            if value is not None:
                self.attributes.append((tag, name, value))


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    if not root.is_dir():
        return [f"asset directory does not exist: {root}"]
    present = {path.name for path in root.iterdir() if path.is_file()}
    if present != EXPECTED:
        errors.append(
            f"asset inventory must be exactly {sorted(EXPECTED)}; got {sorted(present)}"
        )
    if errors:
        return errors

    html = (root / "index.html").read_text("utf-8")
    css = (root / "workbench.css").read_text("utf-8")
    js = (root / "workbench.js").read_text("utf-8")
    parser = AssetHTMLParser()
    parser.feed(html)

    required_tags = {"header", "nav", "main", "section", "h1", "h2"}
    missing_tags = required_tags - set(parser.tags)
    if missing_tags:
        errors.append(f"missing semantic HTML tags: {sorted(missing_tags)}")
    if ("a", "class", "skip-link") not in parser.attributes:
        errors.append("missing keyboard skip link")
    if ("div", "role", "status") not in parser.attributes:
        errors.append("missing aria-live status region")
    if ("div", "aria-live", "polite") not in parser.attributes:
        errors.append("missing polite aria-live region")
    for tag, name, value in parser.attributes:
        if name in {"src", "href"} and not (
            value.startswith("/") or value.startswith("#")
        ):
            errors.append(f"non-local {tag} {name}: {value}")
        if name.startswith("on"):
            errors.append(f"inline event handler is forbidden: {name}")
    if "<script" in html and 'src="/assets/workbench.js"' not in html:
        errors.append("scripts must use only the bundled workbench.js")

    for name, content in (("index.html", html), ("workbench.css", css), ("workbench.js", js)):
        if REMOTE.search(content):
            errors.append(f"{name} contains a remote or protocol-relative resource")
    for token in FORBIDDEN_JS:
        if token in js:
            errors.append(f"workbench.js contains forbidden capability: {token}")
    for required in (
        'const API_ROOT = "/api/v0.5"',
        "document.createElement",
        ".textContent",
        "prefers-reduced-motion",
    ):
        source = js if required != "prefers-reduced-motion" else css
        if required not in source:
            errors.append(f"missing required asset contract: {required}")
    if re.search(r"fetch\s*\(\s*[^`'\"]", js):
        errors.append("fetch targets must be visibly rooted in a local literal")
    if "href =" in js or "location" in js:
        errors.append("JavaScript navigation is forbidden")
    if "@import" in css:
        errors.append("CSS imports are forbidden")
    if ":focus-visible" not in css:
        errors.append("visible keyboard focus styling is missing")
    if "@media (max-width:" not in css:
        errors.append("narrow-screen styling is missing")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("asset_directory", type=Path)
    args = parser.parse_args(argv)
    errors = validate(args.asset_directory)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Validated 3 bundled workbench assets: local, build-free, and safe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
