from __future__ import annotations

import hashlib
import unittest

from tiny_corpus_workbench.canonical_json import (
    artifact_key,
    canonical_json,
    edge_key,
    logical_copy_key,
    record_key,
    session_id,
)


class WorkbenchIdentityPreimageTests(unittest.TestCase):
    def test_canonical_json_is_exact_compact_sorted_utf8_without_newline(self) -> None:
        value = {"z": "文档", "a": [True, None, 1]}
        expected = b'{"a":[true,null,1],"z":"\xe6\x96\x87\xe6\xa1\xa3"}'
        self.assertEqual(canonical_json(value), expected)
        self.assertFalse(canonical_json(value).endswith(b"\n"))
        with self.assertRaises(ValueError):
            canonical_json({"bad": float("nan")})

    def test_all_identity_preimages_and_hashes_are_frozen(self) -> None:
        identity = {"observation_id": "1" * 64}
        expected_target = {
            "kind": "OBSERVATION",
            "record_schema_version": "tcw.preparation-manifest/v0.5",
            "identity_type": "observation_id",
            "identity_value": "1" * 64,
            "run_id": "run-1",
            "manifest_sha256": "2" * 64,
            "content_sha256": "3" * 64,
        }
        cases = {
            "logical": (
                {
                    "kind": "OBSERVATION",
                    "record_schema_version": "tcw.preparation-manifest/v0.5",
                    "identity": identity,
                    "run_id": "run-1",
                },
                b'{"identity":{"observation_id":"1111111111111111111111111111111111111111111111111111111111111111"},"kind":"OBSERVATION","record_schema_version":"tcw.preparation-manifest/v0.5","run_id":"run-1"}',
                "dfb7b0e21f5b34895914d5b5ec9453aa3b489992263e3f624f09578c80e6ae91",
                logical_copy_key(
                    kind="OBSERVATION",
                    record_schema_version="tcw.preparation-manifest/v0.5",
                    identity=identity,
                    run_id="run-1",
                ),
            ),
            "record": (
                {
                    "kind": "OBSERVATION",
                    "record_schema_version": "tcw.preparation-manifest/v0.5",
                    "identity": identity,
                    "run_id": "run-1",
                    "manifest_sha256": "2" * 64,
                },
                b'{"identity":{"observation_id":"1111111111111111111111111111111111111111111111111111111111111111"},"kind":"OBSERVATION","manifest_sha256":"2222222222222222222222222222222222222222222222222222222222222222","record_schema_version":"tcw.preparation-manifest/v0.5","run_id":"run-1"}',
                "126339b7672e33e1f84eb43f819acfb9a27600fe9775f600fd5f009421436250",
                record_key(
                    kind="OBSERVATION",
                    record_schema_version="tcw.preparation-manifest/v0.5",
                    identity=identity,
                    run_id="run-1",
                    manifest_sha256="2" * 64,
                ),
            ),
            "edge": (
                {
                    "relation": "DIAGNOSIS_SUBJECT",
                    "from_record_key": "4" * 64,
                    "expected_target": expected_target,
                },
                b'{"expected_target":{"content_sha256":"3333333333333333333333333333333333333333333333333333333333333333","identity_type":"observation_id","identity_value":"1111111111111111111111111111111111111111111111111111111111111111","kind":"OBSERVATION","manifest_sha256":"2222222222222222222222222222222222222222222222222222222222222222","record_schema_version":"tcw.preparation-manifest/v0.5","run_id":"run-1"},"from_record_key":"4444444444444444444444444444444444444444444444444444444444444444","relation":"DIAGNOSIS_SUBJECT"}',
                "cedde8014426d430e8560f2749e9e66c791e52ceb92b661c2906598d88d7c78d",
                edge_key(
                    relation="DIAGNOSIS_SUBJECT",
                    from_record_key="4" * 64,
                    expected_target=expected_target,
                ),
            ),
            "artifact": (
                {
                    "record_key": "4" * 64,
                    "role": "diagnostic-findings",
                    "relative_path": "findings.json",
                    "sha256": "5" * 64,
                },
                b'{"record_key":"4444444444444444444444444444444444444444444444444444444444444444","relative_path":"findings.json","role":"diagnostic-findings","sha256":"5555555555555555555555555555555555555555555555555555555555555555"}',
                "8eb5cdf00ca7c8fa8c39731b26734877ef55ab05757bf6f37a87f074bd24fb83",
                artifact_key(
                    record_key="4" * 64,
                    role="diagnostic-findings",
                    relative_path="findings.json",
                    sha256="5" * 64,
                ),
            ),
            "session": (
                {
                    "top_level_record_keys": ["4" * 64],
                    "contained_record_keys": ["6" * 64],
                    "edge_keys": ["7" * 64],
                },
                b'{"contained_record_keys":["6666666666666666666666666666666666666666666666666666666666666666"],"edge_keys":["7777777777777777777777777777777777777777777777777777777777777777"],"top_level_record_keys":["4444444444444444444444444444444444444444444444444444444444444444"]}',
                "7d49f9954e120c887d5d730c2206a7879a030d2e8fc007673e0d11d7db7a21cf",
                session_id(
                    top_level_record_keys=["4" * 64],
                    contained_record_keys=["6" * 64],
                    edge_keys=["7" * 64],
                ),
            ),
        }
        for name, (preimage, expected_bytes, expected_hash, actual) in cases.items():
            with self.subTest(name=name):
                encoded = canonical_json(preimage)
                self.assertEqual(encoded, expected_bytes)
                self.assertEqual(actual, expected_hash)
                self.assertEqual(expected_hash, hashlib.sha256(expected_bytes).hexdigest())

    def test_session_identity_sorts_inputs_and_rejects_duplicates(self) -> None:
        expected = session_id(
            top_level_record_keys=["1" * 64, "2" * 64],
            contained_record_keys=[],
            edge_keys=[],
        )
        self.assertEqual(
            session_id(
                top_level_record_keys=["2" * 64, "1" * 64],
                contained_record_keys=[],
                edge_keys=[],
            ),
            expected,
        )
        with self.assertRaises(ValueError):
            session_id(
                top_level_record_keys=["1" * 64, "1" * 64],
                contained_record_keys=[],
                edge_keys=[],
            )


if __name__ == "__main__":
    unittest.main()
