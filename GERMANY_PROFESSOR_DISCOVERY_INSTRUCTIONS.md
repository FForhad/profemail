# Standard Operating Procedure (SOP): Germany Professor Discovery & Sheet Population

This document specifies the standard workflow, institutional targets, validation rules, and data schemas for discovering, vetting, and populating faculty records for universities in Germany (QS World University Rankings $\le$ 250 and top technical/excellence universities) into the PhD outreach tracking system.

---

## 1. Target Institutional Scope (QS Rank $\le$ 250 & Excellence Clusters)

Target institutions must be recognized German universities within the QS Top 250 or major European AI/CS excellence hubs:

### Primary Target Universities:
1. **Technical University of Munich (TUM)** — QS ~#28
   - Department of Computer Science / TUM School of Computation, Information and Technology (CIT)
   - Contact Group prefix: `TUM-CIT`, `TUM-CS`
2. **Ludwig Maximilian University of Munich (LMU Munich)** — QS ~#54
   - Institute of Informatics / Munich Center for Machine Learning (MCML)
   - Contact Group prefix: `LMU-CS`, `LMU-MCML`
3. **Heidelberg University** — QS ~#87
   - Institute of Computer Science / Interdisciplinary Center for Scientific Computing (IWR)
   - Contact Group prefix: `HEIDELBERG-CS`
4. **Karlsruhe Institute of Technology (KIT)** — QS ~#102
   - Department of Informatics / KASTEL / Institute for Program Structures and Data Organization (IPD)
   - Contact Group prefix: `KIT-CS`, `KIT-IN`
5. **RWTH Aachen University** — QS ~#106
   - Computer Science Department / Chair of Software Engineering / Information Systems
   - Contact Group prefix: `RWTH-CS`
6. **Technical University of Berlin (TU Berlin)** — QS ~#154
   - Faculty IV - Electrical Engineering and Computer Science / BIFOLD (Berlin Institute for the Foundations of Learning and Data)
   - Contact Group prefix: `TUB-CS`, `TUB-EECS`
7. **University of Freiburg** — QS ~#189
   - Department of Computer Science / Autonomous Intelligent Systems / BrainLinks-BrainTools
   - Contact Group prefix: `FREIBURG-CS`
8. **University of Tübingen** — QS ~#213
   - Department of Computer Science / Cyber Valley / Tübingen AI Center
   - Contact Group prefix: `TUEBINGEN-CS`, `TUEBINGEN-AI`
9. **University of Bonn** — QS ~#239
   - Institute of Computer Science / Lamarr Institute for Machine Learning and Artificial Intelligence
   - Contact Group prefix: `BONN-CS`
10. **Technical University of Darmstadt (TU Darmstadt)** — QS ~#246
    - Department of Computer Science / Hessian Center for Artificial Intelligence (hessian.AI)
    - Contact Group prefix: `TUD-CS`, `TUD-AI`
11. **Max Planck Institutes & Research Centers**:
    - Max Planck Institute for Informatics (MPI-INF, Saarbrücken) — `MPI-INF`
    - Max Planck Institute for Intelligent Systems (MPI-IS, Tübingen/Stuttgart) — `MPI-IS`

---

## 2. Research Alignment Criteria

Target faculty members must actively conduct research in domains aligned with Forhad Uddin Ahmed's profile (`PROFILE_INSTRUCTIONS.md`):
- **Priority 1 (High)**:
  - Machine Learning & Deep Learning (foundations, architectures)
  - Explainable AI (XAI) & Interpretable Machine Learning
  - Predictive Modeling & Time Series Forecasting
  - AI-driven Software Engineering (automated debugging, code intelligence)
- **Priority 2 (Medium)**:
  - Natural Language Processing (NLP) & Large Language Models (LLMs)
  - Computer Vision & Multimodal Learning
  - Intelligent Systems, Robotics & Cyber-Physical Systems
  - Data Mining & Knowledge Graphs
- **Priority 3 (Low)**:
  - Systems for ML, Distributed Systems, Cloud Computing, AI Security & Privacy

---

## 3. Mandatory Google Sheet Schema & Data Standards

All rows added to the Google Sheet must adhere strictly to these column formats:

| Column Name | Type / Format | Requirement | Description / Value Example |
| :--- | :--- | :--- | :--- |
| `Professor Name` | String | **Mandatory** | Official name with German academic title (e.g., `Prof. Dr. Matthias Niessner`). |
| `University` | String | **Mandatory** | Official English/German university name (e.g., `Technical University of Munich`). |
| `Country` | String | **Mandatory** | `Germany`. |
| `Department/Lab` | String | **Mandatory** | Specific department, chair (Lehrstuhl), or institute name. |
| `Contact Group (Lock)` | String | **Mandatory** | Unique group lock identifier formatted as `<UNIV>-<DEPT>` (e.g., `TUM-CS`, `KIT-CS`). |
| `Pipeline Status` | String | **Mandatory** | Set strictly to `Pending` for new entries. |
| `Priority` | Integer | **Mandatory** | `1` (High), `2` (Medium), or `3` (Low). |
| `Professor Email` | String | **Mandatory** | Verified academic email (e.g., `@tum.de`, `@kit.edu`, `@rwth-aachen.de`). |
| `Professor Profile URL` | URL (String) | **Mandatory** | Direct link to official faculty page or lab homepage. |
| `Google Scholar URL` | URL (String) | **Mandatory** | Direct link to verified Google Scholar profile. |
| `Research Area` | String | **Mandatory** | Concise comma-separated keywords (e.g., `Machine Learning, Explainable AI, Computer Vision`). |
| `Funding Status` | String | Mandatory | `DAAD / DFG / University Fellowship / RA Available`. |
| `Target Timezone` | String | Mandatory | `CET/CEST (UTC+1/+2)`. |
| `Preferred Send Day/Time(BDTime)` | String | Mandatory | `Mon-Thu 1:00 PM - 4:00 PM`. |

---

## 4. Verification & Duplicate Prevention Protocol

1. **Anti-Duplicate Verification**:
   - Every candidate must be cross-checked against existing professors in the Google Sheet (both Name and Email).
   - Ensure existing German professors (e.g. at RWTH Aachen) are never duplicated or overwritten.
2. **Institutional Email Mandate**:
   - Only official university email domains ending in `.de` or `.edu` (e.g. `@tum.de`, `@kit.edu`, `@lmu.de`, `@tu-berlin.de`, `@uni-tuebingen.de`, `@cs.tu-darmstadt.de`, `@uni-freiburg.de`, `@uni-bonn.de`) are accepted.
3. **Contiguous Block Placement**:
   - The new Germany entries must be inserted into the existing Germany block so that all German professors remain grouped contiguously.
