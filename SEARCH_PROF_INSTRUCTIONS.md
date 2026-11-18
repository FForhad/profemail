# Standard Operating Procedure (SOP): `SearchProf` Discovery & Staging Workflow

This document defines the procedure for discovering prospective professors via web search, logging them into the **`SearchProf`** staging sheet, generating outreach drafts, and managing concurrency locks.

---

## 1. Purpose & Staging Concept

**`SearchProf`** serves as a lightweight, flexible **discovery buffer**:
* Allows ad-hoc manual or automated searching of professors across universities and countries.
* Keeps raw/unvetted candidates separate from the primary 29-column production pipeline in **`Professors List`**.
* Enforces the same departmental concurrency locking rules to protect outreach integrity.

---

## 2. Spreadsheet Schema (11 Columns)

The **`SearchProf`** sheet is organized with the following streamlined headers:

| Col | Header | Required | Purpose & Rules |
| :---: | :--- | :---: | :--- |
| **A** | `Professor Name` | **Yes** | Full name with title (e.g. *Prof. Dr. Jane Doe*). |
| **B** | `University` | **Yes** | Full name of the institution (e.g. *Carnegie Mellon University*). |
| **C** | `Country` | **Yes** | Host country (e.g. *Canada*, *Germany*, *USA*, *Malaysia*). |
| **D** | `Department/Lab` | **Yes** | Department, school, or research lab (e.g. *School of Computer Science*). |
| **E** | `Contact Group (Lock)` | **Yes** | Departmental lock key (e.g. `CMU-CS`, `TUM-CIT`, `UT-CS`). Prevents simultaneous outreach to faculty in the same department. |
| **F** | `Professor Email` | **Yes** | Official institutional email address (prioritizing email explicitly stated in post). |
| **G** | `Google Scholar / Profile URL` | **Yes** | Official profile link or Google Scholar profile. |
| **H** | `Post Age (Days)` | **Yes** | **Strictly < 7 Days**. Number of days since the recruitment announcement was published. |
| **I** | `Email Draft` | Auto / Manual | Generated outreach email draft ($\le 150$ words, strictly adhering to academic constraints). |
| **J** | `Status` | **Yes** | Staging status: `Pending`, `Needs Review`, `Approved`, `Promoted`, or `Discarded`. |
| **K** | `Notes` | Optional | Funding breakdown, intake semester, and original LinkedIn post link. |

---

## 3. LinkedIn Discovery Protocol (Exclusive Source)

All future opportunity discovery for **`SearchProf`** must be sourced **strictly from LinkedIn posts published within the last 7 days**.

### A. Primary LinkedIn Search Filters
1. Open LinkedIn and use the search bar with targeted academic recruitment keywords.
2. Filter by: **`Posts`**.
3. Filter by **Date Posted**: Select **`Past Week`** or **`Past 24 Hours`** (Guarantees `Post Age < 7 Days`).
4. Sort by: **`Latest`**.

### B. High-Yield LinkedIn Search Strings
Copy and paste these exact strings into the LinkedIn search box:

* **Funded Master's & GRA Calls**:
  ```text
  ("Graduate Research Assistant" OR "GRA" OR "RA") AND ("Master's" OR "MSc" OR "Master") AND ("Machine Learning" OR "AI" OR "Deep Learning") AND ("funded" OR "stipend")
  ```
* **Professor Recruitment Announcements**:
  ```text
  ("I am hiring" OR "looking for students" OR "openings in my lab") AND ("Master's" OR "MSc" OR "PhD") AND ("Machine Learning" OR "Explainable AI" OR "Time Series")
  ```
* **Regional Intakes (Spring/Fall 2027)**:
  ```text
  "Research Assistant" AND ("Spring 2027" OR "Fall 2027" OR "January 2027") AND ("Computer Science" OR "Machine Learning")
  ```
* **Assistant Professor Startup Lab Hiring**:
  ```text
  "Assistant Professor" AND ("excited to announce" OR "joining") AND ("recruiting" OR "accepting") AND ("Master's" OR "PhD")
  ```

---

## 4. Vetting & Logging Protocol

For every LinkedIn post discovered:
1. **Recency Verification**: Check post timestamp (e.g., `1d`, `3d`, `5d`). If $\ge 7$ days, exclude.
2. **Email Extraction Priority**: If the LinkedIn post specifies a contact email address (e.g., *"Send your CV to professor@univ.edu"* or a dedicated lab email), **always prioritize and log that exact email** into the `Professor Email` column. If no email is provided in the post, look up their verified institutional faculty email from the official university directory.
3. **Professor & Institutional Verification**: Extract professor's full name, institution, and verify their profile / Google Scholar URL.
4. **Log into `SearchProf`**:
   * Add Professor Name, University, Department, Contact Group Lock.
   * Add the prioritized email and profile URL.
   * Set `Post Age (Days)` to the exact days count ($< 7$).
   * In `Notes`, paste the original LinkedIn post link, funding details, and application remarks.
   * Set `Status` to `Pending`.

1. **Department Concurrency Lock**:
   - Check if the candidate's `Contact Group (Lock)` is already active in **`SearchProf`** or **`Professors List`** (with status `Needs Review`, `Approved`, or `Applied`).
   - If locked, do not draft or send; leave candidate status as `Pending` or note for future intake.
2. **Recent Publication Check**:
   - Verify that the professor has published actively in **2025 or 2026** in fields aligned with Forhad's background (ML, XAI, Time Series, AI-driven SE).
3. **Degree & Intake Alignment**:
   - **USA**: Inquire about funded **PhD** opportunities for **Spring/Fall 2027**.
   - **Non-USA**: Inquire about funded **Master's** (GRA) opportunities for **Spring/Fall 2027**.

---

## 5. Accessing `SearchProf` via CLI & Code

### CLI Management Commands
To run the automated drafting agent against `SearchProf` instead of the main sheet, supply the `--worksheet` argument:

```bash
# Draft outreach for the next eligible professor in SearchProf
python manage.py draft_next --worksheet "SearchProf"

# Process up to 3 professors in SearchProf
python manage.py draft_next --worksheet "SearchProf" --limit 3
```

### Python / Script Access
```python
import os, gspread
from dotenv import load_dotenv

load_dotenv()
gc = gspread.service_account(filename="credentials.json")
sh = gc.open_by_url(os.getenv("GOOGLE_SHEET_URL"))

# Access the SearchProf worksheet directly
search_sheet = sh.worksheet("SearchProf")
records = search_sheet.get_all_records()
```

---

## 6. Graduation / Moving to `Professors List`

When a candidate in `SearchProf` is reviewed and approved for official outreach:
1. **Direct Copy-Paste**:
   - Copy the values from columns A–E (`Professor Name` through `Professor Email`) and F (`Google Scholar / Profile URL`).
   - Paste them into the corresponding columns of the appropriate country block in **`Professors List`**.
   - Set `Pipeline Status` in **`Professors List`** to `Pending` (or `Needs Review` if the draft is already completed).
2. **Update Staging Status**:
   - Mark `Status` in **`SearchProf`** as **`Promoted`** to preserve history and prevent duplicate outreach.
