# Golden fixtures

The twelve files in `golden/` are generated from the three authoritative JSON
specifications in `authored/`. They are fictional, contain no personal data or
external resources, and are dedicated to the public domain under CC0-1.0.

The small `golden/fixtures.json` registry records current fixture IDs, paths,
learning properties, hashes, and the generator recipe. It contains no release,
schema, runtime, or build provenance.

Regenerate the files and registry from the repository root:

```bash
uv run --frozen --group fixtures python tools/generate_fixtures.py
uv run --frozen --group fixtures python tools/generate_fixtures.py --check
uv run --frozen --group fixtures python tools/verify_fixtures.py
```

The repository's MIT license applies to code. The separate CC0 declaration in
`LICENSE-CC0-1.0.txt` applies to the authored specifications, generated golden
documents, diagnosis corpus, and versioned refinement fixtures.

The separate `diagnosis/` corpus exercises fixed diagnosis rules. It
contains two Markdown sources and one deterministic three-page PDF. Generate
or check it with `tools/generate_diagnosis_fixtures.py`. Its registry records
expected rule identifiers, file sizes, hashes, and the CC0-1.0 license.

The `refinement/v0.5/` directory is a mixed-format fixture set. It contains a
deterministic Markdown source for whitespace normalization and a deterministic
DOCX source for line-end dehyphenation. Check their registry with
`tools/generate_refinement_fixtures.py --check`. The repeated-margin refiner
reuses `diagnosis/repeated-margin.pdf`.

The `corpus/v0.5/` directory contains two corpus specifications. It adds no raw
document:

- `golden-matrix.json` lists all 12 registered golden fixtures. It contains
  three families and four formats per family. Its exact diagnosis outcome is
  nine D009 findings in the three TXT members and no other findings.
- `quality-corpus.json` lists the five existing diagnosis and refinement
  sources. It covers exactly D002, D003, D004, D005, D007, D009, and D010.

Check both specifications with:

```bash
uv run --frozen python tools/verify_corpus_specs.py
```

The checker validates membership, paths, family and format metadata, and
expected rule coverage. It does not rewrite a fixture or specification.
