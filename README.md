# DaktariTB MCP

**The action layer for TB/HIV clinical workflows on the Prompt Opinion platform.**

A healthcare MCP server that turns clinical reasoning into FHIR writes: lab orders, ART dose adjustments with drug interaction tracking, and Kenya MOH TB notification forms — all as structured, auditable resources.

Built for the [Agents Assemble: Healthcare AI Endgame](https://agents-assemble.devpost.com/) hackathon.

---

## The Problem

LLM healthcare agents are good at clinical reasoning. They are bad at clinical action.

Ask any modern agent about a PLHIV patient with a 4-week cough, 8 kg weight loss, and declining CD4 — it will correctly flag TB risk, recommend GeneXpert MTB/RIF, advise double-dose dolutegravir for rifampicin co-administration, and remind you about contact tracing. Ask the same agent to **create those orders in the chart** and it has nothing to offer beyond a dialog box.

Prompt Opinion calls this gap "the last mile." DaktariTB is a set of MCP tools designed to close it, specifically for the single deadliest co-infection pattern in sub-Saharan Africa: TB in people living with HIV.

## What it Does

DaktariTB exposes three MCP tools, each producing a specific [5T deliverable](https://www.promptopinion.ai) Prompt Opinion agents cannot produce natively:

| Tool | 5T | Output |
|---|---|---|
| `order_tb_workup` | Transaction | FHIR `ServiceRequest` bundle: GeneXpert MTB/RIF, Urine LF-LAM (if CD4 < 350), Chest X-Ray, AFB smear |
| `adjust_art_for_rif` | Transaction | FHIR `MedicationRequest` for DTG 50mg BID + `DetectedIssue` documenting the rifampicin–dolutegravir UGT1A1 interaction |
| `generate_tb_notification` | Template | FHIR `DocumentReference` containing a completed Kenya MOH TB-001 Notification Form |

All tools read patient context through Prompt Opinion's [SHARP FHIR extension](https://docs.promptopinion.ai/fhir-context/mcp-fhir-context) — no bespoke auth, no glue code.

## Architecture

```
  Clinician in Prompt Opinion
          │
          │  (Patient context: Wanjiru Kamau, PLHIV, suspected TB)
          ▼
  Po General Chat Agent (Gemini 3 Flash)
          │  "Order GeneXpert and adjust her ART"
          │
          │  Tool invocation (MCP over HTTPS)
          │  Headers: X-FHIR-Server-URL, X-FHIR-Access-Token, X-Patient-ID
          ▼
  DaktariTB MCP Server  ◄─── (this repo)
          │
          │  1. Read SHARP headers
          │  2. Fetch relevant FHIR resources
          │  3. Construct ServiceRequest / MedicationRequest / DocumentReference
          │  4. POST back to FHIR store
          ▼
  Prompt Opinion FHIR Store
```

## Built On

- [Model Context Protocol](https://modelcontextprotocol.io) (Anthropic)
- [HL7 FHIR R4](https://hl7.org/fhir/R4)
- [Prompt Opinion SHARP extension](https://docs.promptopinion.ai/fhir-context/mcp-fhir-context)
- Python 3.11+, FastAPI, Pydantic, httpx
- Kenya Ministry of Health TB-001 form specification

## Quickstart

```bash
# Clone
git clone https://github.com/its-kios09/daktaritb-mcp.git
cd daktaritb-mcp

# Install
pip install -e .

# Configure
cp .env.example .env
# (no secrets needed for local dev — SHARP headers come from Po at runtime)

# Run
uvicorn daktaritb_mcp.server:app --reload --port 8000

# Health check
curl http://localhost:8000/healthz
```

## Registering with Prompt Opinion

Once deployed behind HTTPS:

1. Go to **Configuration → MCP Servers → Add MCP Server**
2. Paste the public URL: `https://12.12.1.2.1.2/mcp`
3. Click **Continue** — the platform will send an `initialize` request
4. You'll see a prompt to trust the `ai.promptopinion/fhir-context` extension — accept
5. The three tools are now available to any agent in your workspace

See [`docs/deployment.md`](docs/deployment.md) for DigitalOcean + Cloudflare Tunnel setup.

## Project Structure

```
src/daktaritb_mcp/
├── server.py              # FastAPI entry point
├── mcp/
│   ├── initialize.py      # Declares ai.promptopinion/fhir-context capability
│   └── protocol.py        # JSON-RPC 2.0 handlers
├── fhir/
│   ├── client.py          # SHARP header reader + FHIR HTTP client
│   └── schemas.py         # Pydantic models for FHIR R4 resources
├── tools/
│   ├── order_tb_workup.py
│   ├── adjust_art_for_rif.py
│   └── generate_tb_notification.py
└── kenya_moh/
    └── tb001_form.py      # Kenya MOH TB-001 form schema + renderer
```

## Test Scenarios

The repo ships with a FHIR bundle of five fictional Kenyan patients representing the full TB/HIV decision space:

- **Wanjiru Kamau** (Nairobi) — PLHIV on TLD, classic WHO 4-symptom positive screen, 8kg weight loss
- **Joseph Otieno** (Kisumu) — PLHIV stable on ART, negative control
- **Amina Hassan** (Mombasa) — HIV-negative TB on RHZE, month 2
- **Grace Njeri** (Nakuru) — Newly diagnosed HIV, pre-ART, with respiratory symptoms
- **Samuel Kiprop** (Eldoret) — TB/HIV co-infected on both DTG and rifampicin (the drug interaction case)

Load via `scripts/load_sample_patients.py` or the bundle at `fixtures/daktaritb_sample_bundle.json`.

## Why This Project

Healthcare AI demos are overwhelmingly trained on US ICU and EHR data. The single deadliest co-infection pattern in the world — TB in PLHIV, responsible for a large share of AIDS-related deaths each year — remains under-served by the agent tooling being built in 2026.

DaktariTB is a small, focused attempt to change that: not with a new model, but with three MCP tools that make existing models useful in real sub-Saharan African clinics.

## License

Apache 2.0. Built to be forked, extended, and deployed in any FHIR-enabled clinical environment.

## Author

[Fredrick Kioko](https://github.com/its-kios09) — Solutions Architect | Senior Software Engineer
## Acknowledgments

- The Prompt Opinion team for a platform that gets the "last mile" right
- WHO TB/HIV integration guidelines
- Kenya Ministry of Health, Division of National TB, Leprosy and Lung Disease Program
- OpenMRS/KenyaEMR community
