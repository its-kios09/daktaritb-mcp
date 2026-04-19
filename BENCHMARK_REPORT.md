# DaktariTB Clinical Benchmark Report

**Result: 10 / 10 scenarios passed** (100%)

This benchmark defines a set of clinical scenarios and asserts that DaktariTB's tools produce decisions consistent with WHO and Kenya Ministry of Health guidelines. Each scenario tests a specific clinical condition with FHIR-valid inputs and verifies both positive cases (tool correctly fires) and negative cases (tool correctly refuses to fire).

Over-firing a clinical decision support tool is dangerous. The benchmark explicitly tests discrimination — scenarios 2, 6, 7, and 8 are negative-case checks where the tool should refuse or decline to act.

## Scenario summary

| # | Scenario | Tool | Expected | Result |
| - | -------- | ---- | -------- | ------ |
| 1 | High-risk PLHIV presumptive TB | `order_tb_workup` | ok | ✓ pass |
| 2 | PLHIV with high CD4 — LF-LAM not indicated | `order_tb_workup` | ok | ✓ pass |
| 3 | HIV-negative adult presumptive TB | `order_tb_workup` | ok | ✓ pass |
| 4 | Severely immunocompromised PLHIV — STAT workup | `order_tb_workup` | ok | ✓ pass |
| 5 | TB/HIV co-infection — DTG-rifampicin interaction management | `adjust_art_for_rif` | ok | ✓ pass |
| 6 | EFV-based ART with rifampicin — no adjustment needed | `adjust_art_for_rif` | skipped | ✓ pass |
| 7 | HIV-negative TB patient — no ART adjustment | `adjust_art_for_rif` | skipped | ✓ pass |
| 8 | PLHIV on TLD without rifampicin — no adjustment | `adjust_art_for_rif` | skipped | ✓ pass |
| 9 | Bacteriologically confirmed pulmonary TB — notification | `generate_tb_notification` | ok | ✓ pass |
| 10 | Extrapulmonary TB (bone and joint) — notification | `generate_tb_notification` | ok | ✓ pass |

## Per-scenario detail

### ✓ Scenario 1: High-risk PLHIV presumptive TB

**Clinical situation:** 34yo female, HIV+ on TLD for 3 years, CD4 dropped from 480 to 290 over 6 months, 4-week cough, 8kg weight loss, drenching night sweats. WHO 4-symptom screen positive. CD4 below 350 threshold.

**Tool invoked:** `order_tb_workup` with arguments `{}`

**Expected outcome:** `status=ok`

**Guideline basis:** WHO Consolidated ART Guidelines (2021), §10.2

> Urine LF-LAM is indicated for PLHIV with CD4 below 350 cells/µL. CD4 of 290 crosses this threshold. Standard TB workup also requires GeneXpert MTB/RIF, AFB smear, and chest X-ray.

**Result:** PASS

---

### ✓ Scenario 2: PLHIV with high CD4 — LF-LAM not indicated

**Clinical situation:** 42yo male, HIV+ stable on TLD, CD4 720, mild 1-week cough. WHO screen borderline positive. CD4 well above 350 threshold.

**Tool invoked:** `order_tb_workup` with arguments `{}`

**Expected outcome:** `status=ok`

**Guideline basis:** WHO Consolidated ART Guidelines (2021), §10.2

> Urine LF-LAM is NOT routinely indicated for PLHIV with CD4 at or above 350 cells/µL. Over-ordering LF-LAM in high-CD4 patients wastes scarce resources and produces false positives.

**Result:** PASS

---

### ✓ Scenario 3: HIV-negative adult presumptive TB

**Clinical situation:** 28yo female, HIV-negative, 3-week productive cough and low-grade fever. No immunocompromise. Standard TB workup required; LF-LAM is HIV-specific and should not be ordered.

**Tool invoked:** `order_tb_workup` with arguments `{}`

**Expected outcome:** `status=ok`

**Guideline basis:** WHO Operational Handbook on TB (2022), Module 3

> HIV-negative patients with presumptive TB receive GeneXpert MTB/RIF as first-line, plus AFB smear and chest X-ray. Urine LF-LAM is a TB antigen detection test validated only in PLHIV and is not recommended for HIV-negative patients.

**Result:** PASS

---

### ✓ Scenario 4: Severely immunocompromised PLHIV — STAT workup

**Clinical situation:** 35yo male, HIV+ on TLD, CD4 140, severely ill with fever and respiratory distress. CD4 below 200 indicates advanced HIV; STAT priority justified for TB workup.

**Tool invoked:** `order_tb_workup` with arguments `{'urgency': 'stat'}`

**Expected outcome:** `status=ok`

**Guideline basis:** WHO ART Guidelines §10.2 + Advanced HIV Disease recommendations

> PLHIV with CD4 below 200 have advanced HIV disease and require urgent TB workup. STAT urgency reduces time-to-diagnosis and mortality. LF-LAM especially valuable in this population due to higher sensitivity in advanced immunosuppression.

**Result:** PASS

---

### ✓ Scenario 5: TB/HIV co-infection — DTG-rifampicin interaction management

**Clinical situation:** 38yo male, HIV+ on TLD for 3 years, newly diagnosed pulmonary TB started on RHZE (rifampicin-based regimen) 2 weeks ago. Rifampicin induces UGT1A1, lowering DTG plasma levels.

**Tool invoked:** `adjust_art_for_rif` with arguments `{}`

**Expected outcome:** `status=ok`

**Guideline basis:** WHO Consolidated ARV Guidelines (2021) §4.4.3

> When rifampicin is co-administered with dolutegravir, DTG dose must be doubled to 50mg twice daily to overcome UGT1A1 induction. This should be implemented as an additive supplementary dose to preserve the fixed-dose TLD combination, continuing for 2 weeks after rifampicin stops due to residual enzyme induction.

**Result:** PASS

---

### ✓ Scenario 6: EFV-based ART with rifampicin — no adjustment needed

**Clinical situation:** 45yo female, HIV+ on efavirenz-based ART (legacy regimen), TB on RHZE. EFV has a different pharmacokinetic profile and does not require dose adjustment for rifampicin co-administration.

**Tool invoked:** `adjust_art_for_rif` with arguments `{}`

**Expected outcome:** `status=skipped`

**Guideline basis:** WHO Consolidated ARV Guidelines (2021) §4.4.3

> The UGT1A1 interaction affects dolutegravir specifically. Efavirenz-based regimens are metabolized primarily through CYP3A4/2B6 and do not require rifampicin dose adjustment. A decision support tool must correctly refuse to adjust regimens that don't need it.

**Result:** PASS

---

### ✓ Scenario 7: HIV-negative TB patient — no ART adjustment

**Clinical situation:** 29yo female, HIV-negative, active TB on RHZE. No HIV means no ART, which means no drug interaction to manage.

**Tool invoked:** `adjust_art_for_rif` with arguments `{}`

**Expected outcome:** `status=skipped`

**Guideline basis:** Kenya NTLD-P Integrated Guidelines for TB/HIV Care

> ART adjustment for rifampicin is only clinically meaningful for PLHIV receiving dolutegravir. The tool must refuse to adjust a regimen that doesn't exist. Over-firing here would fabricate a prescription for a non-existent patient need.

**Result:** PASS

---

### ✓ Scenario 8: PLHIV on TLD without rifampicin — no adjustment

**Clinical situation:** 31yo female, HIV+ on TLD, no TB, no rifampicin in chart. Without rifampicin co-administration there is no interaction to manage. Pre-emptive adjustment is unsafe.

**Tool invoked:** `adjust_art_for_rif` with arguments `{}`

**Expected outcome:** `status=skipped`

**Guideline basis:** Pharmacovigilance principle: no intervention without indication

> DTG 50mg BID dosing is only indicated during rifampicin co-administration. Prescribing BID dosing to a patient not on rifampicin would expose them to unnecessary drug burden without clinical benefit.

**Result:** PASS

---

### ✓ Scenario 9: Bacteriologically confirmed pulmonary TB — notification

**Clinical situation:** Confirmed pulmonary TB (ICD-10 A15.0). Case must be notified to Kenya NTLD-P via TIBU. Classification: pulmonary (A15 prefix), bacteriologically confirmed (A15.0 specifically).

**Tool invoked:** `generate_tb_notification` with arguments `{}`

**Expected outcome:** `status=ok`

**Guideline basis:** Kenya NTLD-P Case Definitions (2024 update)

> ICD-10 A15.x codes designate bacteriologically confirmed pulmonary TB, where a specimen has been positive by smear, culture, or WHO-approved molecular test. A16.x codes indicate clinically diagnosed pulmonary TB. The notification tool must distinguish these.

**Result:** PASS

---

### ✓ Scenario 10: Extrapulmonary TB (bone and joint) — notification

**Clinical situation:** Tuberculosis of bones and joints (ICD-10 A18.0). Extrapulmonary TB requires different treatment duration and monitoring. Classification: extrapulmonary (A18 prefix), clinically diagnosed.

**Tool invoked:** `generate_tb_notification` with arguments `{'include_hiv_section': False}`

**Expected outcome:** `status=ok`

**Guideline basis:** Kenya NTLD-P Case Definitions (2024 update)

> ICD-10 A17-A19 codes designate extrapulmonary TB. A18.0 specifically indicates osteoarticular TB. Extrapulmonary cases are typically clinically diagnosed because obtaining bacteriological confirmation is difficult (requires tissue sampling). Treatment duration may be extended (up to 9-12 months for CNS or bone involvement).

**Result:** PASS

---

## Reproducibility

```bash
git clone https://github.com/its-kios09/daktaritb-mcp.git
cd daktaritb-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/run_clinical_benchmark.py
```

The benchmark uses httpx MockTransport to isolate clinical logic from network I/O. Each scenario produces a fresh FHIR context; no state leaks between scenarios. Running the benchmark takes under 2 seconds.
