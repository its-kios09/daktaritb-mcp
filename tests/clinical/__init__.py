"""Clinical benchmark suite for DaktariTB.

Each scenario is a defined clinical situation with FHIR-valid fixtures,
an expected decision, and a citation to the relevant WHO or Kenya MOH
guideline. Running pytest tests/clinical/ produces pass/fail per scenario.

Running scripts/run_clinical_benchmark.py produces a markdown report.
"""
