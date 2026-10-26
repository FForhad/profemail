# Standard Operating Procedure (SOP): Malaysia Professor Discovery & Sheet Population

This document specifies the standard workflow, institutional targets, validation rules, and data schemas for discovering, vetting, and populating faculty records for universities in Malaysia (QS World University Rankings $\le$ 600 and top research universities) into the graduate outreach tracking system, with special emphasis on Senior Lecturers with prospective funding.

---

## 1. Target Institutional Scope (QS Rank $\le$ 600 & Top Research Universities)

Target institutions include recognized Malaysian research universities and premier technology institutes within the QS Top 600:

### Primary Research Universities (QS 1–250):
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

### Top Tier & Established Private / Specialized Universities (QS 251–600):
6. **Taylor's University** — QS ~#251
   - School of Computer Science
   - Contact Group prefix: `TAYLORS-CS`
   - Domains: `taylors.edu.my`
7. **UCSI University** — QS ~#265
   - Institute of Computer Science and Digital Innovation (ICSDI)
   - Contact Group prefix: `UCSI-ICSDI`
   - Domains: `ucsiuniversity.edu.my`
8. **Universiti Teknologi PETRONAS (UTP)** — QS ~#269
   - Department of Computer & Information Sciences
   - Contact Group prefix: `UTP-CIS`
   - Domains: `utp.edu.my`
9. **INTI International University** — QS ~#516
   - Faculty of Information and Communications Technology (FICT)
   - Contact Group prefix: `INTI-FICT`
   - Domains: `newinti.edu.my`
10. **Sunway University** — QS ~#539
    - School of Engineering and Technology / Department of Computing and Information Systems
    - Contact Group prefix: `SUNWAY-SET`
    - Domains: `sunway.edu.my`, `imail.sunway.edu.my`
11. **Universiti Utara Malaysia (UUM)** — QS ~#554
    - School of Computing (SOC)
    - Contact Group prefix: `UUM-SOC`
    - Domains: `uum.edu.my`
12. **Universiti Tunku Abdul Rahman (UTAR)** — QS ~#550-600
    - Lee Kong Chian Faculty of Engineering and Science (LKC FES) / Faculty of Information and Communication Technology (FICT)
    - Contact Group prefix: `UTAR-FICT`
    - Domains: `utar.edu.my`
13. **Universiti Tenaga Nasional (UNITEN)** — QS ~#550-600
    - College of Computing and Informatics (CCI)
    - Contact Group prefix: `UNITEN-CCI`
    - Domains: `uniten.edu.my`
14. **Universiti Malaysia Pahang Al-Sultan Abdullah (UMPSA)** — QS ~#600
    - Faculty of Computing
    - Contact Group prefix: `UMPSA-COMP`
    - Domains: `umpsa.edu.my`
15. **Multimedia University (MMU)** — Premier Digital Tech University
    - Faculty of Computing and Informatics (FCI)
    - Contact Group prefix: `MMU-FCI`
    - Domains: `mmu.edu.my`
16. **Monash University Malaysia & University of Nottingham Malaysia** (Premier Global Campuses)
    - School of IT / School of Computer Science
    - Contact Group prefix: `MUM-IT`, `UNM-CS`
    - Domains: `monash.edu.my`, `nottingham.edu.my`

---

## 2. Senior Lecturer & Funding Qualification Criteria

Target faculty members must be **Senior Lecturers** (*Pensyarah Kanan*), Assistant Professors, or research-active faculty with indicators of active research funding:

1. **Academic Rank Focus**:
   - Primary target: **Senior Lecturer** (*Pensyarah Kanan*) / Assistant Professor.
   - Academic titles typically include: `Dr.`, `Ts. Dr.`, `Ir. Dr.`, or `Dr.` with Senior Lecturer appointment.
2. **Funding & GRA Qualification**:
   - Active grant holders under MOHE schemes: **FRGS** (*Fundamental Research Grant Scheme*), **PRGS** (*Prototype Development Research Grant*), or **LRGS**.
   - University-funded internal grants (e.g. UM Research Grant / Bantuan Penyelidikan, UKM GUP, UTM Tier 1/2, UPM GP, etc.).
   - Explicit graduate vacancies: Actively recruiting Master's by Research students with **Graduate Research Assistantship (GRA)** monthly stipends or tuition assistance.
3. **Research Domain Alignment**:
   - Faculty must conduct active research in domains aligned with Forhad Uddin Ahmed's profile (`PROFILE_INSTRUCTIONS.md`):
     - **Priority 1 (High)**: Explainable AI (XAI), Machine Learning & Deep Learning architectures, Predictive Modeling, AI-driven Software Engineering (automated debugging, code intelligence).
     - **Priority 2 (Medium)**: NLP & Large Language Models, Computer Vision, Intelligent Systems & Robotics, Healthcare / Financial AI Applications.
     - **Priority 3 (Low)**: Cloud Computing, IoT/Edge AI, Cybersecurity, Information Systems.

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
