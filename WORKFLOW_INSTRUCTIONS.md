**# PhD Outreach Agent — Standard Workflow & Execution Instructions**

This document defines the exact, step-by-step procedure the AI Agent must execute whenever instructed to process a professor, research their profile, draft an outreach email, and update the Google Sheet.

Whenever the user says:

- **"Process the next professor"**

- **"Draft next"**

- **"Read WORKFLOW_INSTRUCTIONS.md and do the work"**

- **"Execute the outreach workflow"**

Follow this document strictly from Step 1 through Step 7.

---

**## Step 1: Environment & Context Verification**

1. ****Verify `.env` configuration****:

- `GOOGLE_SHEET_URL`: URL of the outreach spreadsheet.

- `GOOGLE_SHEET_NAME`: Default worksheet name (`Professors List`).

- `GEMINI_API_KEY`: Active Google Gemini API key.

- `GEMINI_MODEL`: Active model (`gemini-3.6-flash`).

2. ****Verify `credentials.json`****:

- Ensure the Google Cloud Service Account JSON file exists in project root.

3. ****Load `PROFILE_INSTRUCTIONS.md`****:

- Read the candidate's profile and constraints from `PROFILE_INSTRUCTIONS.md`.

- ****Critical Rule****: Forhad Uddin Ahmed must be introduced as an ****"AI/ML Researcher and Software Engineer"****.

- ****Forbidden****: NEVER state or imply that he is currently a Lecturer (his BAIUST teaching appointment concluded in May 2026).

- ****Target Intake****: Funded Spring 2027 PhD positions.

- ****Inquiry phrasing****: Always ask if positions are expected (**"Do you expect to have PhD opportunities for Spring 2027?"**), never assume they are open.

---

**## Step 2: Google Sheet Authentication & Reading**

1. Authenticate using `gspread.service_account(filename="credentials.json")`.

2. Open the spreadsheet using `GOOGLE_SHEET_URL`.

3. Select the worksheet named `"Professors List"` (or worksheet index 0).

4. Fetch all rows as a list of dictionaries (`worksheet.get_all_records()`).

5. Read header column names from Row 1.

---

**## Step 3: Concurrency & Lock Logic (Selecting 1 Candidate)**

1. ****Identify Locked Contact Groups****:

- Check the `"Contact Group (Lock)"` and `"Pipeline Status"` columns for every row.

- Any group that contains at least one professor with status:

```
 \- \`Researching\`

 \- \`Needs Review\`

 \- \`Approved\`

 \- \`Applied\`

 is considered **\*\*LOCKED\*\***.
```

2. ****Filter Eligible Candidates****:

- A professor is eligible if and only if:

```
 \- \`"Pipeline Status"\` == \`"Pending"\` **\*\*AND\*\***

 \- \`"Contact Group (Lock)"\` is **\*\*NOT\*\*** in the set of locked groups.
```

3. ****Sort and Pick Candidates****:

- Sort eligible professors by `"Priority"` (Priority `1` or `'High'` is highest; treat blanks/unranked as lowest priority, e.g. `999`).

- Break ties using the sheet row index (lowest row first).

- If user requests processing $N$ professors (e.g. `limit=2`), iterate through up to $N$ candidates, skipping any candidate whose Contact Group was locked by an earlier candidate in the same batch.

- If no eligible candidate exists, output: `"No eligible professors found"` and exit gracefully.

---

**## Step 4: Web & Google Scholar Scraping**

1. Extract the selected professor's `"Google Scholar URL"` (or profile URL if Scholar is absent).
   - Ensure the Google Scholar query includes `&sortby=pubdate` so that publications are sorted in reverse chronological order (newest first).

2. Make an HTTP request with realistic desktop browser headers (`User-Agent`, `Accept-Language`) to avoid basic scraping blocks.

3. Parse HTML with `BeautifulSoup`:
   - Target publication rows (table class `gsc_a_tr`).
   - Extract the most recent paper titles, publication years (STRICTLY prioritizing **2025 and 2026**), and co-authors.
   - Extract stated research areas/interests (tag `#gsc_prf_int a`).

4. **Accuracy & Recency Mandate**: Only use verified recent papers from the scraped data or sheet. **Strictly prioritize 2025 and 2026 papers; do NOT select old papers from years ago when recent work is available. Never invent or hallucinate paper titles.**

---

**## Step 5: LLM Synthesis with Gemini 3.6 Flash**

1. Construct a structured prompt providing:

- Full candidate context from `PROFILE_INSTRUCTIONS.md`.

- Target professor's name, university, department, and known research area.

- Scraped recent publications (titles and years).

- Scraped research interests/interests, when available.

2. Call `client.models.generate_content` with `model="gemini-3.6-flash"`.

3. Require the model to produce:

- ****LLM Research Summary****: 2–4 concise sentences analyzing the professor's recent direction, methodologies, and focus based on actual verified publications and research interests.

- ****LLM Fit Score (1–10)****: Realistic assessment of overlap with Forhad's background in ML, XAI, predictive modeling, AI-driven Software Engineering, and software systems.

- ****Email Subject****: Formal academic subject (e.g., `Prospective PhD Applicant – Spring 2027 – Forhad Uddin Ahmed`).

- ****Email Draft****:

```
 \- Maximum **\*\*150 words\*\***.

 \- Addressed formally using full name (\`Dear Professor \<FullName>,\` or \`Dear Prof. Dr. \<FullName>,\`). Use the professor's actual academic title when available and never invent a title.

 \- Positioning: *"I am Forhad Uddin Ahmed, an AI/ML Researcher and Software Engineer..."*
 \- Do NOT state "I am applying for Spring 2027 funded PhD positions" in the introduction; only inquire about Spring 2027 PhD availability at the inquiry stage near the closing.
 \- Keep the introduction concise. Mention only the parts of Forhad's background that are relevant to the professor's research.

 \- Cite 1–2 real and relevant papers from the scraped data.

 \- Do not merely list paper titles. Briefly explain what aspect of the professor's work is relevant to Forhad's research interests.

 \- Connect Forhad's actual research in Explainable AI, Machine Learning, predictive modeling, and software systems to the professor's specific research direction.

 \- The connection must be technically credible and based on the actual research overlap. Do not force a connection simply to make the email appear personalized.

 \- Do not claim that Forhad has worked on a research area, method, dataset, problem, or technology unless it is explicitly supported by \`PROFILE\_INSTRUCTIONS.md\`.

 \- Do not claim that Forhad has read, implemented, reproduced, extended, or collaborated on the professor's work unless explicitly supported.

 \- Avoid generic statements such as \`"Your impressive research aligns perfectly with my interests."\`

 \- Avoid excessive praise, promotional language, or overly enthusiastic wording.

 \- Do not automatically describe a professor's work as \`foundational\`, \`groundbreaking\`, \`pioneering\`, \`seminal\`, or \`influential\`. Use these terms only when clearly supported by evidence. Otherwise use natural wording such as \`"your work on..."\`, \`"your research on..."\`, or \`"your paper..."\`.

 \- The email should feel like a serious researcher personally contacted the professor after examining their research, rather than a generic AI-generated PhD template.

 \- Use a natural research connection such as:
   
   \`Professor's specific research → relevant research problem → Forhad's related background → potential PhD research interest\`

 \- The research connection should be at the research/problem level, not merely because both use the same programming language, framework, or general technology.

 \- Respectful Spring 2027 PhD availability inquiry.

 \- Ask whether the professor **expects to have funded PhD opportunities for Spring 2027**. Never assume that a position is currently available.

 \- Mention that both **\*\*Resume and Academic Transcript\*\*** are attached for review (not just CV).

 \- Professional sign-off.
```

4. ********Email Style Requirements******:

- The preferred tone is concise, natural, technically informed, respectful, and academically mature.

- The email should not sound like a Statement of Purpose, cover letter, formal application essay, marketing message, or AI-generated template.

- Avoid unnecessary biography, detailed employment history, long lists of technologies, GPA, or unrelated achievements.

- The ideal structure is:

```

$$- Short introduction.

\\- Specific reference to the professor's research/paper.

\\- Brief explanation of the strongest genuine connection between that research and Forhad's background.

\\- Spring 2027 PhD inquiry.

\\- Resume and academic transcript mention.

\\- Professional sign-off.

\`\`\`

\- The email should be concise enough for a professor to understand the research fit within approximately 30–45 seconds.

\- Use direct and natural wording rather than overly polished, promotional, or excessively formal academic language.

\- Preferred wording may include natural phrases such as:

\`\`\`

\\- \\\`"I have been following your work on..."\\\`

\\- \\\`"I have been particularly interested in your work on..."\\\`

\\- \\\`"I was particularly interested in your paper..."\\\`

\\- \\\`"Given my background in..."\\\`

\\- \\\`"My research in..., combined with my experience in..., has led me to explore..."\\\`

\\- \\\`"I am interested in how..."\\\`

\`\`\`

These are examples of natural wording only. Do not use the same phrase, opening, transition, or sentence structure repeatedly across different professors.

\- Avoid generic phrases such as:

\`\`\`

\\- \\\`"I am writing to express my strong interest..."\\\`

\\- \\\`"I am reaching out to inquire..."\\\`

\\- \\\`"Your research interests perfectly align with my academic goals..."\\\`

\\- \\\`"I believe my skills and experience make me an ideal candidate..."\\\`

\\- \\\`"I would be honored to contribute to your esteemed research group..."\\\`

\\- \\\`"It would be an incredible honor..."\\\`

\\- \\\`"I look forward to the possibility of working with you..."\\\`

\`\`\`

\- Avoid excessive compliments such as \`"your outstanding research"\`, \`"your groundbreaking work"\`, \`"your pioneering research"\`, \`"your remarkable contributions"\`, or \`"your prestigious research group"\` unless the wording is genuinely justified by verified information.

\- Prefer **\*\*research specificity over flattery\*\***.

\- *\*\****\*\*Natural Research Connection Rule\*\***\*\*: Before writing the email, identify the **single strongest genuine research connection** between the professor's work and Forhad's actual background.

\- The research paragraph should naturally explain **\*\*what specific aspect of the professor's research interests Forhad and why\*\*** rather than simply stating that their research aligns.

\- The connection should normally follow this reasoning:

\`\`\`

\\- Professor's specific research.

\\- Relevant research problem, methodology, or direction.

\\- Forhad's related research or engineering background.

\\- Potential research interest or direction.

\`\`\`

\- Do not force a connection merely to make the email appear highly personalized.

\- The research connection must be based on the **underlying research problem or methodology**, not merely matching keywords.

\- Do not connect the professor to Forhad simply because both use terms such as AI, machine learning, software engineering, predictive modeling, DevOps, or software systems.

\- For example, do not assume:

\`\`\`

\\- Professor works on software architecture → Forhad has backend experience → therefore strong research fit.

\\- Professor works on AI → Forhad works on AI → therefore perfect research alignment.

\`\`\`

The connection must explain **why the professor's specific research is relevant to Forhad's actual research background or interests**.

\- Do not force a connection between every professor's research and predictive modeling, XAI, or machine learning.

\- If the professor's work is primarily related to software engineering, software architecture, DevOps, testing, requirements engineering, software reliability, model-driven engineering, or another area, identify the **strongest genuine intersection** with Forhad's software engineering and AI/ML background.

\- If the strongest connection is software engineering rather than AI/ML, emphasize software engineering.

\- If it is ML or predictive modeling, emphasize ML or predictive modeling.

\- If it is software reliability, testing, architecture, DevOps, or another specific research area, use that connection when supported by both the professor's research and Forhad's profile.

\- Select only the **1–2 most relevant aspects** of Forhad's background for each professor. Do not attempt to mention every research interest in every email.

\- Do not automatically include Explainable AI, Machine Learning, predictive modeling, AI-driven Software Engineering, and software systems in every email. Use only the areas that create the strongest research connection.

\- Do not add technical terms such as \`"intelligent automation"\`, \`"AI-driven"\`, \`"data-driven"\`, \`"predictive models"\`, or \`"explainable AI"\` simply because they appear in Forhad's profile. Use them only when they naturally relate to the professor's actual research.

\- Avoid the phrase \`"I am deeply interested in applying..."\` as a default construction. Prefer restrained and natural expressions such as \`"I am interested in exploring..."\`, \`"I have become interested in..."\`, or \`"This has led me to explore..."\` when appropriate.

\- Avoid making the professor's paper title the entire basis of personalization. The paper should provide evidence of the professor's research direction, while the email should demonstrate an understanding of the underlying research problem.

\- The final research paragraph should still make sense if the paper title is removed. The research fit should come from the explanation, not from paper-name dropping.

\- *\*\****\*\*Anti-Template Rule\*\***\*\*: The email must NOT follow a fixed sentence pattern across professors.

\- Do not repeatedly generate structures such as:

\`\`\`

\\- \\\`"I am particularly drawn to your research..."\\\`

\\- \\\`"My [background] aligns well with..."\\\`

\\- \\\`"I am eager to apply my background to..."\\\`

\\- \\\`"Given my experience... I am interested in..."\\\`

\\- \\\`"Your research aligns closely with my interests..."\\\`

\`\`\`

These phrases are not forbidden individually, but they must NOT become recurring default constructions.

\- Do not write the email by taking a fixed template and replacing the professor's name, research area, and paper titles.

\- The structure, sentence openings, transitions, and rhythm should vary naturally depending on the professor's research.

\- *\*\****\*\*Avoid Forced AI Positioning\*\***\*\*: Do not automatically frame every potential PhD direction as \`"AI-driven"\`, \`"intelligent"\`, \`"ML-based"\`, or \`"data-driven"\`.

\- If the professor's research does not naturally involve AI/ML, do not force AI/ML terminology into the email merely because Forhad has an AI/ML background.

\- The applicant should sound interested in exploring a research direction, not as though he has already defined a complete PhD project.

\- *\*\****\*\*Use Restrained Confidence\*\***\*\*: The applicant should sound capable and genuinely interested without exaggerating the similarity between his background and the professor's research.

\- Avoid phrases such as:

\`\`\`

\\- \\\`"aligns perfectly with my interests"\`

\\- \\\`"perfectly matches my research"\`

\\- \\\`"exactly aligns with my expertise"\`

\\- \\\`"is an ideal continuation of my research"\`

\\- \\\`"I am the perfect fit for your group"\`

\`\`\`

\- Prefer measured language such as:

\`\`\`

\\- \\\`"connects with my background in..."\\\`

\\- \\\`"closely relates to my research interests..."\\\`

\\- \\\`"has led me to explore..."\\\`

\\- \\\`"I am interested in how..."\\\`

\\- \\\`"I see a potential connection between..."\\\`

\`\`\`

\- The email should feel like an observation made by a researcher who has examined the professor's work, not a sales pitch.

\- *\*\****\*\*Do Not Force a Future Research Proposal\*\***\*\*: The email does not need to propose a complete research project, detailed methodology, dataset, or expected contribution.

\- A credible research interest or potential direction is sufficient.

\- Do not claim that Forhad intends to solve a specific problem under the professor's supervision unless that direction is genuinely supported by his profile.

\- *\*\****\*\*Professor-Specificity Test\*\***\*\*: Before finalizing the email, mentally remove the professor's name and paper titles.

Ask:

\`\`\`

Could this same email be sent to another professor without changing the research paragraph?

\`\`\`

\- If the answer is **yes**, the email is not personalized enough and must be revised.

\- If the answer is **no**, because the research connection depends on the professor's specific work, the personalization is acceptable.

\- *\*\****\*\*Naturalness Test\*\***\*\*: The final email should sound like a capable PhD applicant personally contacting a professor after examining their research.

\- It should not sound like:

\`\`\`

\\- an AI-generated template,

\\- a Statement of Purpose,

\\- a cover letter,

\\- a research proposal,

\\- a marketing message, or

\\- an exaggerated expression of admiration.

\`\`\`

\- Prefer:

\`\`\`

specific + concise + technically credible + restrained

\`\`\`

over:

\`\`\`

generic + elaborate + overly flattering + artificially sophisticated

\`\`\`

\- *\*\****\*\*Variation Requirement\*\***\*\*: Across different professors, vary sentence openings, transitions, paragraph rhythm, and the way the research connection is expressed.

\- Do not reuse the same rhetorical structure merely because it produced a good email for a previous professor.

\- The final email should feel **individually written for this professor**, not like a generic PhD template with the professor's name, research area, and paper titles replaced.
$$




5. ****Paper Selection Rules****:

- Prefer recent papers that are directly relevant to the professor's current research direction.

- Prefer papers that create a genuine research connection with Forhad's background.

- Do not automatically select the newest papers. Select the 1–2 papers that provide the strongest and most natural research connection.

- Older papers may be used when they are particularly relevant to the professor's research direction.

- Avoid selecting papers merely because they have high citation counts.

- Avoid unrelated papers even if they are recent.

- Do not force a paper reference simply for personalization.

- If no recent publication provides a meaningful connection, use another verified research detail from the professor's profile when available.

- ****Never invent, alter, combine, or hallucinate publication titles or research claims.****

6. ****Research Fit & Personalization Rules****:

- The email must clearly answer:

```
 \- **Why this professor?** → Include at least one concrete research detail specific to the professor.

 \- **Why Forhad?** → Connect that research direction to Forhad's actual background.

 \- **Why Spring 2027?** → Clearly ask about expected funded PhD opportunities.
```

- Before finalizing, check whether the email could be sent to another professor simply by changing the professor's name and paper titles.

- If the answer is yes, the email is not personalized enough and must be revised.

- Do not exaggerate the research fit. Phrases such as `"aligns perfectly"`, `"perfect match"`, or `"exactly aligns with my expertise"` should generally be avoided.

- Prefer measured language such as:

```
 \- \`"connects with my background in..."\`

 \- \`"closely relates to my research interests..."\`

 \- \`"has led me to explore..."\`

 \- \`"I am interested in how..."\`

 \- \`"I see a potential connection between..."\`
```

- Technical terminology should only be included when it is supported by both the professor's research and Forhad's actual background.

7. ****Pre-Save Verification****:

- Check word count $\le 150$ words.

- If over 150 words, revise automatically until $\le 150$ words.

- Check that the professor's full name is correct.

- Check that the professor's academic title is correct when included.

- Check that the university is correct.

- Check that all cited papers exist in the scraped data or verified sheet data.

- Check that cited papers are recent, strictly prioritizing **2025 and 2026** publications (or latest available 2024-2026), avoiding old papers from years ago.

- Check that no publication title has been invented, altered, or incorrectly combined.

- Check that all research claims are supported by the provided data.

- Check that Spring 2027 is mentioned.

- Check that the email asks about **funded** PhD opportunities rather than assuming that a position is available.

- Check that both Resume and Academic Transcript are mentioned.

- Check that Forhad is introduced as an **"AI/ML Researcher and Software Engineer"**.

- Check that no forbidden terms (e.g. "currently a Lecturer") appear.

- Check that no unsupported research claims appear.

- Check that there is at least one concrete professor-specific research connection.

- Check that the email does not contain excessive praise or generic AI-generated language.

- Check that the email sounds natural and concise.

- If any verification fails, revise the email before proceeding to Step 6.

---

**## Step 6: Google Sheet Direct Update**

1. Locate the exact row number of the selected professor (`sheet_row = record_index + 2`).

2. Map the relevant columns dynamically:

- `"Pipeline Status"` (Column M) $\rightarrow$ Set to ****`Needs Review`**** **(Immediately locks the group for future runs)**

- `"LLM Research Summary"` (Column P) $\rightarrow$ Insert generated summary

- `"LLM Fit Score (1-10)"` (Column Q) $\rightarrow$ Insert fit score (e.g. `8` or `9`)

- `"Email Subject"` (Column R) $\rightarrow$ Insert generated subject

- `"Email Draft"` (Column S) $\rightarrow$ Insert generated draft

3. Perform the update via `worksheet.batch_update()` for speed and atomicity.

---

**## Step 7: Output & Verification**

Print a clean summary report to the user containing:

1. ****Selected Professor & Group****: Name, University, Sheet Row, and Priority.

2. ****Scraped Publications****: List of the papers identified.

3. ****Generated Summary****: The exact text placed into the sheet.

4. ****Email Subject & Draft****: The email content and its exact word count.

5. ****Sheet Status****: Confirmation that row was saved with status `Needs Review`.
