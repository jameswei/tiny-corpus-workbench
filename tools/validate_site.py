#!/usr/bin/env python3
"""Smoke-check the authored static project website."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


EXPECTED_FILES = {
    "404.html",
    "assets/favicon.svg",
    "index.html",
    "styles.css",
}
CANONICAL_URL = "https://lifeplayer.space/tiny-corpus-workbench/"
FORBIDDEN_ELEMENTS = {
    "button",
    "embed",
    "form",
    "iframe",
    "input",
    "object",
    "script",
    "select",
    "textarea",
}
REFERENCE_ATTRIBUTES = {"href", "src"}


@dataclass(frozen=True, order=True)
class Issue:
    path: str
    line: int
    message: str


@dataclass(frozen=True)
class Reference:
    line: int
    element: str
    attribute: str
    value: str


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[int, str, dict[str, str]]] = []
        self.ids: dict[str, list[int]] = {}
        self.references: list[Reference] = []
        self.titles: list[list[int | str]] = []
        self._title_index: int | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._record(tag, attrs)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._record(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._title_index = None

    def handle_data(self, data: str) -> None:
        if self._title_index is not None:
            self.titles[self._title_index][1] += data

    def _record(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line = self.getpos()[0]
        tag = tag.lower()
        values = {name.lower(): value or "" for name, value in attrs}
        self.elements.append((line, tag, values))
        if tag == "title":
            self.titles.append([line, ""])
            self._title_index = len(self.titles) - 1
        if identifier := values.get("id"):
            self.ids.setdefault(identifier, []).append(line)
        for attribute in REFERENCE_ATTRIBUTES:
            if attribute in values:
                self.references.append(
                    Reference(line, tag, attribute, values[attribute].strip())
                )


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _inventory(site: Path) -> tuple[set[str], list[Issue]]:
    found: set[str] = set()
    issues: list[Issue] = []
    if not site.is_dir():
        return found, [Issue(".", 1, "site directory does not exist")]
    for directory, dirnames, filenames in os.walk(site, followlinks=False):
        base = Path(directory)
        for name in sorted(dirnames + filenames):
            path = base / name
            relative = path.relative_to(site).as_posix()
            if path.is_symlink():
                issues.append(Issue(relative, 1, "symbolic links are not allowed"))
                continue
            if path.is_file():
                found.add(relative)
    for missing in sorted(EXPECTED_FILES - found):
        issues.append(Issue(missing, 1, "expected regular file is missing"))
    for unexpected in sorted(found - EXPECTED_FILES):
        issues.append(Issue(unexpected, 1, "unexpected file in site inventory"))
    return found, issues


def _parse_page(path: Path, relative: str) -> tuple[PageParser | None, str, list[Issue]]:
    issues: list[Issue] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        return None, "", [Issue(relative, 1, f"cannot read UTF-8 HTML: {error}")]
    parser = PageParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as error:  # HTMLParser errors are input-dependent.
        issues.append(Issue(relative, 1, f"cannot parse HTML: {error}"))
        return None, text, issues
    return parser, text, issues


def _metadata_issues(relative: str, parser: PageParser) -> list[Issue]:
    issues: list[Issue] = []
    html = [(line, attrs) for line, tag, attrs in parser.elements if tag == "html"]
    if not html or not html[0][1].get("lang", "").strip():
        issues.append(Issue(relative, html[0][0] if html else 1, "html lang is required"))

    metas = [(line, attrs) for line, tag, attrs in parser.elements if tag == "meta"]
    if not any(attrs.get("charset", "").lower() == "utf-8" for _, attrs in metas):
        issues.append(Issue(relative, 1, "UTF-8 charset metadata is required"))
    if not any(
        attrs.get("name", "").lower() == "viewport" and attrs.get("content", "")
        for _, attrs in metas
    ):
        issues.append(Issue(relative, 1, "viewport metadata is required"))
    if not any(
        attrs.get("name", "").lower() == "description" and attrs.get("content", "").strip()
        for _, attrs in metas
    ):
        issues.append(Issue(relative, 1, "description metadata is required"))

    if len(parser.titles) != 1 or not str(parser.titles[0][1]).strip():
        issues.append(
            Issue(
                relative,
                int(parser.titles[0][0]) if parser.titles else 1,
                "exactly one non-empty title is required",
            )
        )
    mains = [line for line, tag, _ in parser.elements if tag == "main"]
    if len(mains) != 1:
        issues.append(Issue(relative, mains[0] if mains else 1, "exactly one main is required"))
    headings = [line for line, tag, _ in parser.elements if tag == "h1"]
    if len(headings) != 1:
        issues.append(Issue(relative, headings[0] if headings else 1, "exactly one h1 is required"))
    return issues


def _policy_issues(relative: str, parser: PageParser) -> list[Issue]:
    issues: list[Issue] = []
    canonical: list[tuple[int, str]] = []
    for line, tag, attrs in parser.elements:
        if tag in FORBIDDEN_ELEMENTS:
            issues.append(Issue(relative, line, f"forbidden element: {tag}"))
        for name in attrs:
            if name.startswith("on"):
                issues.append(Issue(relative, line, f"event-handler attribute is forbidden: {name}"))
        if tag == "link":
            rel = {token.lower() for token in attrs.get("rel", "").split()}
            href = attrs.get("href", "")
            if "canonical" in rel:
                canonical.append((line, href))
            if "stylesheet" in rel and urlsplit(href).scheme:
                issues.append(Issue(relative, line, "external style sheets are forbidden"))
            if any(token in rel for token in {"preconnect", "dns-prefetch", "modulepreload"}):
                issues.append(Issue(relative, line, "external dependency hint is forbidden"))
    if len(canonical) != 1 or canonical[0][1] != CANONICAL_URL:
        issues.append(
            Issue(relative, canonical[0][0] if canonical else 1, "canonical URL is incorrect")
        )
    if relative == "404.html":
        robots = [
            (line, attrs.get("content", "").lower())
            for line, tag, attrs in parser.elements
            if tag == "meta" and attrs.get("name", "").lower() == "robots"
        ]
        if not any("noindex" in content.split(",") for _, content in robots):
            issues.append(Issue(relative, robots[0][0] if robots else 1, "404 page must use noindex"))
        home_links = [
            reference
            for reference in parser.references
            if reference.element == "a" and reference.value == CANONICAL_URL
        ]
        if not home_links:
            issues.append(Issue(relative, 1, "404 page must use the canonical HTTPS home link"))
    return issues


def _reference_issues(
    site: Path,
    relative: str,
    parser: PageParser,
    page_ids: dict[str, set[str]],
) -> list[Issue]:
    issues: list[Issue] = []
    source = site / relative
    for identifier, lines in parser.ids.items():
        for line in lines[1:]:
            issues.append(Issue(relative, line, f"duplicate id: {identifier}"))
    for reference in parser.references:
        value = reference.value
        if not value:
            continue
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc:
            if reference.element == "a":
                if parsed.scheme != "https" or not parsed.netloc:
                    issues.append(Issue(relative, reference.line, "external navigation must use HTTPS"))
            elif reference.element == "link" and value == CANONICAL_URL:
                pass
            else:
                issues.append(Issue(relative, reference.line, "external runtime dependency is forbidden"))
            continue
        if value.startswith("//"):
            issues.append(Issue(relative, reference.line, "external runtime dependency is forbidden"))
            continue
        if parsed.path.startswith("/"):
            issues.append(Issue(relative, reference.line, "root-relative reference is forbidden"))
            continue
        decoded_path = unquote(parsed.path)
        target = (source.parent / decoded_path).resolve() if decoded_path else source.resolve()
        if not _inside(target, site.resolve()):
            issues.append(Issue(relative, reference.line, "local reference escapes the site root"))
            continue
        if decoded_path and not target.is_file() and not (
            target.is_dir() and (target / "index.html").is_file()
        ):
            issues.append(Issue(relative, reference.line, f"local reference does not resolve: {value}"))
            continue
        if parsed.fragment:
            fragment_page = relative
            if decoded_path:
                candidate = target / "index.html" if target.is_dir() else target
                try:
                    fragment_page = candidate.relative_to(site.resolve()).as_posix()
                except ValueError:
                    continue
            if parsed.fragment not in page_ids.get(fragment_page, set()):
                issues.append(Issue(relative, reference.line, f"local fragment does not resolve: #{parsed.fragment}"))
    return issues


def validate(site: Path) -> list[Issue]:
    site = site.resolve()
    found, issues = _inventory(site)
    parsed_pages: dict[str, PageParser] = {}
    page_ids: dict[str, set[str]] = {}
    for relative in ("404.html", "index.html"):
        if relative not in found:
            continue
        parser, _text, parse_issues = _parse_page(site / relative, relative)
        issues.extend(parse_issues)
        if parser is not None:
            parsed_pages[relative] = parser
            page_ids[relative] = set(parser.ids)
    for relative, parser in parsed_pages.items():
        issues.extend(_metadata_issues(relative, parser))
        issues.extend(_policy_issues(relative, parser))
        issues.extend(_reference_issues(site, relative, parser, page_ids))
    return sorted(set(issues))


def main(argv: list[str] | None = None) -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("site_directory", type=Path)
    args = argument_parser.parse_args(argv)
    issues = validate(args.site_directory)
    for issue in issues:
        print(f"{issue.path}:{issue.line}: {issue.message}")
    if issues:
        print(f"site validation failed with {len(issues)} issue(s)")
        return 1
    print(f"site validation passed: {len(EXPECTED_FILES)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
