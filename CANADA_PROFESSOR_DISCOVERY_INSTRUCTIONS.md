# Standard Operating Procedure (SOP): Canada Professor Discovery & Sheet Population

This document specifies the standard workflow, institutional targets, validation rules, and data schemas for discovering, vetting, and populating faculty records for universities in Canada (QS World University Rankings $\le$ 250 and top Canadian CS/AI research programs) into the graduate outreach tracking system.

---

## 1. Target Institutional Scope (QS Rank $\le$ 250 & U15 Research Universities)

Target institutions must be recognized Canadian research universities within the QS Top 250 or premier AI/CS hubs (Vector Institute, Mila, Amii):

### Primary Target Universities & Regional Timezones:

#### Eastern Timezone (`EST/EDT`, America/Toronto / America/Montreal, BD Time `Mon-Thu 6:00 PM - 9:00 PM`):
1. **University of Toronto (U of T)** — QS ~#21 — Department of Computer Science / Vector Institute (`UTORONTO-CS`) — `cs.toronto.edu`, `utoronto.ca`
2. **McGill University** — QS ~#29 — School of Computer Science / Mila (`MCGILL-CS`) — `cs.mcgill.ca`, `mcgill.ca`
3. **University of Waterloo** — QS ~#112 — David R. Cheriton School of Computer Science (`WATERLOO-CS`) — `uwaterloo.ca`, `cs.uwaterloo.ca`
4. **Western University (Western)** — QS ~#114 — Department of Computer Science (`WESTERN-CS`) — `uwo.ca`, `csd.uwo.ca`
5. **Université de Montréal (UdeM)** — QS ~#159 — DIRO / Mila (`UDEM-CS`) — `iro.umontreal.ca`, `umontreal.ca`
6. **McMaster University** — QS ~#176 — Department of Computing and Software (`MCMASTER-CAS`) — `mcmaster.ca`, `cas.mcmaster.ca`
7. **University of Ottawa (uOttawa)** — QS ~#189 — School of Electrical Engineering and Computer Science (`UOTTAWA-EECS`) — `uottawa.ca`
8. **Queen's University** — QS ~#193 — School of Computing (`QUEENS-CS`) — `queensu.ca`, `cs.queensu.ca`

#### Pacific Timezone (`PST/PDT`, America/Vancouver, BD Time `Mon-Thu 9:00 PM - 12:00 AM`):
9. **University of British Columbia (UBC)** — QS ~#34 — Department of Computer Science (`UBC-CS`) — `cs.ubc.ca`, `ubc.ca`
10. **Simon Fraser University (SFU)** — Top Canadian CS Research Hub (`SFU-CS`) — `cs.sfu.ca`, `sfu.ca`

#### Mountain Timezone (`MST/MDT`, America/Edmonton, BD Time `Mon-Thu 7:00 PM - 10:00 PM`):
11. **University of Alberta (UAlberta)** — QS ~#96 — Department of Computing Science / Amii (`UALBERTA-CS`) — `ualberta.ca`, `cs.ualberta.ca`
12. **University of Calgary (UCalgary)** — QS ~#182 — Department of Computer Science (`UCALGARY-CS`) — `ucalgary.ca`, `cpsc.ucalgary.ca`

---

## 2. Research Alignment Criteria

Target faculty members must actively conduct research in domains aligned with Forhad Uddin Ahmed's profile (`PROFILE_INSTRUCTIONS.md`):
- **Priority 1 (High)**:
  - Machine Learning & Deep Learning (architectures, optimization, foundation models)
  - Explainable AI (XAI) & Interpretable Machine Learning
  - Predictive Modeling & Time Series Forecasting
  - AI-driven Software Engineering (SE for AI, AI for SE, code intelligence, program repair)
- **Priority 2 (Medium)**:
  - Natural Language Processing (NLP) & Large Language Models (LLMs)
  - Intelligent Systems, Autonomous Agents & Robust Decision-Making
  - Multimodal Learning & Computer Vision
  - Healthcare AI & Financial AI
- **Priority 3 (Low)**:
  - Systems for ML, Distributed Systems, Cloud Computing, Data Mining

---

## 3. Mandatory Google Sheet Schema & Data Standards (29 Columns)

All rows added to the Google Sheet must adhere strictly to these column formats:

| Col Index | Column Name | Type / Format | Requirement | Description / Value Example |
| :---: | :--- | :--- | :--- | :--- |
| **A** (1) | `Professor Name` | String | **Mandatory** | Official name with title (e.g., `Prof. Sanja Fidler`). |
| **B** (2) | `University` | String | **Mandatory** | Full university name (e.g., `University of Toronto`). |
| **C** (3) | `Country` | String | **Mandatory** | `Canada`. |
| **D** (4) | `Department/Lab` | String | **Mandatory** | Specific department or school name. |
| **E** (5) | `Contact Group (Lock)` | String | **Mandatory** | Unique group lock identifier formatted as `<UNIV>-<DEPT>-<SUBAREA>` (e.g., `UTORONTO-CS-ML`). |
| **F** (6) | `Priority` | Integer | **Mandatory** | `1` (High), `2` (Medium), or `3` (Low). |
| **G** (7) | `Professor Profile URL` | URL (String) | **Mandatory** | Direct link to official faculty page or lab homepage. |
| **H** (8) | `Google Scholar URL` | URL (String) | **Mandatory** | Direct link to verified Google Scholar profile. |
| **I** (9) | `Research Area` | String | **Mandatory** | Concise comma-separated keywords (e.g., `Machine Learning, Explainable AI, Software Engineering`). |
| **J** (10) | `Funding Status` | String | **Mandatory** | `Funded MSc / MASc / GRA / NSERC Available`. |
| **K** (11) | `Deadline` | String | Optional | Intake deadline or empty string `""`. |
| **L** (12) | `Pipeline Status` | String | **Mandatory** | Set strictly to `Pending` for new discovery entries. |
| **M** (13) | `Target Timezone` | String | **Mandatory** | `America/Toronto`, `America/Vancouver`, or `America/Edmonton`. |
| **N** (14) | `Preferred Send Day/Time(BDTime)` | String | **Mandatory** | Regional window: `Mon-Thu 6:00 PM - 9:00 PM` (Eastern), `Mon-Thu 7:00 PM - 10:00 PM` (Mountain), or `Mon-Thu 9:00 PM - 12:00 AM` (Pacific). |
| **O–Q** | `LLM Summary / Fit / Subject` | String | Empty | Generated during outreach drafting. |
| **R** (18) | `Professor Email` | String | **Mandatory** | Verified academic email with official Canadian institutional domain (e.g. `@cs.toronto.edu`, `@uwaterloo.ca`, `@cs.ubc.ca`, `@ualberta.ca`, `@cs.mcgill.ca`). |
| **S–AC** | `Email Draft & Action Tracking`| String | Empty | Generated and populated during outreach progression. |

---

## 4. Verification & Duplicate Prevention Protocol

1. **Anti-Duplicate Verification**:
   - Every candidate must be cross-checked against all 1,305 existing professors in the Google Sheet (both Name and Email).
   - Zero duplication with existing professors.
2. **Institutional Email Mandate**:
   - Only official university email domains ending in `.ca` (e.g. `@cs.toronto.edu`, `@uwaterloo.ca`, `@cs.ubc.ca`, `@ualberta.ca`, `@cs.mcgill.ca`, `@uwo.ca`, `@queensu.ca`, `@uottawa.ca`, `@mcmaster.ca`, `@ucalgary.ca`) are accepted. No personal Gmail/Yahoo addresses.
3. **Contiguous Block Placement**:
   - The new Canada entries must be inserted directly after row 1305 (the end of the USA block), forming a new, continuous `Canada` block so that all records remain organized contiguously by country.
