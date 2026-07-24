from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tiny_corpus_workbench.cli import observe
from tiny_corpus_workbench.diagnosis import diagnose
from tiny_corpus_workbench.diagnosis_verification import verify_diagnosis
from tiny_corpus_workbench.v03 import (
    diagnose as diagnose_v03,
    verify_diagnosis as verify_diagnosis_v03,
)


ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = Path(os.environ.get("TCW_DOCLING_ARTIFACTS", ".cache/docling/models"))


class DiagnosisIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MODEL_ROOT.is_dir():
            raise unittest.SkipTest(f"prefetched Docling models are required: {MODEL_ROOT}")

    def test_raw_diagnosis_corpus_runs_offline_with_expected_rules(self) -> None:
        registry = json.loads(
            (ROOT / "fixtures/diagnosis/v0.2/fixtures.json").read_text("utf-8")
        )

        def deny(*args, **kwargs):
            raise AssertionError("diagnosis workflow attempted network access")

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            socket, "create_connection", deny
        ), mock.patch.object(socket.socket, "connect", deny), mock.patch.object(
            socket.socket, "connect_ex", deny
        ):
            root = Path(directory)
            for fixture in registry["fixtures"]:
                with self.subTest(fixture=fixture["id"]):
                    source = ROOT / fixture["path"]
                    source_before = source.read_bytes()
                    code, observation = observe(
                        str(source), root / "observations", MODEL_ROOT
                    )
                    self.assertEqual(int(code), 0)
                    diagnosis = diagnose(observation, root / "diagnoses")
                    findings = json.loads(
                        (diagnosis / "findings.json").read_text("utf-8")
                    )
                    actual = sorted(
                        {
                            item["rule_id"] for item in findings["findings"]
                        }
                    )
                    self.assertEqual(actual, fixture["expected_rules"])
                    verified = verify_diagnosis(diagnosis, observation)
                    self.assertEqual(
                        verified["artifact_integrity"]["status"], "VERIFIED"
                    )
                    self.assertEqual(verified["observation_state"]["status"], "MATCH")
                    self.assertEqual(verified["derivation_state"]["status"], "MATCH")
                    self.assertEqual(source.read_bytes(), source_before)

    def test_refinement_fixture_registry_runs_offline_with_expected_rules(
        self,
    ) -> None:
        registry = json.loads(
            (ROOT / "fixtures/refinement/v0.3/fixtures.json").read_text("utf-8")
        )

        def deny(*args, **kwargs):
            raise AssertionError("v0.3 fixture workflow attempted network access")

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            socket, "create_connection", deny
        ), mock.patch.object(socket.socket, "connect", deny), mock.patch.object(
            socket.socket, "connect_ex", deny
        ):
            root = Path(directory)
            for fixture in registry["fixtures"]:
                with self.subTest(fixture=fixture["id"]):
                    source = ROOT / fixture["path"]
                    source_before = source.read_bytes()
                    code, observation = observe(
                        str(source), root / "observations", MODEL_ROOT
                    )
                    self.assertEqual(int(code), 0)
                    diagnosis = diagnose_v03(
                        observation, root / "diagnoses"
                    )
                    findings = json.loads(
                        (diagnosis / "findings.json").read_text("utf-8")
                    )
                    actual = sorted(
                        {item["rule_id"] for item in findings["findings"]}
                    )
                    self.assertEqual(actual, fixture["expected_rules"])
                    verified = verify_diagnosis_v03(
                        diagnosis, observation
                    )
                    self.assertEqual(
                        verified["artifact_integrity"]["status"], "VERIFIED"
                    )
                    self.assertEqual(
                        verified["subject_state"]["status"], "MATCH"
                    )
                    self.assertEqual(
                        verified["derivation_state"]["status"], "MATCH"
                    )
                    self.assertEqual(source.read_bytes(), source_before)


if __name__ == "__main__":
    unittest.main()
