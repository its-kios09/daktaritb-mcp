# DaktariTB MCP

**The action layer for TB/HIV clinical workflows on the Prompt Opinion platform.**

A healthcare MCP server that turns clinical reasoning into FHIR writes: lab orders, ART dose adjustments with drug interaction tracking, and Kenya MOH TB notification forms — all as structured, auditable resources.

Built for the [Agents Assemble: Healthcare AI Endgame](https://agents-assemble.devpost.com/) hackathon.

---

## The Problem

Kenya notified ~97,000 TB cases in 2023 against an estimated incidence of ~140,000 — roughly 30% of diagnosed cases never reach the national surveillance system. Each missed case is 3–10 contacts who never get screened.

LLM healthcare agents are good at clinical reasoning. They are bad at clinical action.

Ask any modern agent about a PLHIV patient with a 4-week cough, 8 kg weight loss, and declining CD4 — it will correctly flag TB risk, recommend GeneXpert MTB/RIF, advise double-dose dolutegravir for rifampicin co-administration, and remind you about contact tracing. Ask the same agent to **create those orders in the chart** and it has nothing to offer beyond a dialog box.

Prompt Opinion calls this gap "the last mile." DaktariTB is a set of MCP tools designed to close it, specifically for the single deadliest co-infection pattern in sub-Saharan Africa: TB in people living with HIV.

## What it Does

DaktariTB exposes three MCP tools, each producing a specific 5T deliverable that Prompt Opinion agents cannot produce natively:

| Tool | 5T | Output |
|---|---|---|
| `order_tb_workup` | Transaction | FHIR `ServiceRequest` bundle: GeneXpert MTB/RIF, Urine LF-LAM (if CD4 < 350), Chest X-Ray, AFB smear |
| `adjust_art_for_rif` | Transaction | FHIR `MedicationRequest` for DTG 50mg BID + `DetectedIssue` documenting the rifampicin–dolutegravir UGT1A1 interaction |
| `generate_tb_notification` | Template | FHIR `DocumentReference` containing a completed Kenya MOH TB-001 Notification Form as a rendered PDF |

All tools read patient context through Prompt Opinion's [SHARP FHIR extension](https://docs.promptopinion.ai/fhir-context/mcp-fhir-context) — no bespoke auth, no glue code.

## Try It

DaktariTB is live and published to the Prompt Opinion Marketplace:

- **DaktariTB MCP Server** — endpoint: `https://daktaritb-mcp.onrender.com/mcp`
- **DaktariTB Specialist (A2A Agent)** — a specialist clinical coordinator agent paired with the server

Both are discoverable in [Prompt Opinion's public marketplace](https://app.promptopinion.ai/) under the Jamii Health Innovations publisher.

To reproduce the demo end-to-end in your own workspace, see [`demo/README.md`](./demo/README.md).

## Architecture

```
  Clinician in Prompt Opinion
          │
          │  (Patient context: Wanjiru Kamau, PLHIV, suspected TB)
          ▼
  DaktariTB Specialist Agent (Gemini 3 Flash)
          │  "Order the TB workup for this patient."
          │
          │  Tool invocation (MCP over HTTPS)
          │  Headers: X-FHIR-Server-URL, X-FHIR-Access-Token, X-Patient-ID
          ▼
  DaktariTB MCP Server  ◄─── (this repo)
          │
          │  1. Read SHARP context headers
          │  2. Fetch relevant FHIR resources
          │  3. Apply clinical logic (deterministic, guideline-driven)
          │  4. Construct ServiceRequest / MedicationRequest / DocumentReference
          │  5. POST back to FHIR store
          ▼
  Prompt Opinion FHIR Store (or any compliant FHIR R4 endpoint)
```

## Clinical Correctness

DaktariTB's tools are backed by a clinical benchmark suite: 10 scenarios where each expected outcome is tied to a specific WHO or Kenya Ministry of Health guideline.

**Current result: 10/10 scenarios pass.**

The suite deliberately includes negative cases — scenarios 2, 6, 7, and 8 test discrimination, where the tool must correctly **refuse** to fire when clinical conditions aren't met. Over-firing a clinical decision support tool is dangerous. The benchmark enforces that discipline.

Reproduce:

```bash
pip install -e ".[dev]"
pytest tests/clinical/           # runs the 10 scenarios
python scripts/run_clinical_benchmark.py   # generates BENCHMARK_REPORT.md
```

See [`BENCHMARK_REPORT.md`](./BENCHMARK_REPORT.md) for the full per-scenario breakdown with guideline citations and clinical rationale.

## Clinical Safety & Regulatory Posture

DaktariTB's three tools are deterministic. They do not use generative models to make clinical decisions. The LLM (Gemini 3 Flash, or any MCP-compatible agent) orchestrates tool calls based on chart context; the tools themselves apply guidelines as code.

- **No raw PHI is transmitted to the LLM for reasoning.** Patient identifiers arrive as SHARP context headers. Tools fetch only the FHIR resources required for the specific clinical decision, apply their logic, and write results back to the chart.
- **Every FHIR write stamps `requester.display` with "DaktariTB MCP Agent"** for audit traceability. Every decision carries `reasonReference` or `evidence` linking back to the source data.
- **Honest about data gaps.** When the chart doesn't provide a required field (DOT supporter, patient phone), the notification is generated with the field explicitly flagged for manual completion before submission to TIBU — never fabricated.
- **Privacy-sensitive toggles.** The notification tool supports `include_hiv_section: false` for contexts where HIV disclosure on a TB notification is contraindicated under Kenya's Data Protection Act (2019).
- **Decision support, not prescribing authority.** Every output states clearly that clinician review is required before becoming actionable in practice. The generated PDF includes this disclosure in its footer.

## Built On

- [Model Context Protocol](https://modelcontextprotocol.io) (Anthropic)
- [HL7 FHIR R4](https://hl7.org/fhir/R4)
- [Prompt Opinion SHARP extension](https://docs.promptopinion.ai/fhir-context/mcp-fhir-context)
- Python 3.11+, FastAPI, Pydantic, httpx, ReportLab
- Kenya NTLD-P TB case definitions and TB-001 form specification
- WHO Consolidated ART Guidelines (2021), WHO Operational Handbook on TB (2022)

## Quickstart

```bash
# Clone
git clone https://github.com/its-kios09/daktaritb-mcp.git
cd daktaritb-mcp

# Install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Configure (optional — SHARP headers come from Po at runtime)
cp .env.example .env

# Run locally
uvicorn daktaritb_mcp.server:app --reload --port 8000

# Health check
curl http://localhost:8000/healthz

# Inspect the tools
curl -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -m json.tool
```

## Registering with Prompt Opinion

Once deployed behind HTTPS:

1. Go to **Configuration → MCP Servers → Add MCP Server**
2. Paste the public URL: `https://daktaritb-mcp.onrender.com/mcp`
3. Click **Continue** — the platform will send an `initialize` request
4. Accept the `ai.promptopinion/fhir-context` extension when prompted
5. The three tools are now available to any agent in your workspace

For a reference deployment on Render.com (used for this hackathon submission), the repo contains a `Dockerfile` and `render.yaml`.

## Project Structure

```
src/daktaritb_mcp/
├── server.py                   # FastAPI entry point, JSON-RPC dispatcher
├── config.py                   # Settings (MOH facility defaults, FHIR timeouts)
├── mcp/
│   ├── initialize.py           # Declares ai.promptopinion/fhir-context capability
│   └── protocol.py             # JSON-RPC 2.0 types + ErrorCode
├── fhir/
│   ├── context.py              # SHARP header reader (X-FHIR-Server-URL, etc.)
│   ├── client.py               # Async httpx FHIR client with search/read/create
│   └── schemas.py              # Builders: ServiceRequest, MedicationRequest,
│                               #           DetectedIssue, DocumentReference
├── tools/
│   ├── base.py                 # ToolDefinition dataclass
│   ├── order_tb_workup.py
│   ├── adjust_art_for_rif.py
│   └── generate_tb_notification.py
└── kenya_moh/
    ├── tb_notification.py      # Kenya NTLD-P notification data model
    └── pdf_renderer.py         # ReportLab-based A4 PDF renderer

tests/
├── clinical/                   # 10-scenario clinical benchmark suite
├── fhir/                       # FHIR context tests
└── tools/                      # Per-tool unit tests
```

## Test Scenarios

The repo ships with a FHIR bundle of five fictional Kenyan patients representing the full TB/HIV decision space:

- **Wanjiru Kamau** (Nairobi) — PLHIV on TLD, classic WHO 4-symptom positive screen, 8kg weight loss, CD4 290
- **Joseph Otieno** (Kisumu) — PLHIV stable on ART, CD4 720 — negative control (discrimination test)
- **Amina Hassan** (Mombasa) — HIV-negative TB on RHZE, month 2
- **Grace Njeri** (Nakuru) — Newly diagnosed HIV, pre-ART, CD4 180
- **Samuel Kiprop** (Eldoret) — TB/HIV co-infected, on both TLD and RHZE — the drug interaction case

Load via `python scripts/seed_demo_patients.py` (full instructions in [`demo/README.md`](./demo/README.md)), or upload the bundle at `demo/daktaritb_sample_bundle.json` directly via Prompt Opinion's Patient Data → Import.

## Why This Project

Healthcare AI demos are overwhelmingly trained on US ICU and EHR data. The single deadliest co-infection pattern in the world — TB in PLHIV, responsible for a large share of AIDS-related deaths each year — remains under-served by the agent tooling being built in 2026.

The pattern also generalizes. Every high-TB-burden country runs a version of Kenya's NTLD-P: India has NIKSHAY, South Africa has ETR.Net, Vietnam has VITIMES, the Philippines has ITIS. Every disease with mandatory surveillance — HIV, COVID, cancer registries — needs the same pipeline: clinical reasoning plus deterministic tools that produce the required paperwork and FHIR writes.

DaktariTB is a small, focused attempt to change that: not with a new model, but with three MCP tools that make existing models useful in real sub-Saharan African clinics — and a template that extends to every jurisdiction with similar public-health workflows.

## License

Apache 2.0. Built to be forked, extended, and deployed in any FHIR-enabled clinical environment.

All sample patient data in this repository is fictional. No real patient data is used or referenced.

## Author

**[Fredrick Kioko](https://github.com/its-kios09)** — Solutions Architect & Senior Software Engineer

Founder, Jamii Health Innovations — clinical AI and health IT for African healthcare systems. Previously deployed KenyaEMR (OpenMRS-based) across 50+ Kenyan counties at Palladium.

## Acknowledgments

- The Prompt Opinion team for a platform that gets the "last mile" right
- WHO Consolidated ART Guidelines (2021) and WHO TB guidelines
- Kenya Ministry of Health, National Tuberculosis, Leprosy and Lung Disease Programme (NTLD-P)
- OpenMRS community