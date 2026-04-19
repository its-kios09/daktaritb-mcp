# DaktariTB Demo Patients

This directory contains the 5 synthetic patient scenarios used to
demonstrate DaktariTB's clinical tools. All patients are entirely
fictional — no real patient data is used.

## The patients

| Name | DOB | City | Clinical scenario |
|------|-----|------|-------------------|
| **Wanjiru Kamau** | 1991-06-14 | Nairobi | PLHIV on TLD × 3 years. CD4 dropped 480→290 over 6 months. WHO 4-symptom positive (4-week cough, 8 kg weight loss, night sweats, fever 38.4). **Demo case for `order_tb_workup` with LF-LAM inclusion.** |
| **Joseph Otieno** | 1983-11-22 | Kisumu | PLHIV stable on TLD. CD4 720, VL suppressed. No TB. **Negative control** — demonstrates the tool correctly does not fire LF-LAM for high-CD4 patients. |
| **Amina Hassan** | 1997-04-03 | Mombasa | HIV-negative, active pulmonary TB on RHZE month 2. **Negative control** for HIV-specific logic — demonstrates LF-LAM is HIV-specific and ART adjustment skips when no HIV. |
| **Grace Njeri** | 1999-09-18 | Nakuru | Newly diagnosed HIV, CD4 180, VL 85,000. Pre-ART. Represents the advanced-HIV workflow before ART initiation. |
| **Samuel Kiprop** | 1987-02-11 | Eldoret | **The hero case.** HIV+ on TLD × 3 years. Newly diagnosed pulmonary TB (A15.0) on RHZE started 2026-03-31. CD4 210, VL 80. Demo case for coordinated multi-tool invocation: TB notification + rifampicin-DTG interaction management. |

## How to load these patients into your Prompt Opinion workspace

### Option 1: Automated (recommended)

```bash
# From the repo root, with the virtualenv active:
python scripts/seed_demo_patients.py \
    --workspace YOUR_WORKSPACE_UUID \
    --cookie-file path/to/cookie.txt
```

See `scripts/seed_demo_patients.py --help` for details on obtaining
your session cookie and workspace ID.

### Option 2: Manual upload via Po UI

1. Log into Prompt Opinion
2. Navigate to **Patient Data → Import**
3. Upload `demo/daktaritb_sample_bundle.json`
4. Confirm the 5 patients appear in **Patient Data → List**

### Option 3: Regenerate the bundle

If you want fresh UUIDs (for example, to seed a second workspace without
ID conflicts):

```bash
python demo/generate_fhir_bundle.py demo/daktaritb_sample_bundle.json
```

## Try the demos

Once patients are loaded, open the Prompt Opinion **Launchpad**,
select a patient, and pick **DaktariTB Specialist** as the agent.

### Demo 1: TB workup on Wanjiru Kamau
Prompt: *"Order the TB workup for this patient."*

Expected outcome: agent places 4 FHIR ServiceRequest resources
(GeneXpert MTB/RIF, AFB sputum smear, chest X-ray, Urine LF-LAM).
LF-LAM is auto-included because Wanjiru's CD4 of 290 is below the
WHO-defined 350 threshold for PLHIV.

### Demo 2: Coordinated co-infection handling on Samuel Kiprop
Prompt: *"File Samuel's TB notification for NTLD-P."*

Expected outcome: the agent autonomously invokes two tools in sequence:

1. `generate_tb_notification` — renders a Kenya NTLD-P TB notification
   PDF and stores it as a FHIR DocumentReference
2. `adjust_art_for_rif` — detects the dolutegravir-rifampicin UGT1A1
   interaction (TLD + RHZE both in chart) and writes both a DetectedIssue
   and a supplementary DTG 50 mg BID MedicationRequest

The agent returns a coordinated clinical summary citing specific
chart values (CD4, VL, dates) and flags fields that require manual
completion before submission to TIBU.

## Clinical safety note

All clinical decisions produced by DaktariTB are **decision support outputs**, not prescribing authority. Every FHIR write stamps `requester.display` with "DaktariTB MCP Agent" for audit traceability. Every decision carries `reasonReference` or `evidence` back to the source data. The generated PDFs explicitly state that submission to surveillance systems requires review and authorization by a registered clinician.

All patient data in this bundle is fictional and should only be loaded into a test/demo workspace, never into a workspace containing real patient data.
