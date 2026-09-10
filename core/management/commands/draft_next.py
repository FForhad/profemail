import os
import re
import sys
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
import gspread
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

# Fallback candidate profile as defined in the specification
DEFAULT_PROFILE = (
    "I am an AI/ML Researcher and Software Engineer with research expertise in "
    "Machine Learning, Explainable AI (XAI), and AI-driven Software Engineering. "
    "I am applying for Spring 2027 PhD positions."
)


class Command(BaseCommand):
    help = (
        "PhD Outreach Agent: Fetches professors from Google Sheet, selects next eligible "
        "professor using concurrency/lock logic, scrapes their Google Scholar profile, "
        "drafts a tailored email & research summary using LLM, and updates the Google Sheet directly."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--sheet",
            type=str,
            default=None,
            help="Google Sheet ID, URL, or Title (overrides settings/env).",
        )
        parser.add_argument(
            "--worksheet",
            type=str,
            default=None,
            help="Worksheet name or index (default: first worksheet).",
        )
        parser.add_argument(
            "--credentials",
            type=str,
            default=None,
            help="Path to credentials.json (default: credentials.json in BASE_DIR).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=1,
            help="Number of professors to process and draft for (default: 1).",
        )
        parser.add_argument(
            "--start-row",
            "--min-row",
            type=int,
            dest="start_row",
            default=None,
            help="Starting / minimum sheet row number to process from (e.g. 178).",
        )
        parser.add_argument(
            "--max-row",
            type=int,
            default=None,
            help="Maximum sheet row number to process up to (e.g. 125).",
        )
        parser.add_argument(
            "--country",
            type=str,
            default=None,
            help="Filter candidate professors by country (e.g. USA, Germany, Japan).",
        )
        parser.add_argument(
            "--intake",
            type=str,
            default=None,
            help="Target intake semester (e.g. 'Spring/Fall 2027', 'Spring 2027', 'Fall 2026').",
        )
        parser.add_argument(
            "--ignore-preceding-locks",
            action="store_true",
            default=False,
            help="Explicitly ignore group locks established by rows prior to --start-row.",
        )
        parser.add_argument(
            "--enforce-all-locks",
            action="store_true",
            default=False,
            help="Enforce group locks across all rows in the sheet even when --start-row is specified.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("=== Starting PhD Outreach Agent: draft_next ==="))

        # -------------------------------------------------------------
        # 1. Authentication & Fetch
        # -------------------------------------------------------------
        creds_path = (
            options.get("credentials")
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            or getattr(settings, "GOOGLE_SHEETS_CREDENTIALS_PATH", "credentials.json")
        )
        if not os.path.isabs(creds_path):
            creds_path = os.path.join(getattr(settings, "BASE_DIR", os.getcwd()), creds_path)

        if not os.path.exists(creds_path):
            self.stderr.write(
                self.style.ERROR(f"Error: Google credentials file not found at: {creds_path}")
            )
            return

        sheet_identifier = (
            options.get("sheet")
            or os.getenv("GOOGLE_SHEET_KEY")
            or os.getenv("GOOGLE_SHEET_URL")
            or getattr(settings, "GOOGLE_SHEET_KEY", "")
            or getattr(settings, "GOOGLE_SHEET_URL", "")
        )
        if not sheet_identifier:
            self.stderr.write(
                self.style.ERROR("Error: No Google Sheet ID or URL provided in options or environment.")
            )
            return

        try:
            gc = gspread.service_account(filename=creds_path)
            if sheet_identifier.startswith("http://") or sheet_identifier.startswith("https://"):
                spreadsheet = gc.open_by_url(sheet_identifier)
            else:
                try:
                    spreadsheet = gc.open_by_key(sheet_identifier)
                except Exception:
                    spreadsheet = gc.open(sheet_identifier)

            worksheet_opt = options.get("worksheet") or os.getenv("GOOGLE_SHEET_NAME")
            worksheet = None
            if worksheet_opt:
                try:
                    worksheet = spreadsheet.worksheet(worksheet_opt)
                except Exception:
                    try:
                        worksheet = spreadsheet.get_worksheet(int(worksheet_opt))
                    except Exception:
                        pass
            if worksheet is None:
                worksheet = spreadsheet.get_worksheet(0)

            # Fetch all records as list of dictionaries
            records = worksheet.get_all_records()
            self.stdout.write(self.style.SUCCESS(f"Successfully fetched {len(records)} row(s) from sheet."))
        except Exception as exc:
            err_str = str(exc)
            if hasattr(exc, "__cause__") and exc.__cause__:
                err_str = str(exc.__cause__)
            if "has not been used in project" in err_str or "it is disabled" in err_str:
                self.stderr.write(
                    self.style.ERROR(
                        "\n[Google Cloud API Not Enabled]\n"
                        "Google Sheets API is currently disabled in your Google Cloud project.\n"
                        "Please click this link and press the blue 'ENABLE' button:\n"
                        "  https://console.developers.google.com/apis/api/sheets.googleapis.com/overview?project=53690441086\n"
                    )
                )
            else:
                self.stderr.write(self.style.ERROR(f"Failed to authenticate or fetch Google Sheet: {exc}"))
            return

        if not records:
            self.stdout.write("No eligible professors found")
            return

        # -------------------------------------------------------------
        # 2. Concurrency & Lock Logic
        # -------------------------------------------------------------
        # Helper to find column keys case-insensitively
        sample_keys = list(records[0].keys())

        def find_key(candidates: List[str]) -> Optional[str]:
            for cand in candidates:
                cand_lower = cand.lower().strip()
                for k in sample_keys:
                    if k.lower().strip() == cand_lower:
                        return k
            return None

        group_col = find_key(["Contact Group (Lock)", "Contact Group", "Group", "Lock"])
        status_col = find_key(["Pipeline Status", "Status", "Pipeline"])
        priority_col = find_key(["Priority"])
        scholar_col = find_key(["Google Scholar URL", "Scholar URL", "Google Scholar", "Profile URL", "Professor Profile URL"])
        name_col = find_key(["Professor Name", "Name"])
        summary_col = find_key(["LLM Research Summary", "Research Summary", "Summary"])
        draft_col = find_key(["Email Draft", "LLM Draft Email", "Draft Email"])
        country_col = find_key(["Country", "Nation", "Location"])

        if not group_col or not status_col:
            self.stderr.write(
                self.style.ERROR(
                    f"Required columns missing. Found columns: {sample_keys}. "
                    f"Need 'Contact Group (Lock)' and 'Pipeline Status'."
                )
            )
            return

        locked_statuses = {"researching", "needs review", "approved", "applied"}

        start_row = options.get("start_row")
        max_row = options.get("max_row")
        country_filter = options.get("country")
        if country_filter:
            country_filter = country_filter.strip().lower()

        # If start_row is specified, by default ignore locks established by rows preceding start_row,
        # unless --enforce-all-locks is explicitly set.
        ignore_preceding_locks = options.get("ignore_preceding_locks") or (
            start_row is not None and not options.get("enforce_all_locks")
        )

        # Identify locked groups
        locked_groups = set()
        for idx, rec in enumerate(records):
            sheet_row = idx + 2
            if ignore_preceding_locks and start_row and sheet_row < start_row:
                continue
            raw_group = str(rec.get(group_col, "")).strip()
            raw_status = str(rec.get(status_col, "")).strip().lower().replace("_", " ")
            if raw_group and raw_status in locked_statuses:
                locked_groups.add(raw_group)

        self.stdout.write(f"Active/Locked Contact Groups ({len(locked_groups)}): {locked_groups if locked_groups else 'None'}")

        # Filter eligible professors:
        # Pipeline Status must be "Pending" AND Contact Group must NOT be locked.
        eligible_candidates = []
        for idx, rec in enumerate(records):
            # In gspread, row 1 is headers, row 2 is records[0] -> sheet_row = idx + 2
            sheet_row = idx + 2
            if start_row and sheet_row < start_row:
                continue
            if max_row and sheet_row > max_row:
                continue

            if country_filter and country_col:
                rec_country = str(rec.get(country_col, "")).strip().lower()
                if country_filter in ["usa", "us", "united states"]:
                    if rec_country not in ["usa", "us", "united states"]:
                        continue
                elif country_filter not in rec_country:
                    continue

            raw_status = str(rec.get(status_col, "")).strip().lower().replace("_", " ")
            raw_group = str(rec.get(group_col, "")).strip()

            if raw_status == "pending" and raw_group not in locked_groups:
                # Parse priority: 1 is highest
                raw_prio = rec.get(priority_col, 999) if priority_col else 999
                try:
                    prio_val = int(raw_prio)
                except (ValueError, TypeError):
                    # If string like 'High', map to 1, 'Medium' to 2, 'Low' to 3
                    p_str = str(raw_prio).strip().lower()
                    if p_str == "high":
                        prio_val = 1
                    elif p_str == "medium":
                        prio_val = 2
                    elif p_str == "low":
                        prio_val = 3
                    else:
                        prio_val = 999

                eligible_candidates.append({
                    "row_index": sheet_row,
                    "record": rec,
                    "priority": prio_val,
                    "name": rec.get(name_col, f"Row {sheet_row}") if name_col else f"Row {sheet_row}",
                    "group": raw_group,
                })

        # Sort candidates strictly by Priority (1 highest), then by sheet row index (lowest first)
        eligible_candidates.sort(key=lambda c: (c["priority"], c["row_index"]))

        if not eligible_candidates:
            self.stdout.write("No eligible professors found")
            return

        limit = options.get("limit", 1) or 1
        if max_row and options.get("limit") == 1:
            limit = len(eligible_candidates)
        processed_count = 0

        # Read sheet headers once
        headers = [h.strip() for h in worksheet.row_values(1)]

        def get_col_index(preferred_name: str, fallback_candidates: List[str]) -> Optional[int]:
            for candidate in [preferred_name] + fallback_candidates:
                c_lower = candidate.lower().strip()
                for idx, h in enumerate(headers):
                    if h.lower().strip() == c_lower:
                        return idx + 1
            return None

        col_summary_idx = get_col_index("LLM Research Summary", ["Research Summary", "Summary"])
        col_draft_idx = get_col_index("Email Draft", ["LLM Draft Email", "Draft Email", "Draft"])
        col_status_idx = get_col_index("Pipeline Status", ["Status", "Pipeline"])
        col_subject_idx = get_col_index("Email Subject", ["Subject"])
        col_fit_idx = get_col_index("LLM Fit Score (1-10)", ["Fit Score", "Fit Score (1-10)"])

        for candidate in eligible_candidates:
            if processed_count >= limit:
                break

            # Dynamic lock check: ensure group was not locked by previous iteration in this batch
            if candidate["group"] in locked_groups:
                continue

            selected_record = candidate["record"]
            selected_row = candidate["row_index"]
            selected_name = candidate["name"]
            selected_group = candidate["group"]

            self.stdout.write("\n" + "=" * 60)
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{processed_count + 1}/{limit}] Selected Professor: '{selected_name}' "
                    f"(Group: '{selected_group}', Priority: {candidate['priority']}, Sheet Row: {selected_row})"
                )
            )

            # -------------------------------------------------------------
            # 3. Scraping
            # -------------------------------------------------------------
            scholar_url = str(selected_record.get(scholar_col, "")).strip() if scholar_col else ""
            if not scholar_url:
                for k in ["Profile URL", "Professor Profile URL", "Lab / University Website URL", "Lab Website URL"]:
                    val = str(selected_record.get(k, "")).strip()
                    if "scholar.google" in val.lower():
                        scholar_url = val
                        break
                    elif not scholar_url and val.startswith("http"):
                        scholar_url = val

            self.stdout.write(f"Target URL for scraping: {scholar_url or 'None provided'}")
            scraped_data = self._scrape_scholar(scholar_url, professor_name=selected_name)
            self.stdout.write(f"Scraped summary length: {len(scraped_data)} chars.")

            rec_country = str(selected_record.get(country_col or "Country", "")).strip().lower()
            is_japan = rec_country == "japan" or bool(country_filter and "japan" in country_filter.lower())
            opt_intake = options.get("intake")
            target_intake = opt_intake or ("Spring/Fall 2027" if is_japan else "Spring 2027")
            email_subject = f"Prospective PhD Applicant – {target_intake} – Forhad Uddin Ahmed"

            # -------------------------------------------------------------
            # 4. LLM Integration (Drafting the Email)
            # -------------------------------------------------------------
            self.stdout.write("Generating research summary, fit score, and email draft via LLM...")
            summary, email_draft, fit_score = self._generate_llm_content(
                professor_name=selected_name,
                selected_record=selected_record,
                scraped_data=scraped_data,
                target_intake=target_intake,
            )

            word_count = len(email_draft.split())
            if word_count > 150:
                self.stdout.write(self.style.WARNING(f"Draft has {word_count} words (>150). Auto-shortening..."))
                email_draft = self._shorten_email_draft(email_draft, max_words=145)
                word_count = len(email_draft.split())

            self.stdout.write(self.style.SUCCESS("--- Generated LLM Research Summary ---"))
            self.stdout.write(summary)
            self.stdout.write(self.style.SUCCESS(f"--- Generated Fit Score: {fit_score}/10 ---"))
            self.stdout.write(self.style.SUCCESS(f"--- Generated Email Draft (Word Count: {word_count}) ---"))
            self.stdout.write(email_draft)

            # -------------------------------------------------------------
            # 5. Sheet Update
            # -------------------------------------------------------------
            self.stdout.write(f"Updating Google Sheet row {selected_row}...")
            try:
                updates = []
                if col_summary_idx:
                    updates.append({
                        "range": gspread.utils.rowcol_to_a1(selected_row, col_summary_idx),
                        "values": [[summary]],
                    })
                if col_draft_idx:
                    updates.append({
                        "range": gspread.utils.rowcol_to_a1(selected_row, col_draft_idx),
                        "values": [[email_draft]],
                    })
                if col_status_idx:
                    updates.append({
                        "range": gspread.utils.rowcol_to_a1(selected_row, col_status_idx),
                        "values": [["Needs Review"]],
                    })
                if col_subject_idx:
                    updates.append({
                        "range": gspread.utils.rowcol_to_a1(selected_row, col_subject_idx),
                        "values": [[email_subject]],
                    })
                if col_fit_idx:
                    updates.append({
                        "range": gspread.utils.rowcol_to_a1(selected_row, col_fit_idx),
                        "values": [[fit_score]],
                    })

                if updates:
                    worksheet.batch_update(updates)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Successfully updated row {selected_row} for '{selected_name}': "
                            f"Status -> 'Needs Review', Summary & Draft updated in Google Sheet."
                        )
                    )
                    # Immediately lock this group for any remaining candidates in this batch
                    if selected_group:
                        locked_groups.add(selected_group)
                    processed_count += 1
                    time.sleep(1.5)
                else:
                    self.stderr.write(self.style.ERROR("No valid columns found to update in Google Sheet."))
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"Failed to update Google Sheet row: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(f"\nFinished processing {processed_count} professor(s) successfully.")
        )

    def _fetch_semantic_scholar(self, name: str) -> str:
        """Fallback to Semantic Scholar graph API to fetch verified recent publications."""
        if not name:
            return ""
        clean_name = re.sub(
            r"^(prof\.|dr\.|assoc\.\s*prof\.|asst\.\s*prof\.|assistant\s*professor|associate\s*professor|professor)\s*",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip()
        queries = [clean_name]
        no_initial = re.sub(r"^[A-Z]\.\s*", "", clean_name).strip()
        if no_initial != clean_name:
            queries.append(no_initial)

        for q in queries:
            try:
                r = requests.get(
                    f"https://api.semanticscholar.org/graph/v1/author/search?query={q}&fields=name,papers.title,papers.year",
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10,
                )
                if r.status_code == 200:
                    data = r.json()
                    authors = data.get("data", [])
                    if authors:
                        author = authors[0]
                        papers = sorted(
                            author.get("papers", []),
                            key=lambda x: x.get("year") or 0,
                            reverse=True,
                        )
                        if papers:
                            lines = [
                                f"Scholar Name (Semantic Scholar): {author.get('name')}",
                                "Recent Publications (sorted newest first):",
                            ]
                            for p in papers[:12]:
                                title = p.get("title")
                                year = p.get("year")
                                if title:
                                    line = f'- Title: "{title}"'
                                    if year:
                                        line += f" | Year: {year}"
                                    lines.append(line)
                            return "\n".join(lines)
            except Exception as e:
                logger.warning(f"Semantic Scholar fallback error for '{q}': {e}")
        return ""

    def _scrape_scholar(self, url: str, professor_name: str = "") -> str:
        """
        Scrapes the Google Scholar profile page with realistic headers
        to extract recent publication titles and publication years.
        Falls back to Semantic Scholar API if Google Scholar fails or is blocked.
        """
        extracted = []
        if url and url.strip():
            url = url.strip()
            if not url.startswith("http"):
                url = f"https://{url}"

            # Ensure Google Scholar sorts by publication date (newest first: 2026, 2025...)
            if "scholar.google" in url and "sortby=pubdate" not in url:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}sortby=pubdate"

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            }

            try:
                response = requests.get(url, headers=headers, timeout=12)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "html.parser")
                    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
                        tag.decompose()

                    name_elem = soup.select_one("#gsc_prf_in")
                    if name_elem:
                        extracted.append(f"Scholar Name: {name_elem.get_text(strip=True)}")

                    interests = [a.get_text(strip=True) for a in soup.select("#gsc_prf_int a")]
                    if interests:
                        extracted.append(f"Research Interests: {', '.join(interests)}")

                    pub_rows = soup.select("tr.gsc_a_tr")
                    if pub_rows:
                        extracted.append("Recent Publications (sorted newest first):")
                        for r in pub_rows[:12]:
                            title_elem = r.select_one("a.gsc_a_at")
                            authors_elem = r.select_one(".gs_gray")
                            year_elem = r.select_one(".gsc_a_y")

                            title = title_elem.get_text(strip=True) if title_elem else ""
                            authors = authors_elem.get_text(strip=True) if authors_elem else ""
                            year = year_elem.get_text(strip=True) if year_elem else ""

                            if title:
                                line = f'- Title: "{title}"'
                                if year:
                                    line += f" | Year: {year}"
                                if authors:
                                    line += f" | Authors: {authors}"
                                extracted.append(line)
                    else:
                        text = " ".join(soup.stripped_strings)
                        text = re.sub(r"\s+", " ", text).strip()
                        if "Sign in to continue" not in text and len(text) > 100:
                            extracted.append(text[:2500])
            except Exception as e:
                logger.warning(f"Error scraping {url}: {e}")

        # If no publications were extracted from Google Scholar, fall back to Semantic Scholar API
        has_pubs = any("Recent Publications" in x for x in extracted)
        if not has_pubs and professor_name:
            s2_res = self._fetch_semantic_scholar(professor_name)
            if s2_res:
                extracted.append(s2_res)

        return "\n".join(extracted) if extracted else "No publication data available."

    def _shorten_email_draft(self, draft: str, max_words: int = 145) -> str:
        """Auto-shortens email draft via LLM to guarantee word count <= 150 words."""
        api_key = os.getenv("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", "")
        model_name = os.getenv("GEMINI_MODEL") or getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash")
        if api_key:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                prompt = (
                    f"Shorten this PhD outreach email draft so that its total word count is strictly under {max_words} words.\n"
                    f"CRITICAL REQUIREMENTS:\n"
                    f"- Retain formal salutation using the professor's full name.\n"
                    f"- Retain applicant positioning as 'AI/ML Researcher and Software Engineer'.\n"
                    f"- Retain cited recent publications and genuine technical bridge.\n"
                    f"- Retain polite Spring 2027 PhD availability inquiry.\n"
                    f"- Retain explicit mention that both resume and academic transcript are attached.\n"
                    f"- Retain formal sign-off: Sincerely,\\nForhad Uddin Ahmed.\n"
                    f"Do NOT output markdown formatting tags, explanation, or commentary. Output ONLY the shortened email text.\n\n"
                    f"{draft}"
                )
                shorten_models = [
                    model_name or "gemini-3.6-flash",
                    "gemini-3.6-flash",
                    "gemini-3.5-flash-lite",
                    "gemini-3.1-flash-lite",
                ]
                for sm in shorten_models:
                    try:
                        resp = client.models.generate_content(
                            model=sm,
                            contents=prompt,
                        )
                        if resp and resp.text:
                            shortened = resp.text.strip()
                            shortened = re.sub(r"^```(?:markdown|text)?\n?", "", shortened).strip()
                            shortened = re.sub(r"\n?```$", "", shortened).strip()
                            if len(shortened.split()) <= 150:
                                return shortened
                    except Exception as err:
                        if "429" in str(err) or "RESOURCE_EXHAUSTED" in str(err) or "503" in str(err):
                            continue
                        break
            except Exception as e:
                logger.warning(f"Error auto-shortening email draft: {e}")
        return draft

    def _generate_llm_content(
        self, professor_name: str, selected_record: Dict[str, Any], scraped_data: str, target_intake: str = "Spring 2027"
    ) -> Tuple[str, str, int]:
        """
        Uses google-generativeai / google.genai / OpenAI to generate:
          a) LLM Research Summary
          b) Email Draft (max 150 words)
          c) LLM Fit Score (1-10)
        """
        api_key = (
            os.getenv("GEMINI_API_KEY")
            or getattr(settings, "GEMINI_API_KEY", "")
            or os.getenv("OPENAI_API_KEY")
        )
        model_name = os.getenv("GEMINI_MODEL") or getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash")

        profile_instructions_path = os.path.join(getattr(settings, "BASE_DIR", os.getcwd()), "PROFILE_INSTRUCTIONS.md")
        profile_instructions_text = ""
        if os.path.exists(profile_instructions_path):
            with open(profile_instructions_path, "r", encoding="utf-8") as f:
                profile_instructions_text = f.read()

        if "spring/fall" in target_intake.lower() or "spring or fall" in target_intake.lower():
            phd_inquiry_rule = (
                f'Respectfully ask about {target_intake} PhD availability near the end ("Do you expect to have PhD opportunities for {target_intake}?" or "for the Spring or Fall 2027 intake?"). Explicitly ask about {target_intake}, never only Spring or only Fall. Never assume open positions exist.'
            )
        else:
            phd_inquiry_rule = (
                f'Respectfully ask about {target_intake} PhD availability near the end ("Do you expect to have PhD opportunities for {target_intake}?"). Never assume open positions exist.'
            )

        # Clean salutation formatting helper
        clean_name = professor_name.strip()
        if clean_name.startswith("Prof. ") or clean_name.startswith("Professor "):
            clean_salutation = f"Dear {clean_name},"
        elif clean_name.startswith("Assoc. Prof. "):
            clean_salutation = f"Dear Associate Professor {clean_name[12:].strip()},"
        elif clean_name.startswith("Associate Professor "):
            clean_salutation = f"Dear Associate Professor {clean_name[20:].strip()},"
        elif clean_name.startswith("Dr. "):
            clean_salutation = f"Dear {clean_name},"
        else:
            clean_salutation = f"Dear Professor {clean_name},"

        prompt = f"""
You are assisting Forhad Uddin Ahmed in drafting a highly personalized, polite, and persuasive PhD outreach email to a prospective advisor to maximize the opportunity of securing a funded PhD position or supervision.

### STRICT PROFILE CONTEXT & WRITING GUIDELINES:
{profile_instructions_text or DEFAULT_PROFILE}

### TARGET PROFESSOR:
- Name: {professor_name}
- Suggested Salutation: {clean_salutation}
- University: {selected_record.get('University', '')}
- Department: {selected_record.get('Department/Lab', selected_record.get('Department', ''))}
- Known Research Area: {selected_record.get('Research Area', '')}
- Sheet Publications: {selected_record.get('Recent Publications', '')}

### SCRAPED SCHOLAR DATA:
{scraped_data}

### INSTRUCTIONS:
1. **Analyze Publications & Research Focus**:
   - Analyze the professor's most recent papers, STRICTLY prioritizing publications from 2025 and 2026 (or 2024 if 2025/2026 are not available).
   - Do NOT cite old foundational papers from years/decades ago when recent 2025/2026 research is present.
   - Generate a concise "LLM Research Summary" (2-4 sentences analyzing the lab's current direction, methodologies, and focus based ONLY on verified recent publications).

2. **Calibrated Fit Score (1-10)**:
   Assess overlap with Forhad's background in ML, XAI, predictive modeling, AI-driven Software Engineering, and scalable software systems:
   - 9–10: Exceptional direct research overlap.
   - 7–8: Strong and meaningful research overlap.
   - 5–6: Moderate or adjacent overlap.
   - 3–4: Weak overlap.
   - 1–2: Very limited overlap.
   *(Do NOT inflate score merely because both work in general AI, ML, or computer science).*

3. **Generate Email Draft (STRICTLY MAXIMUM 150 WORDS)**:
   - **Salutation**: Use formal academic etiquette: `{clean_salutation}` (never duplicate titles like "Dear Professor Prof.").
   - **Polite Opening**: Begin courteously with a polite greeting (e.g., "I hope this email finds you well." or "I hope you are having a productive semester."), immediately followed by positioning Forhad as an "AI/ML Researcher and Software Engineer" with research experience in the relevant area. (DO NOT state that he is currently a Lecturer. Do NOT state "I am applying for funded PhD positions" in the opening).
   - **Thoughtful Research Bridge**:
     - Cite 1–2 verified RECENT papers (strictly prioritizing 2025 and 2026 papers from the scraped data).
     - Use respectful, intellectually mature academic phrasing (e.g., "I read with great interest your recent paper...", "I have been following your lab's work on..."). Do NOT use exaggerated praise like "I am deeply impressed" or "groundbreaking".
     - Explain *why* that specific research problem or methodology is compelling, rather than just dropping titles.
     - Naturally connect Forhad's actual research experience (Explainable AI, Machine Learning, predictive modeling, or software systems) to the professor's specific recent research focus.
     - Maintain intellectual humility, technical credibility, and sincerity.
   - **Respectful, Opportunity-Maximizing Inquiry**:
     - Respectfully inquire whether the professor expects to have capacity or funded PhD opportunities for {target_intake} in their research group.
     - Express polite deference to their time (e.g., "If your schedule permits, I would be very grateful for the opportunity to discuss potential research alignment or seek your advice.").
     - Explicitly state that both his **Resume and Academic Transcript** are attached for review (e.g. "I have attached my resume and academic transcript for your review."). Do NOT say only "CV attached".
   - **Polite Sign-off**:
     Thank you very much for your time and consideration.

     Sincerely,
     Forhad Uddin Ahmed
   - **Strict Word Count Constraint**: The total email MUST be between 115 and 140 words (STRICT CEILING: 145 words, never exceed 150 words).

### OUTPUT FORMAT:
You MUST respond in this exact format:

[RESEARCH_SUMMARY]
<Your concise research summary here>
[/RESEARCH_SUMMARY]

[FIT_SCORE]
<An integer between 1 and 10>
[/FIT_SCORE]

[EMAIL_DRAFT]
<Your outreach email draft under 150 words here>
[/EMAIL_DRAFT]
"""

        # 1. Try google.genai (official new SDK)
        if api_key:
            candidate_models = [
                model_name or "gemini-3.6-flash",
                "gemini-3.6-flash",
                "gemini-3.5-flash-lite",
                "gemini-3.1-flash-lite",
                "gemini-3.8-flash",
            ]
            for m_name in candidate_models:
                try:
                    from google import genai
                    client = genai.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model=m_name,
                        contents=prompt,
                    )
                    if response and response.text:
                        return self._parse_llm_response(response.text)
                except Exception as e:
                    logger.warning(f"google.genai call failed for model {m_name}: {e}")
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "503" in str(e):
                        continue
                    break

            # 2. Try legacy google.generativeai if available
            try:
                import google.generativeai as genai_legacy
                genai_legacy.configure(api_key=api_key)
                m = genai_legacy.GenerativeModel("gemini-1.5-flash")
                response = m.generate_content(prompt)
                if response and response.text:
                    return self._parse_llm_response(response.text)
            except Exception as e:
                logger.warning(f"google-generativeai legacy failed: {e}")

            # Try OpenAI if OPENAI_API_KEY is available
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                try:
                    import openai
                    client = openai.OpenAI(api_key=openai_key)
                    completion = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                    )
                    text = completion.choices[0].message.content
                    if text:
                        return self._parse_llm_response(text)
                except Exception as e:
                    logger.warning(f"OpenAI call failed: {e}")

        # Deterministic fallback if API keys not provided or network failure
        self.stdout.write(self.style.WARNING("Using deterministic template generation (no LLM key or call failed)."))
        return self._generate_deterministic_content(professor_name, selected_record, scraped_data, target_intake=target_intake)

    def _parse_llm_response(self, text: str) -> Tuple[str, str, int]:
        """Extracts summary, email draft, and fit score from LLM tags."""
        summary = ""
        email_draft = ""
        fit_score = 8

        summary_match = re.search(r"\[RESEARCH_SUMMARY\](.*?)\[/RESEARCH_SUMMARY\]", text, re.DOTALL | re.IGNORECASE)
        if summary_match:
            summary = summary_match.group(1).strip()

        fit_match = re.search(r"\[FIT_SCORE\](.*?)\[/FIT_SCORE\]", text, re.DOTALL | re.IGNORECASE)
        if fit_match:
            try:
                score_str = re.findall(r"\b\d+\b", fit_match.group(1))
                if score_str:
                    fit_score = max(1, min(10, int(score_str[0])))
            except Exception:
                fit_score = 8

        draft_match = re.search(r"\[EMAIL_DRAFT\](.*?)\[/EMAIL_DRAFT\]", text, re.DOTALL | re.IGNORECASE)
        if draft_match:
            email_draft = draft_match.group(1).strip()

        if not summary or not email_draft:
            # Fallback parsing
            parts = text.split("\n\n")
            if len(parts) >= 2:
                summary = parts[0].strip()
                email_draft = "\n\n".join(parts[1:]).strip()
            else:
                summary = "Research focus extracted from publications and profile."
                email_draft = text.strip()

        # Clean email_draft: remove accidental Subject line or markdown fences
        if email_draft:
            email_draft = re.sub(r"^Subject:.*?\n+", "", email_draft, flags=re.IGNORECASE).strip()
            email_draft = re.sub(r"^```(?:markdown|text)?\n?", "", email_draft).strip()
            email_draft = re.sub(r"\n?```$", "", email_draft).strip()

        return summary, email_draft, fit_score

    def _generate_deterministic_content(
        self, professor_name: str, selected_record: Dict[str, Any], scraped_data: str, target_intake: str = "Spring 2027"
    ) -> Tuple[str, str, int]:
        """High quality deterministic fallback conforming to the prompt specification."""
        full_name = professor_name.strip() if professor_name else "Professor"
        if full_name.lower().startswith("prof") or full_name.lower().startswith("dr"):
            salutation = f"Dear {full_name},"
        else:
            salutation = f"Dear Professor {full_name},"
        univ = selected_record.get("University", "your university")

        # Prioritize finding a 2026 or 2025 paper from scraped data
        recent_matches_2026 = re.findall(r'Title:\s*"([^"]+)"\s*\|\s*Year:\s*2026', scraped_data)
        recent_matches_2025 = re.findall(r'Title:\s*"([^"]+)"\s*\|\s*Year:\s*2025', scraped_data)
        recent_matches_2024 = re.findall(r'Title:\s*"([^"]+)"\s*\|\s*Year:\s*2024', scraped_data)

        if recent_matches_2026:
            featured_paper = recent_matches_2026[0]
        elif recent_matches_2025:
            featured_paper = recent_matches_2025[0]
        elif recent_matches_2024:
            featured_paper = recent_matches_2024[0]
        else:
            paper_matches = re.findall(r'Title:\s*"([^"]+)"', scraped_data)
            if not paper_matches:
                paper_matches = re.findall(r'-\s+([A-Z][^\n]+?\(\d{4}\))', scraped_data)
            featured_paper = paper_matches[0] if paper_matches else "your recent publications in machine learning"

        combined_text = f"{selected_record.get('Research Area', '')} {selected_record.get('Department/Lab', '')} {featured_paper} {scraped_data}".lower()

        # Domain classification & deep reasoning
        if any(k in combined_text for k in ["nlp", "language", "linguistic", "dialogue", "retrieval", "text", "translation", "prompt", "llm"]):
            summary = (
                f"Professor {professor_name}'s research at {univ} investigates core challenges in natural language processing, "
                f"language model representations, and semantic understanding, with recent advancements demonstrated in '{featured_paper}'."
            )
            fit_score = 8
            research_bridge = (
                f"My research background centers on Machine Learning, Natural Language Processing, and Explainable AI (XAI). "
                f"Given your lab's work on robust language representations and model evaluation, I believe my background in "
                f"transparent architectures and scalable ML pipelines aligns well with your current research direction."
            )
        elif any(k in combined_text for k in ["software", "testing", "defect", "verification", "refactoring", "code", "debugging", "developer", "program analysis"]):
            summary = (
                f"Professor {professor_name}'s laboratory at {univ} advances software engineering methodologies, program analysis, "
                f"and developer tooling, focusing on reliability and empirical rigor as demonstrated in '{featured_paper}'."
            )
            fit_score = 9
            research_bridge = (
                f"My research background spans AI-driven Software Engineering, Explainable AI, and software systems. "
                f"Having worked on both machine learning architectures and scalable software engineering systems, I am particularly "
                f"interested in how intelligent models and explainability can improve software quality, testing, and system reliability."
            )
        elif any(k in combined_text for k in ["explainab", "interpretab", "trustworthy", "fairness", "transparent", "causal", "robust"]):
            summary = (
                f"Professor {professor_name}'s group at {univ} develops foundational principles for interpretable, trustworthy, "
                f"and robust machine learning systems, as reflected in '{featured_paper}'."
            )
            fit_score = 9
            research_bridge = (
                f"My research background directly centers on Explainable AI (XAI) and trustworthy machine learning, where I have "
                f"published peer-reviewed work on feature attribution and model transparency. Given your focus on reliable and interpretable "
                f"learning systems, I believe my background allows me to contribute meaningfully to your lab's projects."
            )
        elif any(k in combined_text for k in ["security", "privacy", "vulnerability", "malware", "adversarial", "cryptograph"]):
            summary = (
                f"Professor {professor_name}'s research at {univ} addresses critical challenges in system security, software vulnerabilities, "
                f"and robust defense mechanisms, as highlighted in '{featured_paper}'."
            )
            fit_score = 8
            research_bridge = (
                f"My research background centers on Machine Learning, Explainable AI, and robust software systems. "
                f"Given your focus on dependable computing and security analysis, I believe my experience in rigorous model "
                f"evaluation and resilient system design aligns well with your research goals."
            )
        else:
            summary = (
                f"Professor {professor_name}'s laboratory at {univ} investigates core problems in machine learning, data intelligence, "
                f"and computational systems, emphasizing robust methodologies as demonstrated in '{featured_paper}'."
            )
            fit_score = 8
            research_bridge = (
                f"My research background centers on Machine Learning, Explainable AI (XAI), and predictive modeling for complex systems. "
                f"Given your focus on principled machine learning and data-driven methods, I believe my experience in trustworthy "
                f"models and scalable pipelines would allow me to contribute effectively to your lab."
            )

        email_draft = (
            f"{salutation}\n\n"
            f"I hope this email finds you well. I am Forhad Uddin Ahmed, an AI/ML Researcher and Software Engineer "
            f"with peer-reviewed research experience in machine learning and explainable AI. I have been following "
            f"your lab's work at {univ}, particularly your recent paper '{featured_paper}'.\n\n"
            f"{research_bridge}\n\n"
            f"Do you expect to have PhD opportunities for {target_intake}? I would welcome the opportunity to discuss "
            f"potential alignment if your schedule permits. I have attached my resume and academic transcript for your review.\n\n"
            f"Thank you for your time and consideration.\n\n"
            f"Sincerely,\n"
            f"Forhad Uddin Ahmed"
        )

        return summary, email_draft, fit_score
