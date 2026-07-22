# Golden fixtures

The twelve files in `golden/` are generated from the three authoritative JSON
specifications in `authored/`. They are fictional, contain no personal data or
external resources, and are dedicated to the public domain under CC0-1.0.

Regenerate them with `uv run --frozen --group fixtures python
tools/generate_fixtures.py`. Verify committed bytes and registry metadata with
`tools/generate_fixtures.py --check` and `tools/verify_fixtures.py`.

The repository's MIT license applies to code. The separate CC0 declaration in
`LICENSE-CC0-1.0.txt` applies to the authored specifications and generated
golden documents.
