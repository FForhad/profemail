import json
import logging
import os
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote_plus

import gspread
import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

DEFAULT_FIELDS = [
    "machine-learning",
    "artificial-intelligence",
    "software-engineering",
    "data-science",
    "computer-science",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

RELEVANT_KEYWORDS = (
    "machine learning",
    "deep learning",
    "artificial intelligence",
    "explainable ai",
    "xai",
    "time series",
    "natural language processing",
    "nlp",
    "large language model",
    "llm",
    "agentic",
    "ai agent",
    "software engineering",
    "predictive modeling",
    "computer vision",
    "reinforcement learning",
    "federated learning",
    "data science",
    "neural network",
    "foundation model",
)

TLD_COUNTRY_MAP = {
    ".edu": "USA",
    ".ca": "Canada",
    ".de": "Germany",
    ".uk": "UK",
    ".nl": "Netherlands",
    ".se": "Sweden",
    ".fi": "Finland",
    ".au": "Australia",
    ".jp": "Japan",
    ".kr": "South Korea",
    ".sg": "Singapore",
    ".my": "Malaysia",
    ".ch": "Switzerland",
    ".fr": "France",
    ".dk": "Denmark",
    ".no": "Norway",
}

MONTH_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b"
)


def deobfuscate_emails(text: str) -> List[str]:
    """Extracts and normalizes standard and [at]/[dot]-obfuscated emails from text."""
    if not text:
        return []
    normalized = text
    normalized = re.sub(r"\s*\[at\]\s*|\s*\(at\)\s*", "@", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*\[dot\]\s*|\s*\(dot\)\s*", ".", normalized, flags=re.IGNORECASE)
    found = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", normalized)
    # Filter out generic aggregator/placeholder addresses
    ignored_domains = ("phdfinder.com", "example.com", "sentry.io", "linkedin.com")
    cleaned: List[str] = []
    seen: Set[str] = set()
    for email in found:
        low = email.lower().rstrip(".")
        if any(low.endswith(dom) or f"@{dom}" in low for dom in ignored_domains):
            continue
        if low not in seen:
            seen.add(low)
            cleaned.append(low)
    return cleaned


def infer_country_from_email_or_text(email: str, text: str) -> str:
    """Infers country from email TLD or text cues when not explicitly provided."""
    low_email = (email or "").lower()
    for tld, country in TLD_COUNTRY_MAP.items():
        if low_email.endswith(tld):
            return country
    low_text = (text or "").lower()
    for country in (
        "USA",
        "Canada",
        "Germany",
        "UK",
        "Netherlands",
        "Sweden",
        "Finland",
        "Australia",
        "Japan",
        "South Korea",
        "Singapore",
        "Malaysia",
        "Switzerland",
        "France",
    ):
        if re.search(rf"\b{re.escape(country.lower())}\b", low_text):
            return country
    if "united states" in low_text:
        return "USA"
    if "united kingdom" in low_text:
        return "UK"
    return "Unknown"


def make_contact_group(university: str, department: str, country: str) -> str:
    """Creates a concise departmental Contact Group (Lock) key."""
    uni_words = [w for w in re.findall(r"[A-Za-z0-9]+", university or "") if w.lower() not in {"university", "of", "the", "at", "and", "in", "for"}]
    dept_words = [w for w in re.findall(r"[A-Za-z0-9]+", department or "") if w.lower() not in {"department", "of", "the", "school", "faculty", "and", "for"}]
    uni_slug = "".join(w[:4].upper() for w in uni_words[:2]) or (country[:3].upper() if country else "UNIV")
    dept_slug = "".join(w[:4].upper() for w in dept_words[:2]) or "LAB"
    return f"{uni_slug}-{dept_slug}"


def parse_linkedin_post_html(html: str, url: str, today: Optional[date] = None) -> Dict[str, Any]:
    """
    Parses a public LinkedIn post HTML page (`linkedin.com/posts/...`) using
    embedded JSON-LD (`SocialMediaPosting`) and OpenGraph metadata.
    """
    today = today or datetime.now(timezone.utc).date()
    soup = BeautifulSoup(html, "html.parser")

    author_name = ""
    post_text = ""
    published_date: Optional[date] = None
    post_age_days: Optional[int] = None

    for sc in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not sc.string:
            continue
        try:
            payload = json.loads(sc.string)
        except Exception:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "SocialMediaPosting":
                date_str = item.get("datePublished", "")
                if date_str:
                    try:
                        published_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
                        post_age_days = max(0, (today - published_date).days)
                    except Exception:
                        pass
                author = item.get("author")
                if isinstance(author, dict):
                    author_name = (author.get("name") or "").strip()
                post_text = (item.get("articleBody") or item.get("headline") or "").strip()
                break

    # Prefer full rendered post body / og:description when longer than JSON-LD headline
    body_elem = soup.select_one("p.attributed-text-segment-list__content, .feed-shared-update-v2__description")
    if body_elem:
        rendered = body_elem.get_text(" ", strip=True)
        if len(rendered) > len(post_text):
            post_text = rendered

    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_desc and og_desc.get("content"):
        desc = og_desc["content"].strip()
        if len(desc) > len(post_text):
            post_text = desc

    if not author_name:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            author_name = og_title["content"].split("|")[0].strip()

    # Fallback age extraction from LinkedIn relative timestamp (e.g. "3d", "1w")
    if post_age_days is None:
        text_sample = soup.get_text(" ", strip=True)[:1500]
        m_age = re.search(r"\b(\d+)\s*(h|hr|d|w)\b", text_sample)
        if m_age:
            val, unit = int(m_age.group(1)), m_age.group(2)
            if unit in ("h", "hr"):
                post_age_days = 0
            elif unit == "d":
                post_age_days = val
            elif unit == "w":
                post_age_days = val * 7

    return {
        "source_url": url,
        "author_name": author_name,
        "post_text": re.sub(r"\s+", " ", post_text).strip(),
        "published_date": published_date.isoformat() if published_date else "",
        "post_age_days": post_age_days,
        "emails": deobfuscate_emails(post_text),
    }


def extract_phdfinder_key_facts(html: str, url: str, today: Optional[date] = None) -> Dict[str, Any]:
    """Parses a PhDFinder opportunity page for structured metadata and LinkedIn link."""
    today = today or datetime.now(timezone.utc).date()
    soup = BeautifulSoup(html, "html.parser")
    title_elem = soup.find("h1")
    title = title_elem.get_text(" ", strip=True) if title_elem else ""
    full_text = soup.get_text(" ", strip=True)

    # Trim header/footer noise
    start_idx = full_text.find("By PhDFinder Team")
    end_idx = full_text.find("Follow the PhDFinder")
    body = full_text[start_idx:end_idx] if start_idx != -1 else full_text

    published_date: Optional[date] = None
    post_age_days: Optional[int] = None
    m_date = MONTH_DATE_RE.search(body[:300])
    if m_date:
        try:
            published_date = datetime.strptime(m_date.group(0), "%B %d, %Y").date()
            post_age_days = max(0, (today - published_date).days)
        except Exception:
            pass

    def grab_field(label: str) -> str:
        pat = rf"(?:–|-)?\s*{re.escape(label)}\s*:\s*(.+?)(?=\s+(?:–|-)?\s*(?:Position type|Institution|University|Department or group|Location|Country|Supervisor|Funding or salary|Duration|Start date|Apply by|Deadline|Fields|Research Project|Candidate Profile|Application Process|Original advertisement|Original post)\s*:|$)"
        m = re.search(pat, body, re.IGNORECASE)
        return m.group(1).strip(" –-:") if m else ""

    university = grab_field("University") or grab_field("Institution")
    country = grab_field("Country") or grab_field("Location")
    department = grab_field("Department or group")
    supervisor = grab_field("Supervisor")
    funding = grab_field("Funding or salary")
    start_date = grab_field("Start date")
    deadline = grab_field("Deadline") or grab_field("Apply by")

    if not supervisor:
        m_sup = re.search(
            r"(?:advised by|supervised by|in|under)\s+((?:Prof\.?|Professor|Dr\.?|Asst\.?\s*Prof\.?|Assoc\.?\s*Prof\.?)\s+[A-Z][A-Za-z.\-']+(?:\s+[A-Z][A-Za-z.\-']+){1,3})",
            body,
        )
        if m_sup:
            supervisor = m_sup.group(1).strip(" .,;:")

    # Clean country if Location includes city/state
    if "," in country and "USA" in country:
        country = "USA"

    # Extract LinkedIn link if present
    linkedin_url = ""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "linkedin.com/posts/" in href or "lnkd.in/" in href:
            linkedin_url = href
            break
    if not linkedin_url:
        m_ln = re.search(r"https?://(?:www\.)?(?:lnkd\.in/[^\s]+|linkedin\.com/posts/[^\s]+)", body)
        if m_ln:
            linkedin_url = m_ln.group(0).rstrip(".,;)")

    # Extract Research Project + Candidate Profile + Application Process summary
    proj_idx = body.find("Research Project")
    end_proj = body.find("Original advertisement")
    if end_proj == -1:
        end_proj = body.find("Original post")
    verbatim_section = body[proj_idx:end_proj].strip() if proj_idx != -1 else body[:1500]

    return {
        "listing_url": url,
        "title": title,
        "university": university,
        "country": country,
        "department": department,
        "supervisor": supervisor,
        "funding": funding,
        "start_date": start_date,
        "deadline": deadline,
        "published_date": published_date.isoformat() if published_date else "",
        "post_age_days": post_age_days,
        "linkedin_url": linkedin_url,
        "emails": deobfuscate_emails(body),
        "body_text": re.sub(r"\s+", " ", verbatim_section).strip(),
        "full_body": body,
    }


class Command(BaseCommand):
    help = (
        "Discover fresh (<7 days) professor recruitment announcements from LinkedIn posts "
        "and academic feeds, verify 2025/2026 publications & locks, and stage into SearchProf."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=5, help="Max new candidates to stage (default: 5).")
        parser.add_argument("--max-age", type=int, default=6, help="Max post age in days, strictly < 7 (default: 6).")
        parser.add_argument(
            "--fields",
            type=str,
            default=",".join(DEFAULT_FIELDS),
            help="Comma-separated PhDFinder field slugs to scan.",
        )
        parser.add_argument("--pages", type=int, default=2, help="Pages per field slug to scan (default: 2).")
        parser.add_argument("--country", type=str, default=None, help="Filter candidates by country (e.g. USA, Canada).")
        parser.add_argument(
            "--linkedin-only",
            action="store_true",
            default=False,
            help="Only stage candidates that include a direct LinkedIn post link (or are passed via --urls).",
        )
        parser.add_argument(
            "--urls",
            nargs="+",
            default=[],
            help="Direct LinkedIn post URLs (linkedin.com/posts/... or lnkd.in/...) to parse and stage.",
        )
        parser.add_argument(
            "--urls-file",
            type=str,
            default=None,
            help="File with one LinkedIn post URL per line to parse and stage.",
        )
        parser.add_argument(
            "--include-phd-non-usa",
            action="store_true",
            default=False,
            help="Allow non-USA PhD-only openings (default filters non-USA to Master's/MSc/MASc/RA-compatible calls).",
        )
        parser.add_argument("--worksheet", type=str, default="SearchProf", help="Target worksheet (default: SearchProf).")
        parser.add_argument("--sheet", type=str, default=None, help="Google Sheet URL or ID (overrides .env).")
        parser.add_argument("--credentials", type=str, default=None, help="Path to credentials.json.")
        parser.add_argument("--dry-run", action="store_true", default=False, help="Preview without writing to sheet.")
        parser.add_argument(
            "--draft",
            action="store_true",
            default=False,
            help="Automatically run draft_next on staged candidates after appending.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("=== Starting LinkedIn & Academic Opportunity Discovery: discover_profs ==="))
        today = datetime.now(timezone.utc).date()
        limit: int = max(1, options["limit"])
        max_age: int = min(6, max(0, options["max_age"]))
        country_filter = options["country"].strip().lower() if options.get("country") else None
        linkedin_only: bool = options["linkedin_only"]
        include_phd_non_usa: bool = options["include_phd_non_usa"]
        dry_run: bool = options["dry_run"]

        # 1. Connect to Google Sheets and load existing professors & locks
        creds_path = (
            options.get("credentials")
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            or getattr(settings, "GOOGLE_SHEETS_CREDENTIALS_PATH", "credentials.json")
        )
        if not os.path.isabs(creds_path):
            creds_path = os.path.join(getattr(settings, "BASE_DIR", os.getcwd()), creds_path)
        if not os.path.exists(creds_path):
            self.stderr.write(self.style.ERROR(f"Credentials file not found: {creds_path}"))
            return

        sheet_identifier = (
            options.get("sheet")
            or os.getenv("GOOGLE_SHEET_KEY")
            or os.getenv("GOOGLE_SHEET_URL")
            or getattr(settings, "GOOGLE_SHEET_KEY", "")
            or getattr(settings, "GOOGLE_SHEET_URL", "")
        )
        if not sheet_identifier:
            self.stderr.write(self.style.ERROR("No Google Sheet URL or ID configured."))
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

            target_ws_name = options["worksheet"]
            search_ws = spreadsheet.worksheet(target_ws_name)
            existing_names, existing_emails, locked_groups = self._load_existing_state(spreadsheet, search_ws)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Failed to connect to Google Sheet: {exc}"))
            return

        self.stdout.write(
            f"Loaded {len(existing_names)} existing names, {len(existing_emails)} emails, "
            f"and {len(locked_groups)} active Contact Group locks."
        )

        # 2. Gather direct LinkedIn URLs (if provided via --urls or --urls-file)
        direct_urls: List[str] = list(options.get("urls") or [])
        if options.get("urls_file"):
            ufile = options["urls_file"]
            if os.path.exists(ufile):
                with open(ufile, "r", encoding="utf-8") as fh:
                    direct_urls.extend(line.strip() for line in fh if line.strip() and not line.strip().startswith("#"))
            else:
                self.stderr.write(self.style.WARNING(f"URLs file not found: {ufile}"))

        staged_rows: List[List[str]] = []

        # Process direct LinkedIn URLs first
        for u in direct_urls:
            if len(staged_rows) >= limit:
                break
            cand = self._process_linkedin_url(u, today, max_age)
            if not cand:
                continue
            row = self._validate_and_format_candidate(
                cand, existing_names, existing_emails, locked_groups, country_filter, include_phd_non_usa
            )
            if row:
                staged_rows.append(row)
                self._register_local_seen(row, existing_names, existing_emails, locked_groups)

        # 3. Discover fresh opportunities from PhDFinder (and follow LinkedIn links when present)
        if len(staged_rows) < limit and not direct_urls:
            fields = [f.strip() for f in options["fields"].split(",") if f.strip()]
            pages = max(1, options["pages"])
            listing_urls = self._discover_phdfinder_urls(fields, pages, today, max_age)
            self.stdout.write(f"Found {len(listing_urls)} recent candidate listing(s) within <= {max_age} days.")

            for lurl in listing_urls:
                if len(staged_rows) >= limit:
                    break
                cand = self._process_phdfinder_listing(lurl, today, max_age, linkedin_only)
                if not cand:
                    continue
                row = self._validate_and_format_candidate(
                    cand, existing_names, existing_emails, locked_groups, country_filter, include_phd_non_usa
                )
                if row:
                    staged_rows.append(row)
                    self._register_local_seen(row, existing_names, existing_emails, locked_groups)

        if not staged_rows:
            self.stdout.write(self.style.WARNING("No new eligible candidates matched all filters."))
            return

        self.stdout.write(self.style.SUCCESS(f"\nPrepared {len(staged_rows)} new candidate(s):"))
        for idx, r in enumerate(staged_rows, 1):
            self.stdout.write(
                f"  {idx}. {r[0]} | {r[1]} ({r[2]}) | Lock: {r[4]} | Email: {r[5]} | Age: {r[7]}d"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY-RUN] Sheet was not modified."))
            return

        search_ws.append_rows(staged_rows, value_input_option="USER_ENTERED")
        self.stdout.write(self.style.SUCCESS(f"Successfully appended {len(staged_rows)} row(s) to '{target_ws_name}'."))

        if options.get("draft"):
            self.stdout.write(self.style.NOTICE(f"\nRunning draft_next on '{target_ws_name}'..."))
            call_command("draft_next", worksheet=target_ws_name, limit=len(staged_rows))

    def _load_existing_state(
        self, spreadsheet: gspread.Spreadsheet, search_ws: gspread.Worksheet
    ) -> Tuple[Set[str], Set[str], Set[str]]:
        """Collects existing names, emails, and active locks across SearchProf and Professors List."""
        names: Set[str] = set()
        emails: Set[str] = set()
        locks: Set[str] = set()
        active_statuses = {"researching", "needs review", "approved", "applied"}

        s_rows = search_ws.get_all_values()
        for r in s_rows[1:]:
            if r and r[0].strip():
                names.add(r[0].strip().lower())
            if len(r) > 5 and r[5].strip():
                emails.add(r[5].strip().lower())
            if len(r) > 9 and r[4].strip() and r[9].strip().lower() in active_statuses:
                locks.add(r[4].strip().lower())

        try:
            main_ws = spreadsheet.worksheet("Professors List")
            m_rows = main_ws.get_all_values()
            for r in m_rows[1:]:
                if r and r[0].strip():
                    names.add(r[0].strip().lower())
                if len(r) > 17 and r[17].strip():
                    emails.add(r[17].strip().lower())
                if len(r) > 11 and r[4].strip() and r[11].strip().lower() in active_statuses:
                    locks.add(r[4].strip().lower())
        except Exception:
            pass

        return names, emails, locks

    def _discover_phdfinder_urls(
        self, fields: List[str], pages: int, today: date, max_age: int
    ) -> List[str]:
        """Collects non-postdoc PhDFinder URLs published within `max_age` days."""
        seen: Set[str] = set()
        urls: List[str] = []

        for slug in fields:
            for page in range(1, pages + 1):
                url = (
                    f"https://phdfinder.com/search/{slug}/"
                    if page == 1
                    else f"https://phdfinder.com/search/{slug}/page/{page}/"
                )
                try:
                    resp = requests.get(url, headers=HEADERS, timeout=12)
                    if resp.status_code != 200:
                        break
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "phdfinder.com/202" not in href or href in seen:
                            continue
                        if "postdoc" in href.lower():
                            continue
                        m_date = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", href)
                        if not m_date:
                            continue
                        try:
                            pub = date(int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3)))
                        except ValueError:
                            continue
                        age = (today - pub).days
                        if 0 <= age <= max_age:
                            seen.add(href)
                            urls.append(href)
                except Exception as exc:
                    logger.warning(f"Error scanning {url}: {exc}")
                    break
        return urls

    def _process_linkedin_url(self, url: str, today: date, max_age: int) -> Optional[Dict[str, Any]]:
        """Fetches a public LinkedIn post URL directly and enriches it."""
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code != 200:
                return None
            parsed = parse_linkedin_post_html(resp.text, resp.url, today=today)
        except Exception as exc:
            logger.warning(f"Failed fetching LinkedIn URL {url}: {exc}")
            return None

        age = parsed["post_age_days"]
        if age is None or age > max_age:
            return None

        text = parsed["post_text"]
        if not any(kw in text.lower() for kw in RELEVANT_KEYWORDS):
            return None

        emails = parsed["emails"]
        if not emails:
            return None

        email = emails[0]
        prof_name = parsed["author_name"] or "Unknown Professor"
        if not re.match(r"^(Prof\.?|Professor|Dr\.?|Asst\.?|Assoc\.?)\b", prof_name, re.I):
            prof_name = f"Prof. {prof_name}"

        extracted = self._llm_extract_fields(text, prof_name, email)
        university = extracted.get("university") or "Unknown University"
        country = extracted.get("country") or infer_country_from_email_or_text(email, text)
        department = extracted.get("department") or "Computer Science / Engineering"

        return {
            "professor_name": prof_name,
            "university": university,
            "country": country,
            "department": department,
            "email": email,
            "post_age": age,
            "post_text": text[:2000],
            "linkedin_url": parsed["source_url"],
            "funding": extracted.get("funding") or "See LinkedIn post",
            "intake": extracted.get("intake") or "Spring/Fall 2027",
            "subject_hint": extracted.get("subject_hint") or "",
        }

    def _process_phdfinder_listing(
        self, url: str, today: date, max_age: int, linkedin_only: bool
    ) -> Optional[Dict[str, Any]]:
        """Fetches a PhDFinder listing and follows any LinkedIn post link inside it."""
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                return None
            info = extract_phdfinder_key_facts(resp.text, url, today=today)
        except Exception as exc:
            logger.warning(f"Error fetching {url}: {exc}")
            return None

        if linkedin_only and not info["linkedin_url"]:
            return None

        age = info["post_age_days"]
        if age is None or age > max_age:
            return None

        # Check relevance to Forhad's research background
        combined_text = f"{info['title']} {info['body_text']}".lower()
        if not any(kw in combined_text for kw in RELEVANT_KEYWORDS):
            return None

        # Follow LinkedIn post if available to grab verbatim text and exact LinkedIn timestamp
        post_text = info["body_text"]
        linkedin_url = info["linkedin_url"]
        emails = list(info["emails"])

        if linkedin_url:
            try:
                li_resp = requests.get(linkedin_url, headers=HEADERS, timeout=12, allow_redirects=True)
                if li_resp.status_code == 200 and "linkedin.com/posts/" in li_resp.url:
                    li_parsed = parse_linkedin_post_html(li_resp.text, li_resp.url, today=today)
                    if li_parsed["post_text"]:
                        post_text = li_parsed["post_text"]
                    if li_parsed["post_age_days"] is not None:
                        age = li_parsed["post_age_days"]
                        if age > max_age:
                            return None
                    for em in li_parsed["emails"]:
                        if em not in emails:
                            emails.insert(0, em)
                    if not info["supervisor"] and li_parsed["author_name"]:
                        info["supervisor"] = f"Prof. {li_parsed['author_name']}"
                    linkedin_url = li_parsed["source_url"]
            except Exception:
                pass

        if not info["supervisor"] or not emails:
            return None

        return {
            "professor_name": info["supervisor"],
            "university": info["university"],
            "country": info["country"] or infer_country_from_email_or_text(emails[0], post_text),
            "department": info["department"] or "Computer Science / Engineering",
            "email": emails[0],
            "post_age": age,
            "post_text": post_text[:2000],
            "linkedin_url": linkedin_url or url,
            "funding": info["funding"] or "Funded",
            "intake": info["start_date"] or "Spring/Fall 2027",
            "subject_hint": "",
            "deadline": info["deadline"],
        }

    def _llm_extract_fields(self, text: str, author: str, email: str) -> Dict[str, str]:
        """Optional Gemini extraction for raw LinkedIn posts; returns empty dict on quota/failure."""
        api_key = os.getenv("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            return {}
        prompt = (
            "Extract JSON with keys: university, country, department, funding, intake, subject_hint "
            f"from this academic recruitment post by {author} ({email}). Return ONLY raw JSON.\n\n{text[:2500]}"
        )
        for model_name in ("gemini-3.5-flash-lite", "gemini-flash-lite-latest"):
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                resp = client.models.generate_content(model=model_name, contents=prompt)
                if resp and resp.text:
                    raw = re.sub(r"^```(?:json)?|```$", "", resp.text.strip()).strip()
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        return {k: str(v or "") for k, v in data.items()}
            except Exception:
                continue
        return {}

    def _verify_recent_publications(self, prof_name: str, university: str) -> Tuple[str, List[str]]:
        """Queries OpenAlex for a verified profile URL and 2025/2026 publications."""
        clean = re.sub(
            r"^(Prof\.?|Professor|Dr\.?|Asst\.?\s*Prof\.?|Assoc\.?\s*Prof\.?)\s+",
            "",
            prof_name,
            flags=re.IGNORECASE,
        ).strip()
        try:
            r = requests.get(
                f"https://api.openalex.org/authors?search={quote_plus(clean)}&per-page=5",
                timeout=8,
            )
            if r.status_code != 200:
                return "", []
            authors = r.json().get("results", [])
            chosen = None
            uni_tokens = [w.lower() for w in re.findall(r"[A-Za-z]+", university or "") if len(w) > 3]
            for a in authors:
                insts = " ".join(
                    (i.get("display_name") or "").lower() for i in a.get("last_known_institutions", [])
                )
                if uni_tokens and any(tok in insts for tok in uni_tokens):
                    chosen = a
                    break
            if not chosen and authors:
                chosen = authors[0]
            if not chosen:
                return "", []
            aid = chosen["id"].split("/")[-1]
            rw = requests.get(
                f"https://api.openalex.org/works?filter=author.id:{aid},publication_year:2025-2026&sort=publication_date:desc&per-page=3",
                timeout=8,
            )
            titles: List[str] = []
            if rw.status_code == 200:
                for w in rw.json().get("results", []):
                    if w.get("title"):
                        titles.append(f"{w.get('publication_year')}: {w['title']}")
            return chosen["id"], titles
        except Exception:
            return "", []

    def _validate_and_format_candidate(
        self,
        cand: Dict[str, Any],
        existing_names: Set[str],
        existing_emails: Set[str],
        locked_groups: Set[str],
        country_filter: Optional[str],
        include_phd_non_usa: bool,
    ) -> Optional[List[str]]:
        """Applies country, degree-alignment, publication recency, duplicate, and lock checks."""
        prof_name = cand["professor_name"].strip()
        email = cand["email"].strip().lower()
        country = cand["country"].strip()
        university = cand["university"].strip()
        department = cand["department"].strip()

        if country_filter and country.lower() != country_filter:
            return None

        # Degree alignment: outside USA, exclude PhD-only calls unless Master's/MSc/MASc/RA position or override flag
        if country.lower() not in {"usa", "united states", "us"} and not include_phd_non_usa:
            low_text = cand["post_text"].lower()
            masters_position_patterns = (
                r"\bmsc\s+(?:and|&|or)?\s*(?:phd\s+)?position",
                r"\bmasc\s+(?:and|&|or)?\s*(?:phd\s+)?position",
                r"\bphd\s*(?:&|and|or)\s*m\.?sc\b",
                r"\bphd\s*(?:&|and|or)\s*masc\b",
                r"\bmaster(?:'s)?\s+(?:by\s+research|thesis|student|position|opening|program)",
                r"\bthesis-based\s+(?:msc|masc|master)",
                r"\bmphil\b",
                r"\bhiwi\b",
                r"\bstudent\s+assistant\b",
            )
            has_masters_opening = any(re.search(pat, low_text) for pat in masters_position_patterns)
            if "phd" in low_text and not has_masters_opening:
                return None

        if prof_name.lower() in existing_names or email in existing_emails:
            return None

        lock = make_contact_group(university, department, country)
        if lock.lower() in locked_groups:
            return None

        # Verify 2025/2026 research activity via OpenAlex
        openalex_url, recent_papers = self._verify_recent_publications(prof_name, university)
        if not recent_papers:
            return None

        profile_url = cand.get("linkedin_url") or openalex_url
        notes_parts = [
            f"Funding: {cand.get('funding', 'Funded')}",
            f"Intake: {cand.get('intake', 'Spring/Fall 2027')}",
        ]
        if cand.get("deadline"):
            notes_parts.append(f"Deadline: {cand['deadline']}")
        if cand.get("subject_hint"):
            notes_parts.append(f"Subject format: {cand['subject_hint']}")
        notes_parts.append(f"Verified recent papers: {'; '.join(recent_papers[:2])}")
        if cand.get("linkedin_url"):
            notes_parts.append(f"Source: {cand['linkedin_url']}")

        return [
            prof_name,
            university,
            country,
            department,
            lock,
            email,
            profile_url,
            str(cand["post_age"]),
            "",
            "Pending",
            " | ".join(notes_parts),
            cand["post_text"],
        ]

    def _register_local_seen(
        self, row: List[str], names: Set[str], emails: Set[str], locks: Set[str]
    ) -> None:
        names.add(row[0].strip().lower())
        emails.add(row[5].strip().lower())
        locks.add(row[4].strip().lower())
