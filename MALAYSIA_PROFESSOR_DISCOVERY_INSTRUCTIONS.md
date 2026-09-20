# Standard Operating Procedure (SOP): Malaysia Professor Discovery & Sheet Population

This document specifies the standard workflow, institutional targets, validation rules, and data schemas for discovering, vetting, and populating faculty records for universities in Malaysia (QS World University Rankings $\le$ 250 and top research universities) into the PhD outreach tracking system.

---

## 1. Target Institutional Scope (QS Rank $\le$ 250 & Top Research Universities)

Target institutions must be recognized Malaysian research universities within or near the QS Top 250:

### Primary Target Universities:
1. **Universiti Malaya (UM)** — QS ~#60
   - Faculty of Computer Science & Information Technology (FCSIT)
   - Contact Group prefix: `UM-FCSIT`
   - Domains: `um.edu.my`
2. **Universiti Kebangsaan Malaysia (UKM)** — QS ~#138
   - Faculty of Information Science & Technology (FTSM)
   - Contact Group prefix: `UKM-FTSM`
   - Domains: `ukm.edu.my`
3. **Universiti Sains Malaysia (USM)** — QS ~#146
   - School of Computer Sciences
   - Contact Group prefix: `USM-CS`
   - Domains: `usm.my`, `cs.usm.my`
4. **Universiti Putra Malaysia (UPM)** — QS ~#148
   - Faculty of Computer Science & Information Technology (FSKTM)
   - Contact Group prefix: `UPM-FSKTM`
   - Domains: `upm.edu.my`
5. **Universiti Teknologi Malaysia (UTM)** — QS ~#181
   - Faculty of Computing
   - Contact Group prefix: `UTM-COMP`
   - Domains: `utm.my`
6. **Universiti Teknologi PETRONAS (UTP)** — QS ~#269
   - Department of Computer & Information Sciences
   - Contact Group prefix: `UTP-CIS`
   - Domains: `utp.edu.my`
7. **Taylor's University** — QS ~#251
   - School of Computer Science
   - Contact Group prefix: `TAYLORS-CS`
   - Domains: `taylors.edu.my`
8. **Sunway University**
   - School of Engineering and Technology / Department of Computing and Information Systems
   - Contact Group prefix: `SUNWAY-SET`
   - Domains: `sunway.edu.my`, `imail.sunway.edu.my`

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
  - Computer Vision & Image Processing
  - Intelligent Systems, Robotics & Cyber-Physical Systems
  - Data Mining & Knowledge Graphs
- **Priority 3 (Low)**:
  - Systems for ML, Distributed Systems, Cloud Computing, AI Security & Privacy, General Data Science

---

## 3. Mandatory Google Sheet Schema & Data Standards

All rows added to the Google Sheet must adhere strictly to these column formats:

| Column Name | Type / Format | Requirement | Description / Value Example |
| :--- | :--- | :--- | :--- |
| `Professor Name` | String | **Mandatory** | Official name with academic title (e.g., `Prof. Dr. Choo Peng Tan`, `Assoc. Prof. Dr. Norisma Idris`). |
| `University` | String | **Mandatory** | Official university name (e.g., `Universiti Malaya`). |
| `Country` | String | **Mandatory** | `Malaysia`. |
| `Department/Lab` | String | **Mandatory** | Specific faculty, department, or school name. |
| `Contact Group (Lock)` | String | **Mandatory** | Unique group lock identifier formatted as `<UNIV>-<DEPT>` (e.g., `UM-FCSIT`, `UTM-COMP`). |
| `Priority` | Integer | **Mandatory** | `1` (High), `2` (Medium), or `3` (Low). |
| `Professor Email` | String | **Mandatory** | Verified academic email (e.g., `@um.edu.my`, `@utm.my`, `@usm.my`). |
| `Professor Profile URL` | URL (String) | **Mandatory** | Direct link to official faculty directory page or lab homepage. |
| `Google Scholar URL` | URL (String) | **Mandatory** | Direct link to verified Google Scholar profile. |
| `Research Area` | String | **Mandatory** | Concise comma-separated keywords (e.g., `Machine Learning, Explainable AI, Computer Vision`). |
| `Funding Status` | String | Mandatory | `GRA / FRGS / University Fellowship / Graduate Assistantship Available`. |
| `Deadline` | String | Optional | Empty string `""` unless specific intake deadline applies. |
| `Pipeline Status` | String | **Mandatory** | Set strictly to `Pending` for new entries. |
| `Target Timezone` | String | Mandatory | `MYT (UTC+8)`. |
| `Preferred Send Day/Time(BDTime)` | String | Mandatory | `Mon-Thu 8:00 AM - 11:00 AM` (corresponding to 10:00 AM – 1:00 PM Malaysia time). |

---

## 4. Verification & Duplicate Prevention Protocol

1. **Anti-Duplicate Verification**:
   - Every candidate must be cross-checked against all existing professors in the Google Sheet (both Name and Email).
   - Ensure the 29 existing Malaysian professors (rows 308–336) and all other records are never duplicated or overwritten.
2. **Institutional Email Mandate**:
   - Only official university email domains ending in `.edu.my` or `.my` (e.g. `@um.edu.my`, `@ukm.edu.my`, `@usm.my`, `@upm.edu.my`, `@utm.my`, `@utp.edu.my`, `@taylors.edu.my`, `@sunway.edu.my`) are accepted.
3. **Contiguous Block Placement**:
   - The new Malaysia entries must be inserted directly into the existing Malaysia block (immediately following row 336) so that all Malaysian professors remain grouped contiguously.
