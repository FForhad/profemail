# ProfEmail — Command Reference by Purpose

A quick-reference guide of all verified commands for **ProfEmail**, organized by task.

> **Prerequisite:** Activate the virtual environment before running commands (or prefix with `.venv/bin/python`):
> ```bash
> source .venv/bin/activate
> ```

---

## 1. Environment, Database & Development

### Virtual Environment & Dependencies
```bash
# Activate virtual environment (Linux/macOS)
source .venv/bin/activate

# Install or update dependencies
pip install -r requirements.txt
```

### Django Setup, Admin UI & Tests
```bash
# Apply database migrations
python manage.py migrate

# Create an admin user for the Django Admin dashboard
python manage.py createsuperuser

# Start the local Django server (visit http://127.0.0.1:8000/admin/)
python manage.py runserver

# Run Django unit tests
python manage.py test

# View all options for a management command
python manage.py sheet_status --help
python manage.py discover_profs --help
python manage.py draft_next --help
python manage.py create_gmail_drafts --help
python manage.py send_approved --help
```

---

## 2. Discovering New Candidates (`discover_profs`)

Finds fresh (`< 7` days old) recruitment calls from LinkedIn post URLs and academic feeds, follows linked LinkedIn announcements for verbatim post text & exact age, verifies 2025/2026 publications via OpenAlex, checks duplicates/locks against both `SearchProf` and `Professors List`, and stages `Pending` rows into `SearchProf`.

```bash
# Preview new candidates without modifying Google Sheet (recommended first run)
python manage.py discover_profs --dry-run --limit 5

# Discover and stage up to 5 new candidates into SearchProf
python manage.py discover_profs --limit 5

# Search with extra custom keywords across PhDFinder + EURAXESS
python manage.py discover_profs --extra-keywords "graph neural network,healthcare ai,rag" --limit 10

# Override search keywords and scan deeper (3 pages per keyword/field)
python manage.py discover_profs --keywords "explainable ai,llm,time series" --pages 3 --limit 10

# Include non-USA PhD-only calls as well (default targets Master's/RA outside USA)
python manage.py discover_profs --include-phd-non-usa --limit 10

# Require a direct LinkedIn post link on every staged candidate
python manage.py discover_profs --linkedin-only --limit 5

# Filter by country or post age (strictly < 7 days)
python manage.py discover_profs --country USA --max-age 5 --limit 5

# Stage directly from one or more LinkedIn post URLs
python manage.py discover_profs --urls "https://www.linkedin.com/posts/..." "https://lnkd.in/p/..."

# Stage from a text file of LinkedIn post URLs (one URL per line)
python manage.py discover_profs --urls-file linkedin_urls.txt

# Discover, stage into SearchProf, AND immediately run draft_next on them
python manage.py discover_profs --limit 3 --draft
```

---

## 3. Drafting Outreach Emails (`draft_next`)

Fetches eligible `Pending` professors, enforces departmental `Contact Group (Lock)` rules (with cooldown), scrapes Google Scholar / Semantic Scholar for recent publications, generates a tailored draft and fit score via Gemini, and writes back `Needs Review`.

### A. Default Sheet (`Professors List`)
```bash
# Draft for the next 1 eligible professor
python manage.py draft_next

# Draft for up to 5 eligible professors in sequence
python manage.py draft_next --limit 5

# Filter by country
python manage.py draft_next --country USA --limit 3
python manage.py draft_next --country Germany --limit 3

# Target a specific intake semester
python manage.py draft_next --country Canada --intake "Spring/Fall 2027" --limit 2

# Process a specific row range (start-row / min-row to max-row)
python manage.py draft_next --start-row 178 --max-row 250 --limit 3

# Enforce all group locks across the entire sheet even when --start-row is set
python manage.py draft_next --start-row 178 --enforce-all-locks --limit 3

# Explicitly ignore locks from rows before --start-row
python manage.py draft_next --start-row 178 --ignore-preceding-locks --limit 3

# Customize departmental cooldown days after an 'Applied' status (default: 9)
python manage.py draft_next --cooldown-days 14 --limit 3
```

### B. Staging Sheet (`SearchProf`)
```bash
# Draft for the next 1 eligible professor in SearchProf
python manage.py draft_next --worksheet "SearchProf"

# Draft for up to 3 professors in SearchProf
python manage.py draft_next --worksheet "SearchProf" --limit 3

# Draft for USA candidates only in SearchProf
python manage.py draft_next --worksheet "SearchProf" --country USA --limit 5

# Draft from a specific starting row in SearchProf
python manage.py draft_next --worksheet "SearchProf" --start-row 40 --limit 5
```

### C. Custom Sheet or Credentials Override
```bash
# Target a different Google Sheet URL/ID or credentials file
python manage.py draft_next --sheet "YOUR_SHEET_URL_OR_ID" --worksheet "SearchProf" --credentials "credentials.json"
```

---

## 4. Saving Drafts to Gmail App (`create_gmail_drafts`)

Creates identical outreach drafts (same recipient, subject, body, HTML signature from `signature.html`, and attachments from `attachments/`) directly in your **Gmail Drafts** folder via the Gmail API, without sending anything.

> **One-Time OAuth Setup:** Personal `@gmail.com` accounts require an OAuth 2.0 Desktop App JSON saved as `gmail_credentials.json` (distinct from the Google Sheets service account `credentials.json`). First login saves `token.json`.

```bash
# 1. Authenticate once with your Gmail account and cache token.json
python manage.py create_gmail_drafts --auth-only

# 2. Preview drafts without touching Gmail
python manage.py create_gmail_drafts --dry-run --limit 5

# 3. Save 'Needs Review' drafts from Professors List to Gmail Drafts
python manage.py create_gmail_drafts --limit 5

# 4. Save drafts from SearchProf (or filter by status/country/row)
python manage.py create_gmail_drafts --worksheet "SearchProf" --status "Needs Review" --limit 5
python manage.py create_gmail_drafts --worksheet "SearchProf" --status "Approved" --row 40
```

---

## 5. Previewing & Dispatching Emails (`send_approved`)

Reads `Approved` rows from the Google Sheet, attaches files from `attachments/`, appends `signature.txt`, and sends via Gmail SMTP.

> **Safety Note:** Live sending is restricted to rows with status `Approved`. Use `--schedule-plan` or `--dry-run` to preview `Needs Review` or `all` rows without sending.

### A. Preview & Dry-Run (No Emails Sent)
```bash
# Preview the university-local send timetable for Approved rows (Professors List)
python manage.py send_approved --schedule-plan

# Preview timetable for Needs Review rows in SearchProf
python manage.py send_approved --worksheet "SearchProf" --schedule-plan --status "Needs Review"

# Simulate scheduled sending without dispatching emails or updating the sheet
python manage.py send_approved --worksheet "SearchProf" --schedule --dry-run

# Simulate immediate sending for a single row
python manage.py send_approved --row 15 --dry-run
```

### B. Immediate Dispatch (Non-Scheduled)
```bash
# Send all Approved emails immediately with default 15s delay between emails
python manage.py send_approved

# Send up to 3 Approved emails with a 30-second delay between each
python manage.py send_approved --limit 3 --delay 30

# Send a specific row only (e.g., row 40 on SearchProf)
python manage.py send_approved --worksheet "SearchProf" --row 40
```

### C. Timezone-Aware Scheduled Dispatch (`--schedule`)
Delivers emails at the university's local workday start time (default `08:30`) with per-region staggering (default `2` minutes).

```bash
# Run scheduled dispatch daemon on Professors List (8:30 AM local time, 2-min gap)
python manage.py send_approved --schedule

# Run scheduled dispatch daemon on SearchProf
python manage.py send_approved --worksheet "SearchProf" --schedule

# Customize local send time and stagger interval
python manage.py send_approved --worksheet "SearchProf" --schedule --start-time "09:00" --gap-minutes 3

# Use a custom attachments folder or signature file
python manage.py send_approved --schedule --attachments-dir "attachments" --signature-file "signature.txt"
```

---

## 6. Google Sheet Inspection & Lock Auditing

### Built-in Sheet Status Command (`sheet_status`)
Shows row counts, status totals, per-country breakdown, active `Contact Group (Lock)` counts, and how many unlocked professors are ready to draft across `Professors List` and `SearchProf`.

```bash
# Full status across Professors List and SearchProf (default 9-day cooldown)
python manage.py sheet_status

# Filter by country or test a custom cooldown window
python manage.py sheet_status --country USA --cooldown-days 4

# Inspect a single worksheet or output JSON
python manage.py sheet_status --worksheet "Professors List"
python manage.py sheet_status --json
```

Quick one-liners using the project's `.venv` and `.env` to inspect live sheet state without modifying rows.

### Check `SearchProf` Row Counts & Statuses
```bash
.venv/bin/python -c "import os, gspread; from collections import Counter; from dotenv import load_dotenv; load_dotenv(); rows = gspread.service_account('credentials.json').open_by_url(os.getenv('GOOGLE_SHEET_URL')).worksheet('SearchProf').get_all_values(); print('Total rows (incl. header):', len(rows)); print('Statuses:', Counter(r[9] for r in rows[1:] if len(r)>9))"
```

### List All `Pending` Rows in `SearchProf`
```bash
.venv/bin/python -c "import os, gspread; from dotenv import load_dotenv; load_dotenv(); rows = gspread.service_account('credentials.json').open_by_url(os.getenv('GOOGLE_SHEET_URL')).worksheet('SearchProf').get_all_values(); [print(f'Row {i}: {r[0]} | {r[1]} ({r[2]}) | {r[4]} | {r[5]}') for i, r in enumerate(rows[1:], 2) if len(r)>9 and r[9].strip().lower()=='pending']"
```

### Audit Active Contact Group Locks Across Both Sheets
```bash
.venv/bin/python -c "import os, gspread; from dotenv import load_dotenv; load_dotenv(); sh = gspread.service_account('credentials.json').open_by_url(os.getenv('GOOGLE_SHEET_URL')); s1 = sh.worksheet('SearchProf').get_all_values(); s2 = sh.worksheet('Professors List').get_all_values(); active = {'researching','needs review','approved','applied'}; l1 = {r[4].strip() for r in s1[1:] if len(r)>9 and r[9].strip().lower() in active}; l2 = {r[4].strip() for r in s2[1:] if len(r)>11 and r[11].strip().lower() in active}; print('SearchProf locks:', len(l1), '| Professors List locks:', len(l2), '| Total unique:', len(l1|l2))"
```

---

## 7. Git Status & Quick Flag Summary

```bash
# Check modified/untracked workspace files
git status

# View recent project commits
git log -n 10 --oneline
```

### `sheet_status` Flags
`--sheet`, `--worksheet`, `--credentials`, `--country`, `--cooldown-days`, `--json`

### `discover_profs` Flags
`--limit`, `--max-age`, `--fields`, `--keywords`, `--extra-keywords`, `--sources`, `--pages`, `--country`, `--linkedin-only`, `--urls`, `--urls-file`, `--include-phd-non-usa`, `--worksheet`, `--sheet`, `--credentials`, `--dry-run`, `--draft`

### `draft_next` Flags
`--sheet`, `--worksheet`, `--credentials`, `--limit`, `--start-row` (`--min-row`), `--max-row`, `--country`, `--intake`, `--ignore-preceding-locks`, `--enforce-all-locks`, `--cooldown-days`

### `create_gmail_drafts` Flags
`--auth-only`, `--dry-run`, `--sheet`, `--worksheet`, `--status`, `--country`, `--row`, `--limit`, `--attachments-dir`, `--signature-file`, `--gmail-credentials`, `--token-file`, `--allow-duplicates`, `--delay`, `--no-browser`

### `send_approved` Flags
`--dry-run`, `--schedule`, `--schedule-plan`, `--start-time`, `--gap-minutes`, `--limit`, `--row`, `--delay`, `--attachments-dir`, `--signature-file`, `--sheet`, `--status`, `--worksheet`
