# PhD Outreach Agent — Standard Workflow & Execution Instructions

This document defines the exact, step-by-step procedure the AI Agent must execute whenever instructed to process a professor, research their profile, draft an outreach email, and update the Google Sheet.

Whenever the user says:
- *"Process the next professor"*
- *"Draft next"*
- *"Read WORKFLOW_INSTRUCTIONS.md and do the work"*
- *"Execute the outreach workflow"*

Follow this document strictly from Step 1 through Step 7.

---

## Step 1: Environment & Context Verification

1. **Verify `.env` configuration**:
   - `GOOGLE_SHEET_URL`: URL of the outreach spreadsheet.
   - `GOOGLE_SHEET_NAME`: Default worksheet name (`Professors List`).
   - `GEMINI_API_KEY`: Active Google Gemini API key.
   - `GEMINI_MODEL`: Active model (`gemini-3.6-flash`).
2. **Verify `credentials.json`**:
   - Ensure the Google Cloud Service Account JSON file exists in project root.
3. **Load `PROFILE_INSTRUCTIONS.md`**:
   - Read the candidate's profile and constraints from `PROFILE_INSTRUCTIONS.md`.
   - **Critical Rule**: Forhad Uddin Ahmed must be introduced as an **"AI/ML Researcher and Software Engineer"**.
   - **Forbidden**: NEVER state or imply that he is currently a Lecturer (his BAIUST teaching appointment concluded in May 2026).
   - **Target Intake**: Funded Fall 2026 PhD positions.
   - **Inquiry phrasing**: Always ask if positions are expected (*"Do you expect to have PhD opportunities for Fall 2026?"*), never assume they are open.

---

## Step 2: Google Sheet Authentication & Reading

1. Authenticate using `gspread.service_account(filename="credentials.json")`.
2. Open the spreadsheet using `GOOGLE_SHEET_URL`.
3. Select the worksheet named `"Professors List"` (or worksheet index 0).
4. Fetch all rows as a list of dictionaries (`worksheet.get_all_records()`).
5. Read header column names from Row 1.

---

## Step 3: Concurrency & Lock Logic (Selecting 1 Candidate)

1. **Identify Locked Contact Groups**:
   - Check the `"Contact Group (Lock)"` and `"Pipeline Status"` columns for every row.
   - Any group that contains at least one professor with status:
     - `Researching`
     - `Needs Review`
     - `Approved`
     - `Applied`
     is considered **LOCKED**.
2. **Filter Eligible Candidates**:
   - A professor is eligible if and only if:
     - `"Pipeline Status"` == `"Pending"` **AND**
     - `"Contact Group (Lock)"` is **NOT** in the set of locked groups.
3. **Sort and Pick Candidates**:
   - Sort eligible professors by `"Priority"` (Priority `1` or `'High'` is highest; treat blanks/unranked as lowest priority, e.g. `999`).
   - Break ties using the sheet row index (lowest row first).
   - If user requests processing $N$ professors (e.g. `limit=2`), iterate through up to $N$ candidates, skipping any candidate whose Contact Group was locked by an earlier candidate in the same batch.
   - If no eligible candidate exists, output: `"No eligible professors found"` and exit gracefully.

---

## Step 4: Web & Google Scholar Scraping

1. Extract the selected professor's `"Google Scholar URL"` (or profile URL if Scholar is absent).
2. Make an HTTP request with realistic desktop browser headers (`User-Agent`, `Accept-Language`) to avoid basic scraping blocks.
3. Parse HTML with `BeautifulSoup`:
   - Target recent publication rows (table class `gsc_a_tr`).
   - Extract the 3–5 most recent paper titles, publication years, and co-authors.
   - Extract stated research areas/interests (tag `#gsc_prf_int a`).
4. **Accuracy Mandate**: Only use verified papers from the scraped data or sheet. **Never invent or hallucinate paper titles.**

---

## Step 5: LLM Synthesis with Gemini 3.6 Flash

1. Construct a structured prompt providing:
   - Full candidate context from `PROFILE_INSTRUCTIONS.md`.
   - Target professor's name, university, department, and known research area.
   - Scraped recent publications (titles and years).
2. Call `client.models.generate_content` with `model="gemini-3.6-flash"`.
3. Require the model to produce:
   - **LLM Research Summary**: 2–4 concise sentences analyzing the lab's recent direction, methodologies, and focus based on actual publications.
   - **LLM Fit Score (1–10)**: Realistic assessment of overlap with Forhad's background in ML, XAI, AI-driven Software Engineering, and full-stack software architecture.
   - **Email Subject**: Formal academic subject (e.g., `Prospective PhD Applicant – Fall 2026 – Forhad Uddin Ahmed`).
   - **Email Draft**:
     - Maximum **150 words**.
     - Addressed formally (`Dear Prof. Dr. <LastName>,`).
     - Positioning: *"I am Forhad Uddin Ahmed, an AI/ML Researcher and Software Engineer..."*
     - Cite 1–2 real papers from the scraped data.
     - Connect Forhad's actual research (Explainable AI, Machine Learning, software systems) to the professor's recent focus.
     - Respectful Fall 2026 PhD availability inquiry.
     - Professional sign-off.
4. **Pre-Save Verification**:
   - Check word count $\le 150$ words.
   - Check that no forbidden terms (e.g. "currently a Lecturer") appear.

---

## Step 6: Google Sheet Direct Update

1. Locate the exact row number of the selected professor (`sheet_row = record_index + 2`).
2. Map the relevant columns dynamically:
   - `"Pipeline Status"` (Column M) $\rightarrow$ Set to **`Needs Review`** *(Immediately locks the group for future runs)*
   - `"LLM Research Summary"` (Column P) $\rightarrow$ Insert generated summary
   - `"LLM Fit Score (1-10)"` (Column Q) $\rightarrow$ Insert fit score (e.g. `8` or `9`)
   - `"Email Subject"` (Column R) $\rightarrow$ Insert generated subject
   - `"Email Draft"` (Column S) $\rightarrow$ Insert generated draft
3. Perform the update via `worksheet.batch_update()` for speed and atomicity.

---

## Step 7: Output & Verification

Print a clean summary report to the user containing:
1. **Selected Professor & Group**: Name, University, Sheet Row, and Priority.
2. **Scraped Publications**: List of the papers identified.
3. **Generated Summary**: The exact text placed into the sheet.
4. **Email Subject & Draft**: The email content and its exact word count.
5. **Sheet Status**: Confirmation that row was saved with status `Needs Review`.
