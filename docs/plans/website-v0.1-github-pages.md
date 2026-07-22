# Website v0.1: GitHub Pages

**Status:** Accepted implementation plan

**Accepted:** 2026-07-22

**Branch:** `feat/github-pages`

## 1. Outcome

Publish a modern, concise, minimal static website for
`tiny-corpus-workbench` at:

```text
https://jameswei.github.io/tiny-corpus-workbench/
```

The website is a project presentation and learning surface. It explains the
current v0.1.0 Extraction Observatory, its artifact model, its integrity
boundary, and how to start. It does not process documents.

This work is an internal publication milestone. It does not activate or
complete a roadmap milestone, change the package version, create a tag or
release, or add a row to the README project-status table.

## 2. Boundaries

The website must remain inside the project's agreed document-preparation
boundary. It can explain extraction, canonical representation, diagnosis, and
controlled refinement, but it must not present chunking, embeddings, indexing,
retrieval, generation, or RAG evaluation as project features.

The first website version is static and dependency-free at runtime. It has:

- no document upload or processing
- no API or server component
- no form, search, analytics, cookies, or user tracking
- no custom domain
- no runtime fetches
- no external fonts, style sheets, JavaScript, or content delivery networks
- no JavaScript requirement

The website does not replace the repository documentation or learner
materials. It guides readers to those authoritative resources.

## 3. Public artifacts

Add these implementation artifacts:

```text
site/index.html
site/404.html
site/styles.css
site/assets/favicon.svg
tools/validate_site.py
tests/unit/test_static_site.py
.github/workflows/pages.yml
```

Update these public or validation contracts:

```text
.github/workflows/ci.yml
README.md
CURRENT.md
pyproject.toml
```

Do not modify `docs/proposal.md` or `docs/roadmap.md` for this work.

## 4. Information architecture

The single page contains six compact sections.

### 4.1 Header and hero

- Use a `v0.1.0` eyebrow.
- Use the heading: "Inspect extraction before downstream systems inherit it."
- Use no more than two introductory sentences.
- Provide "Try it" and "View GitHub" actions.
- State: "This site explains the project. It does not process documents."

### 4.2 Purpose and workflow

Explain why extraction evidence must be inspected before downstream use. Show
this workflow with semantic HTML and CSS:

```text
original source
    -> validated private snapshot
    -> Docling / MarkItDown branches
    -> manifest + comparison
    -> published evidence
```

Label the source as unchanged, the snapshot as temporary, Docling JSON as
canonical, and Markdown views as derived. State that the private snapshot is
removed before publication.

### 4.3 v0.1 and artifact anatomy

Summarize the released surface: supported fixture formats, twelve deterministic
fixtures, offline observation after model prefetch, and the `observe` and
`verify` commands. Show the exact five-file published observation layout:

```text
manifest.json
comparison.json
docling/document.json
docling/document.md
markitdown/document.md
```

### 4.4 Integrity boundary

Clearly distinguish these claims:

- **Verified:** structural validity, artifact integrity, and explicitly
  derivable semantic consistency.
- **Not authenticated:** the verifier does not establish who created or last
  changed otherwise valid evidence.

Do not imply cryptographic signing, key management, authenticity, or
tamper-proof operation.

### 4.5 Quick start and learning

Use the existing three-command setup and observation path from the README.
Link to the Extraction Observatory guide and the v0.1 learner module.

### 4.6 Status and footer

State that v0.1.0 is available and v0.2 through v1.0 are planned. Link to the
release, roadmap, repository, and license.

Section introductions contain no more than two sentences. Cards contain no
more than three bullets. Major claims are not duplicated across sections.

## 5. Visual and interaction direction

Use a modern product-documentation style rather than an application dashboard.
The page is quiet, direct, and spacious.

### 5.1 Color

Use these design tokens:

| Role | Color |
| --- | --- |
| Canvas | `#f8fafc` |
| Surface | `#ffffff` |
| Subtle surface | `#f1f5f9` |
| Primary text | `#0f172a` |
| Muted text | `#475569` |
| Border | `#dbe3ed` |
| Accent | `#2563eb` |
| Accent hover | `#1d4ed8` |
| Evidence foreground | `#047857` |
| Evidence background | `#ecfdf5` |
| Limitation foreground | `#a16207` |
| Limitation background | `#fffbeb` |
| Code background | `#0b1220` |
| Code foreground | `#e5e7eb` |

### 5.2 Typography and layout

- Use only system sans-serif and system monospace font stacks.
- Use a maximum content width of 1120 pixels.
- Use a 12-column desktop grid, a 6-column tablet grid, and one column on
  mobile.
- Convert the workflow diagram to a vertical sequence on small screens.
- Keep code blocks horizontally scrollable without causing page overflow.

### 5.3 Restraint

Do not use gradients, decorative shadows, glass effects, textures, hero art,
stock imagery, fake application windows, terminal-dot decoration, dashboard
chrome, large icons, repeated pills, or decorative animation.

No navigation drawer or JavaScript hamburger is required. Interactions are
limited to clear keyboard focus and 120-160 millisecond color, border, or
underline transitions. Disable transitions when the user prefers reduced
motion.

## 6. Link and metadata contract

- Make site asset paths relative so the site works at the GitHub Pages project
  subpath.
- Use absolute HTTPS URLs for repository, guide, lesson, release, roadmap, and
  license navigation.
- Set the canonical URL to the GitHub Pages URL.
- Give the custom 404 page `noindex` metadata and a clear link to the site
  home.
- Add a visible Website link near project status in `README.md` without adding
  a milestone row.
- Add `Website` to `[project.urls]` in `pyproject.toml`.
- Update `CURRENT.md` to record the website as a separate publication surface
  and to treat GitHub Pages and Actions as authoritative for live status.

Repository homepage metadata is updated only after the deployed site is live
and verified.

## 7. Static-site validator

Implement `tools/validate_site.py` with the Python standard library. It accepts
the site directory, reports deterministic file-and-line issues, and exits
nonzero on validation failure.

The validator checks:

- the expected file inventory consists of regular files and contains no
  symbolic links
- HTML language, UTF-8 charset, viewport, description, title, one `main`, and
  one `h1`
- unique element IDs and valid local fragments
- local references remain inside the site root and resolve
- asset references are not root-relative
- external navigation uses HTTPS
- pages contain no scripts, event-handler attributes, forms, form controls,
  iframes, objects, external style sheets, external fonts, or runtime media
- the canonical URL is correct
- the 404 page has `noindex` behavior and a valid home link

Unit tests cover one valid temporary site and failures for missing assets,
broken fragments, duplicate IDs, path escape, root-relative references,
symbolic links, forbidden interactive elements, and external dependencies.

Add this command to the existing `Fast validation` CI job without renaming the
job or changing the repository ruleset:

```bash
uv run --frozen python tools/validate_site.py site
```

## 8. GitHub Pages workflow

Add `.github/workflows/pages.yml` using only immutable references to official
GitHub actions. Run it on pushes to `main` and manual dispatch. Guard build and
deployment so they run only for `refs/heads/main`.

Use:

- top-level `permissions: {}`
- concurrency group `pages` with `cancel-in-progress: false`
- ten-minute job timeouts
- a build job with `contents: read`
- checkout with persisted credentials disabled
- Pages configuration, static-site validation, and an upload containing only
  `site/`
- a deploy job that needs the build job and grants only `pages: write` and
  `id-token: write`
- the `github-pages` environment and the deployment URL output

Pin these exact action revisions:

| Action | Version | Commit |
| --- | --- | --- |
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/configure-pages` | v6.0.0 | `45bfe0192ca1faeb007ade9deae92b16b8254a0d` |
| `actions/upload-pages-artifact` | v5.0.0 | `fc324d3547104276b827a68afc52ff2a11cc49c9` |
| `actions/deploy-pages` | v5.0.0 | `cd2ce8fcbc39b97be8ca5fce6e763baed58fa128` |

The Pages workflow also runs the static-site validator before upload.

## 9. Verification

Run:

```bash
uv run --frozen python tools/validate_site.py site
uv run --frozen pytest tests/unit/test_static_site.py
uv run --frozen pytest tests/unit
uv run --frozen python -m compileall -q src tests tools
uv run --frozen python tools/generate_fixtures.py --check
uv run --frozen python tools/check_portability.py
git diff --check
```

Run the full extraction suite when the required local model inventory is
available.

Preview locally with:

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory site
```

Check 1440, 1280, 768, 390, and 320 pixel widths. Verify keyboard focus,
reduced-motion behavior, no horizontal page overflow, local and fragment
links, scrollable code, the local 404 page, and that the preview loads only its
own HTML, CSS, and favicon.

## 10. Failure modes

- A local reference that escapes the site root, a missing asset, a symbolic
  link, or a forbidden external/runtime dependency fails validation.
- A Pages workflow run outside `main` does not deploy.
- If GitHub Pages is already configured differently at publication time,
  inspect the drift and stop instead of overwriting it.
- If deployment fails, do not set the repository homepage. Repair deployment
  through a new pull request rather than bypassing branch protection or
  publishing manually.
- If implementation needs a server, client-side application, external runtime
  dependency, custom domain, or changed project boundary, return for owner
  approval.

## 11. Review and publication gates

1. A milestone builder implements this accepted plan.
2. A fresh milestone reviewer examines the complete branch diff, verification
   evidence, and visual evidence. Review repeats until `PASS`.
3. Stop for owner approval before pushing or opening a pull request.
4. After approval, push the reviewed branch and open a draft pull request.
5. Require the existing `Fast validation` and `Full extraction` checks on the
   exact reviewed head. Mark ready only with owner approval, request or wait for
   Copilot review, and resolve all review threads.
6. Pages activation is a separate external-state gate. Recheck the Pages API.
   If it remains unconfigured and the owner explicitly approves activation,
   configure its build type as `workflow`. Do not replace a drifted setting.
7. Never merge automatically. The owner performs or explicitly authorizes a
   squash merge.
8. Confirm that the merge-triggered Pages deployment uses the merged commit.
   Verify the HTTPS home page, CSS and favicon under the project subpath,
   anchors and navigation, custom 404 behavior, and desktop and mobile layout.
9. Only after live verification and explicit approval, set the repository
   homepage to the live Pages URL.

## 12. Acceptance criteria

- The accepted plan is saved before implementation.
- The site is semantic, responsive, keyboard accessible, visually restrained,
  and usable at all specified viewport widths.
- It accurately represents v0.1.0 and the project's integrity and scope
  boundaries.
- It has none of the forbidden application behavior or external runtime
  dependencies.
- The validator and its negative-path tests pass.
- Existing unit, fixture, compile, portability, and diff-hygiene checks pass.
- A fresh milestone reviewer returns `PASS` with no blocking finding.
- Existing GitHub checks pass on the reviewed pull-request head and review
  threads are resolved.
- GitHub Pages is configured for Actions only through the explicit activation
  gate.
- The owner-approved squash merge deploys the merged commit successfully.
- The live site and custom 404 page pass post-deployment checks.
- README, package metadata, CURRENT, and repository homepage point to the live
  site at the appropriate gates.
- The package remains v0.1.0, with no new tag, release, roadmap activation,
  custom domain, or API.
