import json
import logging
import os
import re
import threading
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import quote_plus, urljoin

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
    "robotics",
    "electrical-engineering",
    "control-systems",
    "biomedical-engineering",
    "mathematics",
    "finance",
    "neuroscience",
    "usa",
    "canada",
    "germany",
    "netherlands",
    "sweden",
    "uk",
]

DEFAULT_SEARCH_KEYWORDS = [
    "machine learning",
    "deep learning",
    "artificial intelligence",
    "explainable ai",
    "large language model",
    "natural language processing",
    "time series",
    "software engineering",
    "computer vision",
    "reinforcement learning",
    "healthcare ai",
    "financial ai",
    "graph neural network",
    "research assistant",
    "master",
]

DEFAULT_SOURCES = ["phdfinder", "euraxess"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

RELEVANT_KEYWORDS = (
    # Core AI / ML
    "machine learning",
    "deep learning",
    "artificial intelligence",
    "explainable ai",
    "xai",
    "interpretable",
    "interpretability",
    "trustworthy ai",
    "responsible ai",
    "ai safety",
    "uncertainty quantification",
    "foundation model",
    "generative ai",
    "diffusion",
    "transformer",
    "neural network",
    "self-supervised",
    "transfer learning",
    "federated learning",
    "reinforcement learning",
    # NLP / LLMs / Agents
    "natural language processing",
    "nlp",
    "large language model",
    "llm",
    "llms",
    "agentic",
    "ai agent",
    "multi-agent",
    "autonomous agent",
    "rag",
    "retrieval-augmented",
    "retrieval augmented",
    "fine-tuning",
    "multimodal",
    "vision-language",
    # Time Series / Graphs / Data
    "time series",
    "forecasting",
    "predictive modeling",
    "spatiotemporal",
    "anomaly detection",
    "data science",
    "data mining",
    "graph neural network",
    "gnn",
    "graph learning",
    "knowledge graph",
    "pattern recognition",
    "computer vision",
    # Software Engineering / Systems
    "software engineering",
    "ai-driven software",
    "software testing",
    "program repair",
    "code generation",
    "software architecture",
    "software resilience",
    "static analysis",
    "bug detection",
    "devops",
    "mlops",
    "distributed systems",
    "cloud computing",
    "scalable systems",
    "intelligent system",
    "cybersecurity",
    "intrusion detection",
    "recommender system",
    "information retrieval",
    # Domain AI (Healthcare / Finance / Robotics)
    "healthcare ai",
    "medical ai",
    "clinical ai",
    "medical imaging",
    "health informatics",
    "bioinformatics",
    "biomedical",
    "stroke",
    "ehr",
    "financial ai",
    "fintech",
    "quantitative finance",
    "fraud detection",
    "risk modeling",
    "cryptocurrency",
    "bitcoin",
    "robotics",
)

GENERIC_EMAIL_PREFIXES = (
    "hr",
    "jobs",
    "job",
    "career",
    "careers",
    "recruit",
    "recruitment",
    "admission",
    "admissions",
    "admin",
    "info",
    "office",
    "contact",
    "support",
    "noreply",
    "no-reply",
    "graduate",
    "grad",
    "apply",
    "applications",
    "application",
    "phd",
    "postdoc",
    "fellowship",
    "scholarship",
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
    ".at": "Austria",
    ".be": "Belgium",
    ".it": "Italy",
    ".es": "Spain",
}

MONTH_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b"
)
DAY_MONTH_DATE_RE = re.compile(
    r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})\b",
    re.IGNORECASE,
)


def deobfuscate_emails(text: str) -> List[str]:
    """Extracts and normalizes standard and [at]/[dot]-obfuscated emails from text."""
    if not text:
        return []
    normalized = text
    normalized = re.sub(r"\s*\[at\]\s*|\s*\(at\)\s*", "@", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*\[dot\]\s*|\s*\(dot\)\s*", ".", normalized, flags=re.IGNORECASE)
    found = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", normalized)
    ignored_domains = ("phdfinder.com", "example.com", "sentry.io", "linkedin.com", "euraxess.ec.europa.eu")
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


def is_generic_email(email: str) -> bool:
    """Return True if the email local-part looks like a generic HR/admin inbox."""
    local = (email or "").split("@", 1)[0].lower()
    tokens = [t for t in re.split(r"[._-]+", local) if t]
    return any(tok in GENERIC_EMAIL_PREFIXES for tok in tokens) or local in GENERIC_EMAIL_PREFIXES


def prioritize_emails(emails: Sequence[str]) -> List[str]:
    """Order extracted emails so personal faculty/PI emails precede generic HR addresses."""
    personal = [e for e in emails if not is_generic_email(e)]
    generic = [e for e in emails if is_generic_email(e)]
    return personal + generic


def infer_name_from_email(email: str) -> str:
    """Infer a professor display name from a personal institutional email like 'mohamed.soliman@...'."""
    if not email or is_generic_email(email):
        return ""
    local = email.split("@", 1)[0]
    parts = [p for p in re.split(r"[._-]+", local) if p and not p.isdigit()]
    # Require at least two alphabetic name parts with >= 2 chars to avoid initials like 'jkm40'
    alpha_parts = [re.sub(r"\d+$", "", p) for p in parts]
    alpha_parts = [p for p in alpha_parts if len(p) >= 2 and p.isalpha()]
    if len(alpha_parts) >= 2:
        return "Prof. " + " ".join(p.capitalize() for p in alpha_parts[:3])
    return ""


def text_matches_keywords(text: str, keywords: Sequence[str]) -> List[str]:
    """Return matched keywords using word-boundary awareness for short acronyms."""
    low = (text or "").lower()
    hits: List[str] = []
    for kw in keywords:
        clean_kw = kw.strip().lower()
        if not clean_kw:
            continue
        if len(clean_kw) <= 4 and " " not in clean_kw:
            if re.search(rf"\b{re.escape(clean_kw)}\b", low):
                hits.append(clean_kw)
        elif clean_kw in low:
            hits.append(clean_kw)
    return hits


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
        "Austria",
        "Denmark",
        "Norway",
        "Belgium",
        "Italy",
        "Spain",
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
    uni_words = [
        w for w in re.findall(r"[A-Za-z0-9]+", university or "")
        if w.lower() not in {"university", "of", "the", "at", "and", "in", "for"}
    ]
    dept_words = [
        w for w in re.findall(r"[A-Za-z0-9]+", department or "")
        if w.lower() not in {"department", "of", "the", "school", "faculty", "and", "for"}
    ]
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
        "emails": prioritize_emails(deobfuscate_emails(post_text)),
    }


def _extract_supervisor_from_text(text: str) -> str:
    """Extract a professor/supervisor name from unstructured recruitment text."""
    patterns = [
        r"(?:advised by|supervised by|mentored by|under the supervision of|research group of|led by|headed by)\s+((?:Prof\.?|Professor|Dr\.?|Asst\.?\s*Prof\.?|Assoc\.?\s*Prof\.?)\s+[A-Z][A-Za-z.\-']+(?:\s+[A-Z][A-Za-z.\-']+){1,3})",
        r"(?:Contact|PI|Principal Investigator|Supervisor|Advisor|Inquiries)\s*[:\-]\s*((?:Prof\.?|Professor|Dr\.?|Asst\.?\s*Prof\.?|Assoc\.?\s*Prof\.?)\s+[A-Z][A-Za-z.\-']+(?:\s+[A-Z][A-Za-z.\-']+){1,3})",
        r"(?:contact|reach out to|email|write to)\s+((?:Prof\.?|Professor|Dr\.?|Asst\.?\s*Prof\.?|Assoc\.?\s*Prof\.?)\s+[A-Z][A-Za-z.\-']+(?:\s+[A-Z][A-Za-z.\-']+){1,3})",
        r"\b((?:Prof\.?|Professor|Asst\.?\s*Prof\.?|Assoc\.?\s*Prof\.?)\s+(?:Dr\.?\s+)?[A-Z][A-Za-z.\-']+\s+[A-Z][A-Za-z.\-']+)\b",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            candidate = m.group(1).strip(" .,;:")
            if len(candidate) <= 60:
                return candidate
    return ""


def _clean_supervisor_field(raw_sup: str) -> str:
    """Trim sentence suffixes from extracted Supervisor field values."""
    if not raw_sup:
        return ""
    m = re.match(
        r"^((?:(?:Prof\.?|Professor|Dr\.?|Asst\.?\s*Prof\.?|Assoc\.?\s*Prof\.?)\s+)?[A-Z][A-Za-z.\-']+(?:\s+[A-Z][A-Za-z.\-']+){1,3})(?:\s*(?:,|;|\(|is\b|and\b))",
        raw_sup.strip(),
    )
    if m:
        return m.group(1).strip(" .,;:")
    return raw_sup.split("(", 1)[0].split(";", 1)[0].strip(" .,;:")[:60]


def extract_phdfinder_key_facts(html: str, url: str, today: Optional[date] = None) -> Dict[str, Any]:
    """Parses a PhDFinder opportunity page for structured metadata and LinkedIn link."""
    today = today or datetime.now(timezone.utc).date()
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("article") or soup
    title_elem = article.find("h1") or soup.find("h1")
    title = title_elem.get_text(" ", strip=True) if title_elem else ""
    full_text = article.get_text(" ", strip=True)

    # Trim header/footer/sidebar noise
    start_idx = full_text.find("By PhDFinder Team")
    end_idx = full_text.find("Follow the PhDFinder")
    if end_idx == -1:
        end_idx = full_text.find("Related Posts")
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
        pat = (
            rf"(?:–|-)?\s*{re.escape(label)}\s*:\s*(.+?)"
            r"(?=\s+(?:–|-)?\s*(?:Position type|Institution|University|Department or group|"
            r"Location|Country|Supervisor|Principal Investigator|PI|Contact|Funding or salary|"
            r"Duration|Start date|Apply by|Deadline|Fields|Research Project|Candidate Profile|"
            r"Application Process|Original advertisement|Original post)\s*:|$)"
        )
        m = re.search(pat, body, re.IGNORECASE)
        return m.group(1).strip(" –-:") if m else ""

    university = grab_field("University") or grab_field("Institution")
    country = grab_field("Country") or grab_field("Location")
    department = grab_field("Department or group")
    supervisor = _clean_supervisor_field(
        grab_field("Supervisor")
        or grab_field("Principal Investigator")
        or grab_field("PI")
        or grab_field("Contact")
    )
    funding = grab_field("Funding or salary")
    start_date = grab_field("Start date")
    deadline = grab_field("Deadline") or grab_field("Apply by")

    if not supervisor:
        supervisor = _extract_supervisor_from_text(body)

    if "," in country and "USA" in country:
        country = "USA"

    linkedin_url = ""
    for a in article.find_all("a", href=True):
        href = a["href"]
        if "linkedin.com/posts/" in href or "lnkd.in/" in href:
            linkedin_url = href
            break
    if not linkedin_url:
        m_ln = re.search(r"https?://(?:www\.)?(?:lnkd\.in/[^\s]+|linkedin\.com/posts/[^\s]+)", body)
        if m_ln:
            linkedin_url = m_ln.group(0).rstrip(".,;)")

    proj_idx = body.find("Research Project")
    end_proj = body.find("Original advertisement")
    if end_proj == -1:
        end_proj = body.find("Original post")
    verbatim_section = body[proj_idx:end_proj].strip() if proj_idx != -1 else body[:2000]

    # Separate clean relevance text (excludes PhDFinder's broad tag list when Research Project exists)
    relevance_text = f"{title} {verbatim_section}".strip()
    emails = prioritize_emails(deobfuscate_emails(body))

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
        "emails": emails,
        "body_text": re.sub(r"\s+", " ", verbatim_section).strip(),
        "relevance_text": re.sub(r"\s+", " ", relevance_text).strip(),
        "full_body": body,
    }


def extract_euraxess_key_facts(html: str, url: str, today: Optional[date] = None) -> Dict[str, Any]:
    """Parses a EURAXESS job offer page for structured metadata, contact email, and age."""
    today = today or datetime.now(timezone.utc).date()
    soup = BeautifulSoup(html, "html.parser")
    title_elem = soup.find("h1")
    title = title_elem.get_text(" ", strip=True) if title_elem else ""
    main_elem = soup.find("main") or soup
    full_text = re.sub(r"\s+", " ", main_elem.get_text(" ", strip=True)).strip()

    published_date: Optional[date] = None
    post_age_days: Optional[int] = None
    m_posted = re.search(r"Posted on:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})", full_text, re.IGNORECASE)
    if not m_posted:
        m_posted = DAY_MONTH_DATE_RE.search(full_text[:1000])
    if m_posted:
        date_token = m_posted.group(1)
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                published_date = datetime.strptime(date_token, fmt).date()
                post_age_days = max(0, (today - published_date).days)
                break
            except ValueError:
                continue

    def grab_euraxess_field(label: str) -> str:
        pat = (
            rf"{re.escape(label)}\s+(.+?)"
            r"(?=\s+(?:Organisation/Company|Department|Research Field|Researcher Profile|"
            r"Positions|Application Deadline|Country|Type of Contract|Job Status|"
            r"Hours Per Week|Offer Starting Date|Is the job funded|Reference Number|"
            r"Offer Description|Where to apply|Requirements|Additional Information|Work Location|Contact)\b|$)"
        )
        m = re.search(pat, full_text, re.IGNORECASE)
        return m.group(1).strip(" :-") if m else ""

    university = grab_euraxess_field("Organisation/Company")
    department = grab_euraxess_field("Department")
    country = grab_euraxess_field("Country")
    research_field = grab_euraxess_field("Research Field")
    positions = grab_euraxess_field("Positions")
    deadline = grab_euraxess_field("Application Deadline")
    start_date = grab_euraxess_field("Offer Starting Date")

    desc_start = full_text.find("Offer Description")
    desc_end = full_text.find("Work Location")
    if desc_end == -1:
        desc_end = len(full_text)
    offer_body = full_text[desc_start:desc_end] if desc_start != -1 else full_text[:2500]

    emails = prioritize_emails(deobfuscate_emails(full_text))
    supervisor = _extract_supervisor_from_text(offer_body)
    if not supervisor and emails:
        supervisor = infer_name_from_email(emails[0])

    return {
        "listing_url": url,
        "title": title,
        "university": university,
        "country": country,
        "department": department or research_field or "Computer Science / Engineering",
        "positions": positions,
        "supervisor": supervisor,
        "funding": "Funded (EURAXESS)",
        "start_date": start_date or "Spring/Fall 2027",
        "deadline": deadline,
        "published_date": published_date.isoformat() if published_date else "",
        "post_age_days": post_age_days,
        "emails": emails,
        "body_text": f"{title}. {positions}. {offer_body}".strip(),
        "relevance_text": f"{title} {research_field} {offer_body}".strip(),
    }


class Command(BaseCommand):
    help = (
        "Discover fresh (<7 days) professor recruitment announcements from LinkedIn posts "
        "and academic feeds (PhDFinder + EURAXESS), verify 2025/2026 publications & locks, "
        "and stage into SearchProf."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=5, help="Max new candidates to stage (default: 5).")
        parser.add_argument("--max-age", type=int, default=6, help="Max post age in days, strictly < 7 (default: 6).")
        parser.add_argument(
            "--fields",
            type=str,
            default=",".join(DEFAULT_FIELDS),
            help="Comma-separated PhDFinder category/country slugs to scan.",
        )
        parser.add_argument(
            "--keywords",
            type=str,
            default=None,
            help="Comma-separated search & relevance keywords (overrides default search queries).",
        )
        parser.add_argument(
            "--extra-keywords",
            type=str,
            default=None,
            help="Comma-separated additional keywords appended to search queries and relevance filter.",
        )
        parser.add_argument(
            "--sources",
            type=str,
            default=",".join(DEFAULT_SOURCES),
            help="Comma-separated discovery sources: phdfinder,euraxess (default: phdfinder,euraxess).",
        )
        parser.add_argument("--pages", type=int, default=2, help="Pages per feed/slug to scan (default: 2).")
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
        sources = {s.strip().lower() for s in options["sources"].split(",") if s.strip()}

        search_keywords, relevance_keywords = self._resolve_keywords(
            options.get("keywords"),
            options.get("extra_keywords"),
        )
        stats: Counter = Counter()

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
            cand = self._process_linkedin_url(u, today, max_age, relevance_keywords, stats)
            if not cand:
                continue
            row = self._validate_and_format_candidate(
                cand, existing_names, existing_emails, locked_groups, country_filter, include_phd_non_usa, stats
            )
            if row:
                staged_rows.append(row)
                self._register_local_seen(row, existing_names, existing_emails, locked_groups)

        # 3. Discover fresh opportunities from PhDFinder (slugs + keyword search + RSS)
        pages = max(1, options["pages"])
        self._thread_local = threading.local()
        self._stats_lock = threading.Lock()

        if len(staged_rows) < limit and not direct_urls and "phdfinder" in sources:
            fields = [f.strip() for f in options["fields"].split(",") if f.strip()]
            listing_urls = self._discover_phdfinder_urls(fields, search_keywords, pages, today, max_age)
            self.stdout.write(
                f"PhDFinder: found {len(listing_urls)} candidate listing(s) within <= {max_age} days."
            )

            pre_cands = self._fetch_listings_parallel(
                listing_urls,
                lambda u: self._process_phdfinder_listing(
                    u, today, max_age, linkedin_only, relevance_keywords, stats,
                    existing_emails=existing_emails,
                    country_filter=country_filter,
                    include_phd_non_usa=include_phd_non_usa,
                ),
            )
            for cand in pre_cands:
                if len(staged_rows) >= limit:
                    break
                row = self._validate_and_format_candidate(
                    cand, existing_names, existing_emails, locked_groups, country_filter, include_phd_non_usa, stats
                )
                if row:
                    staged_rows.append(row)
                    self._register_local_seen(row, existing_names, existing_emails, locked_groups)

        # 4. Discover fresh opportunities from EURAXESS (unless --linkedin-only)
        if len(staged_rows) < limit and not direct_urls and not linkedin_only and "euraxess" in sources:
            eu_urls = self._discover_euraxess_urls(search_keywords, pages)
            self.stdout.write(f"EURAXESS: found {len(eu_urls)} candidate job listing(s) to check.")

            eu_cands = self._fetch_listings_parallel(
                eu_urls,
                lambda u: self._process_euraxess_listing(
                    u, today, max_age, relevance_keywords, stats,
                    existing_emails=existing_emails,
                    country_filter=country_filter,
                    include_phd_non_usa=include_phd_non_usa,
                ),
            )
            for cand in eu_cands:
                if len(staged_rows) >= limit:
                    break
                row = self._validate_and_format_candidate(
                    cand, existing_names, existing_emails, locked_groups, country_filter, include_phd_non_usa, stats
                )
                if row:
                    staged_rows.append(row)
                    self._register_local_seen(row, existing_names, existing_emails, locked_groups)

        if stats:
            summary = ", ".join(f"{k}: {v}" for k, v in sorted(stats.items()))
            self.stdout.write(self.style.NOTICE(f"Filter stats -> {summary}"))

        if not staged_rows:
            self.stdout.write(self.style.WARNING("No new eligible candidates matched all filters."))
            if stats.get("non_usa_phd_only"):
                self.stdout.write(
                    self.style.NOTICE(
                        f"Tip: {stats['non_usa_phd_only']} non-USA PhD listing(s) were skipped by the Master's filter. "
                        "Pass --include-phd-non-usa to include them."
                    )
                )
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

    @staticmethod
    def _resolve_keywords(
        keywords_opt: Optional[str], extra_keywords_opt: Optional[str]
    ) -> Tuple[List[str], Tuple[str, ...]]:
        """Build search query keywords and the combined relevance keyword tuple."""
        if keywords_opt:
            search_kws = [k.strip() for k in keywords_opt.split(",") if k.strip()]
        else:
            search_kws = list(DEFAULT_SEARCH_KEYWORDS)

        extra_kws = [k.strip() for k in (extra_keywords_opt or "").split(",") if k.strip()]
        for ek in extra_kws:
            if ek.lower() not in {s.lower() for s in search_kws}:
                search_kws.append(ek)

        merged_relevance = list(RELEVANT_KEYWORDS)
        existing_low = {k.lower() for k in merged_relevance}
        for kw in search_kws:
            low = kw.lower()
            if low not in existing_low:
                merged_relevance.append(low)
                existing_low.add(low)

        return search_kws, tuple(merged_relevance)

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

    def _collect_phdfinder_links_from_html(
        self, html: str, today: date, max_age: int, seen: Set[str], urls: List[str]
    ) -> None:
        soup = BeautifulSoup(html, "html.parser")
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

    def _get(self, url: str, timeout: int = 12, **kwargs) -> requests.Response:
        tl = getattr(self, "_thread_local", None)
        if tl is not None:
            sess = getattr(tl, "session", None)
            if sess is None:
                sess = requests.Session()
                sess.headers.update(HEADERS)
                tl.session = sess
            return sess.get(url, headers=HEADERS, timeout=timeout, **kwargs)
        return requests.get(url, headers=HEADERS, timeout=timeout, **kwargs)

    def _bump_stat(self, stats: Optional[Counter], key: str) -> None:
        if stats is None:
            return
        lock = getattr(self, "_stats_lock", None)
        if lock:
            with lock:
                stats[key] += 1
        else:
            stats[key] += 1

    @staticmethod
    def _fetch_listings_parallel(urls: List[str], worker_fn, max_workers: int = 6) -> List[Dict[str, Any]]:
        """Fetch and pre-parse listing pages concurrently while preserving source order."""
        if not urls:
            return []
        ordered_results: Dict[int, Optional[Dict[str, Any]]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map = {pool.submit(worker_fn, u): idx for idx, u in enumerate(urls)}
            for fut in as_completed(future_map):
                idx = future_map[fut]
                try:
                    ordered_results[idx] = fut.result()
                except Exception:
                    ordered_results[idx] = None
        return [ordered_results[i] for i in range(len(urls)) if ordered_results.get(i)]

    @staticmethod
    def _is_non_usa_phd_only(country: str, post_text: str, include_phd_non_usa: bool) -> bool:
        """Return True if a non-USA post is PhD-only and should be skipped."""
        if country.lower() in {"usa", "united states", "us"} or include_phd_non_usa:
            return False
        low_text = (post_text or "").lower()
        masters_position_patterns = (
            r"\bmsc\s+(?:and|&|or|/)?\s*(?:phd\s+)?position",
            r"\bmasc\s+(?:and|&|or|/)?\s*(?:phd\s+)?position",
            r"\bphd\s*(?:&|and|or|/)\s*m\.?sc\b",
            r"\bphd\s*(?:&|and|or|/)\s*masc\b",
            r"\bmaster(?:'s)?\s+(?:by\s+research|thesis|student|position|positions|opening|program)",
            r"\bthesis-based\s+(?:msc|masc|master)",
            r"\bgraduate\s+research\s+assistant\b",
            r"\bscientist\s*\(\s*research\s+assistant\s*\)",
            r"\bmphil\b",
            r"\bhiwi\b",
            r"\bstudent\s+assistant\b",
        )
        has_masters_opening = any(re.search(pat, low_text) for pat in masters_position_patterns)
        return ("phd" in low_text or "doctoral" in low_text) and not has_masters_opening

    def _discover_phdfinder_urls(
        self,
        fields: List[str],
        keywords: List[str],
        pages: int,
        today: date,
        max_age: int,
    ) -> List[str]:
        """Collects non-postdoc PhDFinder URLs via category slugs, keyword search, and RSS."""
        seen: Set[str] = set()
        urls: List[str] = []

        # RSS feed for freshest items
        try:
            r_feed = self._get("https://phdfinder.com/feed/", timeout=10)
            if r_feed.status_code == 200:
                root = ET.fromstring(r_feed.text)
                for item in root.findall("./channel/item"):
                    link = (item.findtext("link") or "").strip()
                    if not link or link in seen or "postdoc" in link.lower():
                        continue
                    pub_raw = (item.findtext("pubDate") or "").strip()
                    age = None
                    if pub_raw:
                        try:
                            age = (today - parsedate_to_datetime(pub_raw).date()).days
                        except Exception:
                            age = None
                    if age is not None and 0 <= age <= max_age:
                        seen.add(link)
                        urls.append(link)
        except Exception as exc:
            logger.debug("PhDFinder RSS scan skipped: %s", exc)

        scan_urls: List[str] = []
        for slug in fields:
            for page in range(1, pages + 1):
                scan_urls.append(
                    f"https://phdfinder.com/search/{slug}/"
                    if page == 1
                    else f"https://phdfinder.com/search/{slug}/page/{page}/"
                )
        for kw in keywords:
            scan_urls.append(f"https://phdfinder.com/?s={quote_plus(kw)}")

        def fetch_scan(u: str) -> Optional[str]:
            try:
                resp = self._get(u, timeout=12)
                return resp.text if resp.status_code == 200 else None
            except Exception as exc:
                logger.warning(f"Error scanning {u}: {exc}")
                return None

        with ThreadPoolExecutor(max_workers=6) as pool:
            pages_html = list(pool.map(fetch_scan, scan_urls))

        for html in pages_html:
            if html:
                self._collect_phdfinder_links_from_html(html, today, max_age, seen, urls)

        return urls

    def _discover_euraxess_urls(self, keywords: List[str], pages: int) -> List[str]:
        """Collect newest EURAXESS job offer URLs across the active search keywords."""
        seen: Set[str] = set()
        urls: List[str] = []
        scan_urls: List[str] = []
        for kw in keywords[:6]:
            for page in range(0, pages):
                scan_urls.append(
                    "https://euraxess.ec.europa.eu/jobs/search"
                    f"?keywords={quote_plus(kw)}"
                    "&sort%5Bname%5D=created&sort%5Bdirection%5D=DESC"
                    + (f"&page={page}" if page > 0 else "")
                )

        def fetch_eu(u: str) -> Optional[str]:
            try:
                resp = self._get(u, timeout=12)
                return resp.text if resp.status_code == 200 else None
            except Exception as exc:
                logger.warning(f"Error scanning EURAXESS {u}: {exc}")
                return None

        with ThreadPoolExecutor(max_workers=4) as pool:
            pages_html = list(pool.map(fetch_eu, scan_urls))

        for html in pages_html:
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.search(r"/jobs/\d+$", href):
                    full_url = urljoin("https://euraxess.ec.europa.eu", href)
                    if full_url not in seen:
                        seen.add(full_url)
                        urls.append(full_url)
        return urls

    def _process_linkedin_url(
        self,
        url: str,
        today: date,
        max_age: int,
        relevance_keywords: Sequence[str] = RELEVANT_KEYWORDS,
        stats: Optional[Counter] = None,
    ) -> Optional[Dict[str, Any]]:
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
            if stats is not None:
                stats["age_filtered"] += 1
            return None

        text = parsed["post_text"]
        if not text_matches_keywords(text, relevance_keywords):
            if stats is not None:
                stats["keyword_mismatch"] += 1
            return None

        emails = parsed["emails"]
        if not emails:
            if stats is not None:
                stats["missing_email"] += 1
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
        self,
        url: str,
        today: date,
        max_age: int,
        linkedin_only: bool,
        relevance_keywords: Sequence[str] = RELEVANT_KEYWORDS,
        stats: Optional[Counter] = None,
        existing_emails: Optional[Set[str]] = None,
        country_filter: Optional[str] = None,
        include_phd_non_usa: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Fetches a PhDFinder listing and follows any LinkedIn post link inside it."""
        try:
            resp = self._get(url, timeout=15)
            if resp.status_code != 200:
                return None
            info = extract_phdfinder_key_facts(resp.text, url, today=today)
        except Exception as exc:
            logger.warning(f"Error fetching {url}: {exc}")
            return None

        if linkedin_only and not info["linkedin_url"]:
            if stats is not None:
                stats["no_linkedin_link"] += 1
            return None

        age = info["post_age_days"]
        if age is None or age > max_age:
            if stats is not None:
                stats["age_filtered"] += 1
            return None

        combined_text = info.get("relevance_text") or f"{info['title']} {info['body_text']}"
        if not text_matches_keywords(combined_text, relevance_keywords):
            if stats is not None:
                stats["keyword_mismatch"] += 1
            return None

        post_text = info["body_text"]
        linkedin_url = info["linkedin_url"]
        emails = list(info["emails"])

        if linkedin_url:
            try:
                li_resp = self._get(linkedin_url, timeout=12, allow_redirects=True)
                if li_resp.status_code == 200 and "linkedin.com/posts/" in li_resp.url:
                    li_parsed = parse_linkedin_post_html(li_resp.text, li_resp.url, today=today)
                    if li_parsed["post_text"]:
                        post_text = li_parsed["post_text"]
                    if li_parsed["post_age_days"] is not None:
                        age = li_parsed["post_age_days"]
                        if age > max_age:
                            if stats is not None:
                                stats["age_filtered"] += 1
                            return None
                    for em in li_parsed["emails"]:
                        if em not in emails:
                            emails.insert(0, em)
                    if not info["supervisor"] and li_parsed["author_name"]:
                        info["supervisor"] = f"Prof. {li_parsed['author_name']}"
                    linkedin_url = li_parsed["source_url"]
            except Exception:
                pass

        emails = prioritize_emails(emails)
        if not emails:
            if stats is not None:
                stats["missing_email"] += 1
            return None

        country = info["country"] or infer_country_from_email_or_text(emails[0], post_text)
        if country_filter and country.lower() != country_filter:
            if stats is not None:
                stats["country_filtered"] += 1
            return None

        if self._is_non_usa_phd_only(country, post_text, include_phd_non_usa):
            if stats is not None:
                stats["non_usa_phd_only"] += 1
            return None

        if existing_emails and emails[0].lower() in existing_emails:
            if stats is not None:
                stats["duplicate_seen"] += 1
            return None

        supervisor = info["supervisor"] or infer_name_from_email(emails[0])
        if not supervisor and not is_generic_email(emails[0]):
            extracted = self._llm_extract_fields(post_text, "", emails[0])
            supervisor = extracted.get("professor_name", "").strip()
        if not supervisor:
            if stats is not None:
                stats["missing_supervisor"] += 1
            return None

        return {
            "professor_name": supervisor,
            "university": info["university"] or "Unknown University",
            "country": country,
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

    def _process_euraxess_listing(
        self,
        url: str,
        today: date,
        max_age: int,
        relevance_keywords: Sequence[str] = RELEVANT_KEYWORDS,
        stats: Optional[Counter] = None,
        existing_emails: Optional[Set[str]] = None,
        country_filter: Optional[str] = None,
        include_phd_non_usa: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Fetches a EURAXESS job offer page and normalizes it into a candidate dict."""
        try:
            resp = self._get(url, timeout=15)
            if resp.status_code != 200:
                return None
            info = extract_euraxess_key_facts(resp.text, url, today=today)
        except Exception as exc:
            logger.warning(f"Error fetching EURAXESS {url}: {exc}")
            return None

        age = info["post_age_days"]
        if age is None or age > max_age:
            if stats is not None:
                stats["age_filtered"] += 1
            return None

        if not text_matches_keywords(info.get("relevance_text") or info["body_text"], relevance_keywords):
            if stats is not None:
                stats["keyword_mismatch"] += 1
            return None

        emails = info["emails"]
        if not emails:
            if stats is not None:
                stats["missing_email"] += 1
            return None

        country = info["country"] or infer_country_from_email_or_text(emails[0], info["body_text"])
        if country_filter and country.lower() != country_filter:
            if stats is not None:
                stats["country_filtered"] += 1
            return None

        if self._is_non_usa_phd_only(country, info["body_text"], include_phd_non_usa):
            if stats is not None:
                stats["non_usa_phd_only"] += 1
            return None

        if existing_emails and emails[0].lower() in existing_emails:
            if stats is not None:
                stats["duplicate_seen"] += 1
            return None

        supervisor = info["supervisor"] or infer_name_from_email(emails[0])
        if not supervisor and not is_generic_email(emails[0]):
            extracted = self._llm_extract_fields(info["body_text"], "", emails[0])
            supervisor = extracted.get("professor_name", "").strip()
        if not supervisor:
            if stats is not None:
                stats["missing_supervisor"] += 1
            return None

        return {
            "professor_name": supervisor,
            "university": info["university"] or "Unknown University",
            "country": country,
            "department": info["department"] or "Computer Science / Engineering",
            "email": emails[0],
            "post_age": age,
            "post_text": info["body_text"][:2000],
            "linkedin_url": url,
            "funding": info["funding"],
            "intake": info["start_date"] or "Spring/Fall 2027",
            "subject_hint": "",
            "deadline": info["deadline"],
        }

    def _llm_extract_fields(self, text: str, author: str, email: str) -> Dict[str, str]:
        """Optional Gemini extraction for raw posts; returns empty dict on quota/failure."""
        api_key = os.getenv("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            return {}
        prompt = (
            "Extract JSON with keys: professor_name, university, country, department, funding, intake, subject_hint "
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
        """Queries OpenAlex (with polite mailto) and falls back to Semantic Scholar for 2025/2026 papers."""
        clean = re.sub(
            r"^(Prof\.?|Professor|Dr\.?|Asst\.?\s*Prof\.?|Assoc\.?\s*Prof\.?)\s+",
            "",
            prof_name,
            flags=re.IGNORECASE,
        ).strip()
        if not clean:
            return "", []

        mailto = (
            os.getenv("EMAIL_HOST_USER")
            or getattr(settings, "CANDIDATE_PROFILE", {}).get("email", "")
            or "research@example.org"
        )
        uni_tokens = [w.lower() for w in re.findall(r"[A-Za-z]+", university or "") if len(w) > 3]

        # Primary: OpenAlex
        try:
            r = self._get(
                f"https://api.openalex.org/authors?search={quote_plus(clean)}&mailto={quote_plus(mailto)}&per-page=5",
                timeout=8,
            )
            if r.status_code == 200:
                authors = r.json().get("results", [])
                chosen = None
                for a in authors:
                    insts = " ".join(
                        (i.get("display_name") or "").lower() for i in a.get("last_known_institutions", [])
                    )
                    if uni_tokens and any(tok in insts for tok in uni_tokens):
                        chosen = a
                        break
                if not chosen and authors:
                    chosen = authors[0]
                if chosen:
                    aid = chosen["id"].split("/")[-1]
                    rw = self._get(
                        f"https://api.openalex.org/works?filter=author.id:{aid},publication_year:2025-2026&sort=publication_date:desc&mailto={quote_plus(mailto)}&per-page=3",
                        timeout=8,
                    )
                    if rw.status_code == 200:
                        titles = [
                            f"{w.get('publication_year')}: {w['title']}"
                            for w in rw.json().get("results", [])
                            if w.get("title")
                        ]
                        if titles:
                            return chosen["id"], titles
        except Exception:
            pass

        # Fallback: Semantic Scholar Graph API
        try:
            rs = self._get(
                f"https://api.semanticscholar.org/graph/v1/author/search?query={quote_plus(clean)}&limit=5&fields=name,affiliations,url,papers.title,papers.year",
                timeout=8,
            )
            if rs.status_code == 200:
                authors = rs.json().get("data", [])
                chosen = None
                for a in authors:
                    affs = " ".join(a.get("affiliations") or []).lower()
                    if uni_tokens and any(tok in affs for tok in uni_tokens):
                        chosen = a
                        break
                if not chosen and authors:
                    chosen = authors[0]
                if chosen:
                    recent = [
                        f"{p['year']}: {p['title']}"
                        for p in (chosen.get("papers") or [])
                        if p.get("title") and p.get("year") in (2025, 2026)
                    ]
                    if recent:
                        return chosen.get("url") or "", recent[:3]
        except Exception:
            pass

        return "", []

    def _validate_and_format_candidate(
        self,
        cand: Dict[str, Any],
        existing_names: Set[str],
        existing_emails: Set[str],
        locked_groups: Set[str],
        country_filter: Optional[str],
        include_phd_non_usa: bool,
        stats: Optional[Counter] = None,
    ) -> Optional[List[str]]:
        """Applies country, degree-alignment, publication recency, duplicate, and lock checks."""
        prof_name = cand["professor_name"].strip()
        email = cand["email"].strip().lower()
        country = cand["country"].strip()
        university = cand["university"].strip()
        department = cand["department"].strip()

        if country_filter and country.lower() != country_filter:
            if stats is not None:
                stats["country_filtered"] += 1
            return None

        if self._is_non_usa_phd_only(country, cand["post_text"], include_phd_non_usa):
            if stats is not None:
                stats["non_usa_phd_only"] += 1
            return None

        if prof_name.lower() in existing_names or email in existing_emails:
            if stats is not None:
                stats["duplicate_seen"] += 1
            return None

        lock = make_contact_group(university, department, country)
        if lock.lower() in locked_groups:
            if stats is not None:
                stats["group_locked"] += 1
            return None

        # Verify 2025/2026 research activity via OpenAlex / Semantic Scholar
        openalex_url, recent_papers = self._verify_recent_publications(prof_name, university)
        if not recent_papers:
            if stats is not None:
                stats["no_recent_pubs"] += 1
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
