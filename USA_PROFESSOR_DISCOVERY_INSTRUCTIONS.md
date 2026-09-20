# Standard Operating Procedure (SOP): USA Professor Discovery & Sheet Population

This document specifies the standard workflow, institutional targets, validation rules, and data schemas for discovering, vetting, and populating faculty records for universities in the United States (QS World University Rankings $\le$ 100 and top US CS/AI R1 programs) into the PhD outreach tracking system.

---

## 1. Target Institutional Scope (QS Rank $\le$ 100 & Top US CS Programs)

Target institutions must be recognized US research universities within the QS Top 100 or top-ranked Computer Science programs in CSRankings:

### Primary Target Universities & Regional Timezones:

#### Eastern Timezone (`EST/EDT`, BD Time `Mon-Thu 6:00 PM - 9:00 PM`):
1. **Carnegie Mellon University (CMU)** — School of Computer Science (`CMU-CS`) — `cmu.edu`, `cs.cmu.edu`
2. **Massachusetts Institute of Technology (MIT)** — Department of Electrical Engineering and Computer Science (`MIT-EECS`) — `mit.edu`, `csail.mit.edu`
3. **Cornell University** — Department of Computer Science (`CORNELL-CS`) — `cornell.edu`, `cs.cornell.edu`
4. **Columbia University** — Department of Computer Science (`COLUMBIA-CS`) — `columbia.edu`, `cs.columbia.edu`
5. **Georgia Institute of Technology (Georgia Tech)** — College of Computing (`GATECH-CS`) — `gatech.edu`, `cc.gatech.edu`
6. **University of Michigan, Ann Arbor** — Computer Science and Engineering (`UMICH-CSE`) — `umich.edu`, `eecs.umich.edu`
7. **University of Maryland, College Park** — Department of Computer Science (`UMD-CS`) — `umd.edu`, `cs.umd.edu`
8. **Harvard University** — John A. Paulson School of Engineering and Applied Sciences (`HARVARD-SEAS`) — `harvard.edu`, `seas.harvard.edu`
9. **Princeton University** — Department of Computer Science (`PRINCETON-CS`) — `princeton.edu`, `cs.princeton.edu`
10. **University of Pennsylvania (UPenn)** — Department of Computer and Information Science (`UPENN-CIS`) — `upenn.edu`, `seas.upenn.edu`
11. **Johns Hopkins University** — Department of Computer Science (`JHU-CS`) — `jhu.edu`, `cs.jhu.edu`
12. **New York University (NYU)** — Courant Institute of Mathematical Sciences (`NYU-CS`) — `nyu.edu`, `cs.nyu.edu`

#### Central Timezone (`CST/CDT`, BD Time `Mon-Thu 7:00 PM - 10:00 PM`):
13. **University of Illinois Urbana-Champaign (UIUC)** — Siebel School of Computing and Data Science (`UIUC-CS`) — `illinois.edu`, `cs.illinois.edu`
14. **University of Texas at Austin (UT Austin)** — Department of Computer Science (`UT-AUSTIN-CS`) — `utexas.edu`, `cs.utexas.edu`
15. **Purdue University** — Department of Computer Science (`PURDUE-CS`) — `purdue.edu`, `cs.purdue.edu`
16. **University of Wisconsin–Madison** — Department of Computer Sciences (`UW-MADISON-CS`) — `wisc.edu`, `cs.wisc.edu`
17. **Northwestern University** — Department of Computer Science (`NORTHWESTERN-CS`) — `northwestern.edu`, `cs.northwestern.edu`

#### Pacific Timezone (`PST/PDT`, BD Time `Mon-Thu 9:00 PM - 12:00 AM`):
18. **Stanford University** — Department of Computer Science (`STANFORD-CS`) — `stanford.edu`, `cs.stanford.edu`
19. **University of California, Berkeley (UC Berkeley)** — Department of Electrical Engineering and Computer Sciences (`BERKELEY-EECS`) — `berkeley.edu`, `eecs.berkeley.edu`, `cs.berkeley.edu`
20. **University of Washington (UW)** — Paul G. Allen School of Computer Science & Engineering (`UW-CSE`) — `washington.edu`, `cs.washington.edu`
21. **University of California, San Diego (UCSD)** — Department of Computer Science and Engineering (`UCSD-CSE`) — `ucsd.edu`, `cs.ucsd.edu`
22. **University of California, Los Angeles (UCLA)** — Computer Science Department (`UCLA-CS`) — `ucla.edu`, `cs.ucla.edu`
23. **University of Southern California (USC)** — Department of Computer Science (`USC-CS`) — `usc.edu`, `cs.usc.edu`

---

## 2. Research Alignment Criteria

Target faculty members must actively conduct research in domains aligned with Forhad Uddin Ahmed's profile (`PROFILE_INSTRUCTIONS.md`):
- **Priority 1 (High)**:
  - Machine Learning & Deep Learning (foundations, architectures, optimization)
  - Explainable AI (XAI) & Interpretable Machine Learning
  - Predictive Modeling & Time Series Forecasting
  - AI-driven Software Engineering (code intelligence, program synthesis, automated debugging)
- **Priority 2 (Medium)**:
  - Natural Language Processing (NLP) & Large Language Models (LLMs)
  - Computer Vision & Multimodal Learning
  - Intelligent Systems, Robotics & Autonomous Agents
  - Data Mining & Knowledge Graphs
- **Priority 3 (Low)**:
  - Systems for ML, Distributed Systems, Cloud Computing, AI Security & Privacy

---

## 3. Mandatory Google Sheet Schema & Data Standards

All rows added to the Google Sheet must adhere strictly to these column formats:

| Column Name | Type / Format | Requirement | Description / Value Example |
| :--- | :--- | :--- | :--- |
| `Professor Name` | String | **Mandatory** | Official name with title (e.g., `Prof. Dan Roth`, `Prof. Percy Liang`). |
| `University` | String | **Mandatory** | Full university name (e.g., `Carnegie Mellon University`). |
| `Country` | String | **Mandatory** | `USA`. |
| `Department/Lab` | String | **Mandatory** | Specific department or school name. |
| `Contact Group (Lock)` | String | **Mandatory** | Unique group lock identifier formatted as `<UNIV>-<DEPT>` (e.g., `CMU-CS`, `MIT-EECS`). |
| `Priority` | Integer | **Mandatory** | `1` (High), `2` (Medium), or `3` (Low). |
| `Professor Email` | String | **Mandatory** | Verified academic email (e.g., `@cs.cmu.edu`, `@cs.stanford.edu`). |
| `Professor Profile URL` | URL (String) | **Mandatory** | Direct link to official faculty page or lab homepage. |
| `Google Scholar URL` | URL (String) | **Mandatory** | Direct link to verified Google Scholar profile. |
| `Research Area` | String | **Mandatory** | Concise comma-separated keywords (e.g., `Machine Learning, Explainable AI, Computer Vision`). |
| `Funding Status` | String | Mandatory | `RA / TA / University Fellowship / NSF Funded Available`. |
| `Deadline` | String | Optional | Intake deadline or empty string `""`. |
| `Pipeline Status` | String | **Mandatory** | Set strictly to `Pending` for new entries. |
| `Target Timezone` | String | Mandatory | `EST/EDT (UTC-5/-4)`, `CST/CDT (UTC-6/-5)`, or `PST/PDT (UTC-8/-7)`. |
| `Preferred Send Day/Time(BDTime)` | String | Mandatory | Regional window: `Mon-Thu 6:00 PM - 9:00 PM` (EST), `Mon-Thu 7:00 PM - 10:00 PM` (CST), or `Mon-Thu 9:00 PM - 12:00 AM` (PST). |

---

## 4. Verification & Duplicate Prevention Protocol

1. **Anti-Duplicate Verification**:
   - Every candidate must be cross-checked against all 953 existing professors in the Google Sheet (both Name and Email).
   - Ensure the 98 existing USA professors (rows 559–656) and all other country records are never duplicated or overwritten.
2. **Institutional Email Mandate**:
   - Only official university email domains ending in `.edu` (e.g. `@cmu.edu`, `@stanford.edu`, `@mit.edu`, `@berkeley.edu`, `@illinois.edu`, `@gatech.edu`, `@umich.edu`, `@washington.edu`) are accepted.
3. **Contiguous Block Placement**:
   - The new USA entries must be inserted directly into the existing USA block (immediately following row 656) so that all USA professors remain grouped contiguously.
