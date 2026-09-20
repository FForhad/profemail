# Standard Operating Procedure (SOP): China Professor Discovery & Sheet Population

This document specifies the standard workflow, data schemas, validation rules, and execution steps for discovering, vetting, and populating faculty records for universities in China (QS World University Rankings $\le$ 250) into the PhD outreach tracking system.

---

## 1. Target Institutional Scope (QS Rank $\le$ 250)

Target institutions must be ranked within the top 250 of the QS World University Rankings. 

### Primary Target Universities (Mainland China):
1. **Peking University (PKU)** — QS ~#14
   - School of Computer Science / School of Artificial Intelligence / School of Electronics Engineering and Computer Science (EECS)
   - Contact Group prefix: `PKU-CS`, `PKU-AI`, `PKU-EECS`
2. **Tsinghua University (THU)** — QS ~#20
   - Department of Computer Science and Technology / Institute for AI / Department of Automation
   - Contact Group prefix: `THU-CS`, `THU-AI`, `THU-AUTO`
3. **Fudan University (FDU)** — QS ~#39
   - School of Computer Science / Academy for Engineering & Technology
   - Contact Group prefix: `FDU-CS`, `FDU-AI`
4. **Shanghai Jiao Tong University (SJTU)** — QS ~#45
   - Department of Computer Science and Engineering / John Hopcroft Center / SEIEE
   - Contact Group prefix: `SJTU-CS`, `SJTU-SEIEE`, `SJTU-AI`
5. **Zhejiang University (ZJU)** — QS ~#47
   - College of Computer Science and Technology / State Key Lab of CAD&CG
   - Contact Group prefix: `ZJU-CS`, `ZJU-CADCG`
6. **University of Science and Technology of China (USTC)** — QS ~#133
   - School of Computer Science and Technology / School of Information Science
   - Contact Group prefix: `USTC-CS`, `USTC-INFO`
7. **Nanjing University (NJU)** — QS ~#145
   - Department of Computer Science and Technology / National Key Lab for Novel Software Technology
   - Contact Group prefix: `NJU-CS`, `NJU-AI`
8. **Tongji University** — QS ~#192
   - Department of Computer Science and Technology / College of Electronic and Information Engineering
   - Contact Group prefix: `TONGJI-CS`, `TONGJI-CEIE`
9. **Wuhan University (WHU)** — QS ~#194
   - School of Computer Science / State Key Lab of Software Engineering
   - Contact Group prefix: `WHU-CS`, `WHU-SKLSE`
10. **Harbin Institute of Technology (HIT)** — QS ~#250
    - Faculty of Computing / School of Computer Science and Technology
    - Contact Group prefix: `HIT-CS`, `HIT-COMP`
11. **Hong Kong SAR Institutions (QS Top 100)** *(Optional / Complementary)*:
    - University of Hong Kong (HKU, ~#17) — `HKU-CS`
    - Chinese University of Hong Kong (CUHK, ~#36) — `CUHK-CSE`
    - Hong Kong University of Science and Technology (HKUST, ~#47) — `HKUST-CSE`
    - Hong Kong Polytechnic University (PolyU, ~#57) — `POLYU-COMP`
    - City University of Hong Kong (CityU, ~#62) — `CITYU-CS`

---

## 2. Research Alignment Criteria

Target faculty members must actively conduct research in domains aligned with Forhad Uddin Ahmed's profile (`PROFILE_INSTRUCTIONS.md`):
- **Primary Matches (Priority 1 - High)**:
  - Machine Learning & Deep Learning (foundations, architectures)
  - Explainable AI (XAI) & Interpretable Machine Learning
  - Predictive Modeling (health, finance, or cyber-physical systems)
  - AI-driven Software Engineering (automated debugging, code intelligence)
- **Secondary Matches (Priority 2 - Medium)**:
  - Natural Language Processing (NLP) & Large Language Models (LLMs)
  - Computer Vision & Multimodal Learning
  - Intelligent Systems & Robotics
  - Data Mining & Knowledge Graphs
- **Adjacent Matches (Priority 3 - Low)**:
  - Systems for ML, Distributed Computing, Cloud Systems

---

## 3. Mandatory Google Sheet Schema & Data Standards

All rows added to the Google Sheet must adhere strictly to these column formats:

| Column Name | Type / Format | Requirement | Description / Value Example |
| :--- | :--- | :--- | :--- |
| `Professor Name` | String | **Mandatory** | Official English / Pinyin name (e.g., `Prof. Zhi-Hua Zhou` or `Dr. Ming Zhang`). Avoid duplicate titles. |
| `University` | String | **Mandatory** | Official English university name (e.g., `Nanjing University`). |
| `Country` | String | **Mandatory** | `China` (or `Hong Kong`). |
| `Department/Lab` | String | **Mandatory** | Specific department, school, or state key laboratory name. |
| `Contact Group (Lock)` | String | **Mandatory** | Unique group lock identifier formatted as `<UNIV>-<DEPT>` (e.g., `NJU-CS`, `PKU-AI`). Enforces concurrency locks so no two professors in the same department are contacted concurrently. |
| `Pipeline Status` | String | **Mandatory** | Must be set strictly to `Pending` for new entries. |
| `Priority` | Integer / String | **Mandatory** | `1` (High), `2` (Medium), or `3` (Low). |
| `Professor Email` | String | **Mandatory** | Verified academic or institutional email address (e.g., `user@nju.edu.cn`, `user@tsinghua.edu.cn`). |
| `Professor Profile URL` | URL (String) | **Mandatory** | Official faculty directory page, university profile, or lab homepage. |
| `Google Scholar URL` | URL (String) | **Mandatory** | Direct URL to the professor's Google Scholar profile page (or Semantic Scholar URL). |
| `Research Area` | String | **Mandatory** | Concise comma-separated keywords (e.g., `Machine Learning, Explainable AI, Data Mining`). |
| `Recent Publications` | String | Optional/Recommended | 1–2 titles of verified recent papers (2024–2026). |
| `Funding Status` | String | Optional | `CSC / University Fellowship / RA Available` or leave blank. |

---

## 4. Verification & Anti-Hallucination Protocol

To guarantee 100% data integrity:
1. **Name & Title Check**: Verify faculty status on official departmental websites (Full Professor, Associate Professor, Assistant Professor, Tenure-Track Assistant Professor, or Young PI).
2. **Email Verification**: Only record official `.edu.cn` / institutional email addresses listed on official university pages or published academic papers.
3. **Google Scholar Validation**: Confirm the Scholar profile belongs to the exact faculty member (matching university affiliation and email domain).
4. **Duplicate Prevention**:
   - Before inserting, fetch existing rows from the Google Sheet.
   - Check both `Professor Name` and `Professor Email` against existing records to prevent duplicates.
5. **Batch Insertion via `gspread`**:
   - Accumulate verified records in structured JSON/dictionary batches.
   - Use `worksheet.append_rows()` or `worksheet.batch_update()` for atomic and efficient sheet updates without hitting Google Sheets API rate limits.
