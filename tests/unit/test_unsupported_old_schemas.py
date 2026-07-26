"""Test-only unsupported schema identifiers.

Current runtime code never imports this module. Negative tests import these
constants to prove that released pre-v0.5 artifacts exit with code 2.
"""

OLD_OBSERVATION_SCHEMA = "tcw.preparation-manifest/v0.1"
OLD_DIAGNOSIS_SCHEMA = "tcw.diagnosis-manifest/v0.3"
OLD_REFINEMENT_DRAFT_SCHEMA = "tcw.refinement-draft/v0.3"
OLD_REFINEMENT_SCHEMA = "tcw.refinement-manifest/v0.3"
