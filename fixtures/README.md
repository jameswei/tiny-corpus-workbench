# Golden fixtures

The twelve files in `golden/` are generated from the three authoritative JSON
specifications in `authored/`. They are fictional, contain no personal data or
external resources, and are dedicated to the public domain under CC0-1.0.

Regenerate them with `uv run --frozen --group fixtures python
tools/generate_fixtures.py`. Verify committed bytes and registry metadata with
`tools/generate_fixtures.py --check` and `tools/verify_fixtures.py`.

The repository's MIT license applies to code. The separate CC0 declaration in
`LICENSE-CC0-1.0.txt` applies to the authored specifications, generated golden
documents, versioned diagnosis corpus, and versioned refinement fixtures.

The separate `diagnosis/v0.2/` corpus exercises fixed diagnosis rules. It
contains two Markdown sources and one deterministic three-page PDF. Generate
or check it with `tools/generate_diagnosis_fixtures.py`. Its registry records
expected rule identifiers, file sizes, hashes, and the CC0-1.0 license.

The `refinement/v0.3/` directory is a mixed-format fixture set. It contains a
deterministic Markdown source for whitespace normalization and a deterministic
DOCX source for line-end dehyphenation. Check their registry with
`tools/generate_refinement_fixtures.py --check`. The repeated-margin refiner
reuses `diagnosis/v0.2/repeated-margin.pdf`.
