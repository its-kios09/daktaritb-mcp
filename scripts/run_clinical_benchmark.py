"""Run the clinical benchmark and emit a markdown report.

Outputs to BENCHMARK_REPORT.md in the repo root.

Usage:
    python scripts/run_clinical_benchmark.py

The report can be embedded in README.md or Devpost.
"""

from __future__ import annotations

import asyncio
import json
import sys
import traceback
from pathlib import Path

# Ensure repo root on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx

from daktaritb_mcp.fhir.context import FhirContext
from daktaritb_mcp.tools import get_tool
from tests.clinical.scenarios import ALL_SCENARIOS, Scenario
from tests.clinical.test_benchmark import _build_transport


async def run_scenario(scenario: Scenario) -> tuple[bool, str, dict | None]:
    """Run one scenario. Returns (passed, failure_reason, full_result)."""
    transport = _build_transport(scenario)

    original = httpx.AsyncClient

    class _Patched(original):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    import daktaritb_mcp.fhir.client as client_mod
    original_class = client_mod.httpx.AsyncClient
    client_mod.httpx.AsyncClient = _Patched

    try:
        tool = get_tool(scenario.tool)
        if tool is None:
            return False, f"Tool {scenario.tool} not registered", None

        patient_id = scenario.patient_builder()["id"]
        ctx = FhirContext(
            server_url="https://fhir.example.com",
            access_token="bench-token",
            patient_id=patient_id,
        )

        result = await tool.impl(ctx, scenario.tool_arguments)

        # Normalize status: some tools (order_tb_workup) return success
        # implicitly via errors=[] rather than an explicit status field.
        actual_status = result.get("status")
        if actual_status is None and "errors" in result:
            actual_status = "ok" if not result["errors"] else "error"

        if actual_status != scenario.expected_status:
            return False, f"expected status={scenario.expected_status}, got {actual_status}", result

        for i, assertion in enumerate(scenario.expected_assertions):
            if not assertion(result):
                return False, f"assertion #{i + 1} failed", result

        return True, "", result
    except Exception as e:
        return False, f"exception: {e}\n{traceback.format_exc()}", None
    finally:
        client_mod.httpx.AsyncClient = original_class


def _fmt_tool_short(t: str) -> str:
    return {
        "order_tb_workup": "order_tb_workup",
        "adjust_art_for_rif": "adjust_art_for_rif",
        "generate_tb_notification": "generate_tb_notification",
    }.get(t, t)


async def main():
    print("Running DaktariTB clinical benchmark...")
    print("=" * 60)
    results = []
    for scenario in ALL_SCENARIOS:
        print(f"  Scenario {scenario.id:2d}: {scenario.name[:60]}...", end="", flush=True)
        passed, reason, result = await run_scenario(scenario)
        results.append((scenario, passed, reason, result))
        print("  ✓ PASS" if passed else f"  ✗ FAIL — {reason}")

    pass_count = sum(1 for _, p, _, _ in results if p)
    total = len(results)
    print("=" * 60)
    print(f"Result: {pass_count} / {total} scenarios passed")

    # --- Generate markdown report ---
    lines = []
    lines.append("# DaktariTB Clinical Benchmark Report")
    lines.append("")
    lines.append(
        f"**Result: {pass_count} / {total} scenarios passed** "
        f"({'100%' if pass_count == total else f'{pass_count * 100 // total}%'})"
    )
    lines.append("")
    lines.append(
        "This benchmark defines a set of clinical scenarios and asserts that "
        "DaktariTB's tools produce decisions consistent with WHO and Kenya "
        "Ministry of Health guidelines. Each scenario tests a specific clinical "
        "condition with FHIR-valid inputs and verifies both positive cases "
        "(tool correctly fires) and negative cases (tool correctly refuses to fire)."
    )
    lines.append("")
    lines.append(
        "Over-firing a clinical decision support tool is dangerous. The benchmark "
        "explicitly tests discrimination — scenarios 2, 6, 7, and 8 are "
        "negative-case checks where the tool should refuse or decline to act."
    )
    lines.append("")
    lines.append("## Scenario summary")
    lines.append("")
    lines.append("| # | Scenario | Tool | Expected | Result |")
    lines.append("| - | -------- | ---- | -------- | ------ |")
    for scenario, passed, reason, _ in results:
        status_display = "✓ pass" if passed else "✗ fail"
        lines.append(
            f"| {scenario.id} | {scenario.name} | `{_fmt_tool_short(scenario.tool)}` | "
            f"{scenario.expected_status} | {status_display} |"
        )
    lines.append("")
    lines.append("## Per-scenario detail")
    lines.append("")
    for scenario, passed, reason, result in results:
        status_icon = "✓" if passed else "✗"
        lines.append(f"### {status_icon} Scenario {scenario.id}: {scenario.name}")
        lines.append("")
        lines.append(f"**Clinical situation:** {scenario.clinical_description}")
        lines.append("")
        lines.append(f"**Tool invoked:** `{scenario.tool}` with arguments `{scenario.tool_arguments}`")
        lines.append("")
        lines.append(f"**Expected outcome:** `status={scenario.expected_status}`")
        lines.append("")
        lines.append(f"**Guideline basis:** {scenario.guideline_citation}")
        lines.append("")
        lines.append(f"> {scenario.guideline_rationale}")
        lines.append("")
        if passed:
            lines.append("**Result:** PASS")
        else:
            lines.append(f"**Result:** FAIL — {reason}")
            if result:
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(result, indent=2, default=str)[:2000])
                lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Reproducibility")
    lines.append("")
    lines.append("```bash")
    lines.append("git clone https://github.com/its-kios09/daktaritb-mcp.git")
    lines.append("cd daktaritb-mcp")
    lines.append("python -m venv .venv && source .venv/bin/activate")
    lines.append("pip install -e \".[dev]\"")
    lines.append("python scripts/run_clinical_benchmark.py")
    lines.append("```")
    lines.append("")
    lines.append(
        "The benchmark uses httpx MockTransport to isolate clinical logic from "
        "network I/O. Each scenario produces a fresh FHIR context; no state "
        "leaks between scenarios. Running the benchmark takes under 2 seconds."
    )
    lines.append("")

    report_path = Path("BENCHMARK_REPORT.md")
    report_path.write_text("\n".join(lines))
    print(f"\nMarkdown report written to {report_path}")
    if pass_count != total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
