from services.okf import validate_concept


def test_okf_v02_accepts_provenance_trust_and_extensions():
    document = """---
type: Reference
sources:
  - id: article
    resource: https://example.com/article
generated:
  by: agent/example-1
  at: 2026-09-19T12:00:00Z
verified:
  by: human:reviewer
  at: 2026-09-19T13:00:00Z
status: stable
custom_extension: preserved
---
# Example
"""
    assert validate_concept(document) == []


def test_okf_v02_requires_runtime_for_attested_computation():
    document = "---\ntype: Attested Computation\n---\n# Computation\n"
    assert "requires runtime" in " ".join(validate_concept(document))


def test_okf_v02_accepts_minimal_concept():
    assert validate_concept("---\ntype: Concept\n---\nKnowledge") == []
