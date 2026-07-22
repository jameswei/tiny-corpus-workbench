# Website v0.1: GitHub Pages

**Status:** Accepted implementation plan

**Accepted:** 2026-07-22

**Validator contract revised:** 2026-07-23

**Public copy revised:** 2026-07-23; roadmap end-state presentation

**Branch:** `feat/github-pages`

## 1. Outcome

Publish a modern, concise, minimal static website for
`tiny-corpus-workbench` at:

```text
https://jameswei.github.io/tiny-corpus-workbench/
```

The website is a project presentation and learning surface. It presents the
roadmap's complete raw-source-to-prepared-revision workbench as one coherent
product story, rather than as a version or release status page. It also gives
readers an honest local entry point and does not process documents itself.

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

- Use the eyebrow: `Local document preparation workbench`.
- Use the heading: "Prepare documents without losing the evidence."
- Use no more than two introductory sentences.
- Provide "Start locally" and "View GitHub" actions.
- State that the site describes the workbench and does not process documents.

### 4.2 Purpose and workflow

Explain the complete project boundary as one evidence-preserving lifecycle.
Show this workflow with semantic HTML and CSS:

```text
original source
    -> extraction
    -> evidence-based diagnosis
    -> explicit human decision
    -> reversible refinement
    -> prepared revision
    -> corpus inspection and comparison
```

Explain that a local visual workbench connects the source, artifacts, findings,
decisions, transformations, revisions, and comparisons without replacing the
underlying CLI and audit contracts.

### 4.3 One inspectable history

Present the roadmap deliverables as four durable capability groups, without
versions, releases, milestone labels, or implementation-status language:

- **Extract:** compare Docling and MarkItDown while retaining lossless
  canonical evidence and source identity.
- **Diagnose:** record deterministic, evidence-backed findings with stable
  identifiers, severity, provenance, and affected document items.
- **Refine:** require explicit decisions, create new prepared revisions, and
  preserve reversible operations plus append-only history.
- **Compare:** inspect patterns across a mixed-format corpus through offline
  reports and a loopback-only visual workbench.

### 4.4 Trust and control boundary

Use two concise columns:

- **Evidence stays inspectable:** original sources, raw extraction artifacts,
  findings, revisions, hashes, and history are retained rather than silently
  overwritten.
- **People retain authority:** diagnosis does not authorize mutation, and
  interpretive refinements require explicit human confirmation.

Retain a short limitation that integrity checking does not establish
authorship or authenticity. Do not imply signing, key management, or
tamper-proof operation.

### 4.5 Local by design and quick start

Describe the coherent local surfaces: stable CLI contracts, static offline
reports, and a loopback-only browser interface. Keep the existing three-command
Extraction Observatory path as the honest starting point available from the
repository today. Link to its guide and learner module without a version label
in visible text.

### 4.6 Project boundary and footer

State that the workbench ends at a prepared document revision. Chunking,
embeddings, indexing, retrieval, generation, and RAG evaluation remain outside
the product boundary. Link to the roadmap, repository, learning material, and
license. Do not show versions, releases, milestone ranges, or progress tables
in the public page copy.

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
- Use absolute HTTPS URLs for repository, guide, lesson, roadmap, and license
  navigation.
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

## 7. Static-site smoke validator

Implement `tools/validate_site.py` with the Python standard library. It accepts
the site directory, reports deterministic file-and-line issues, and exits
nonzero on validation failure.

This is a focused project smoke check, not a general HTML or CSS security
parser. It checks the authored site and common accidental regressions. Browser
QA and source review establish that the committed site has no external runtime
dependencies; the validator does not promise to recognize every equivalent
syntax that a browser supports.

The validator checks:

- the expected file inventory consists of regular files and contains no
  symbolic links
- HTML language, UTF-8 charset, viewport, description, title, one `main`, and
  one `h1`
- unique element IDs and valid local fragments
- local references remain inside the site root and resolve
- asset references are not root-relative
- external navigation uses HTTPS
- the authored pages do not contain scripts, event-handler attributes, forms,
  form controls, iframes, objects, or external style sheets through the normal
  markup paths used by this site
- the canonical URL is correct
- the 404 page has `noindex` behavior and a valid home link

Unit tests cover one valid temporary site and failures for missing assets,
broken fragments, duplicate IDs, path escape, root-relative references,
symbolic links, forbidden interactive elements, and ordinary external
stylesheet references. Adversarial parsing of the complete HTML and CSS
languages is explicitly outside this validator's contract.

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
uv run --frozen --group test python -m unittest tests.unit.test_static_site -v
uv run --frozen --group test python -m unittest discover -s tests/unit -v
uv run --frozen --group test python -m compileall -q src tests tools
uv run --frozen --group fixtures python tools/generate_fixtures.py --check
uv run --frozen --group fixtures python tools/verify_fixtures.py
uv run --frozen --group fixtures python tools/verify_checkout_portability.py
git diff --check main...HEAD
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
own HTML, CSS, and favicon. This request-log check applies to the committed
site, rather than to arbitrary HTML or CSS mutations.

## 10. Failure modes

- A local reference that escapes the site root, a missing asset, a symbolic
  link, or a common forbidden markup regression fails validation.
- If source review or browser QA shows that the committed site loads an
  unapproved runtime dependency, correct the authored site before publication;
  do not expand the smoke validator into a browser-policy engine.
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
- It presents the roadmap's complete intended workbench as one durable product
  story while preserving the project's integrity and scope boundaries and
  keeping the quick-start path factually runnable.
- Source review and browser request logging confirm that the committed site has
  none of the forbidden application behavior or external runtime dependencies.
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
