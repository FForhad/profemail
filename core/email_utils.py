import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import gspread
from django.core.mail import EmailMultiAlternatives


SIGN_OFF_PATTERNS = [
    r"Sincerely,\s*Forhad Uddin Ahmed",
    r"Best regards,\s*Forhad Uddin Ahmed",
    r"Warm regards,\s*Forhad Uddin Ahmed",
    r"Regards,\s*Forhad Uddin Ahmed",
    r"Sincerely,",
    r"Best regards,",
]


def load_attachments(attachments_dir: Path) -> List[Path]:
    """Return sorted non-hidden attachment file paths from attachments_dir."""
    if not attachments_dir.exists() or not attachments_dir.is_dir():
        return []
    attachments = [
        f for f in attachments_dir.iterdir()
        if f.is_file() and not f.name.startswith(".")
    ]
    attachments.sort(key=lambda p: p.name)
    return attachments


def load_signatures(signature_path: Path) -> Tuple[str, str]:
    """Load plain-text and companion HTML signature from signature_path."""
    signature_text = ""
    if signature_path.exists():
        signature_text = signature_path.read_text(encoding="utf-8").strip()

    html_sig_path = signature_path.with_suffix(".html")
    signature_html = ""
    if html_sig_path.exists():
        signature_html = html_sig_path.read_text(encoding="utf-8").strip()

    return signature_text, signature_html


def strip_signoff(draft: str) -> str:
    """Remove trailing sign-off lines before appending a styled HTML signature."""
    for pat in SIGN_OFF_PATTERNS:
        match = re.search(pat, draft, re.IGNORECASE)
        if match:
            return draft[:match.start()].rstrip()
    return draft.rstrip()


def merge_signature(draft: str, signature: str) -> str:
    """Merge a plain-text signature into the draft without duplicating sign-offs."""
    if not signature:
        return draft

    sig_starts_with_signoff = any(
        signature.lower().startswith(p)
        for p in ["sincerely", "best regards", "regards", "warm regards"]
    )

    for pat in SIGN_OFF_PATTERNS:
        match = re.search(pat, draft, re.IGNORECASE)
        if match:
            if sig_starts_with_signoff:
                return draft[:match.start()].rstrip() + "\n\n" + signature
            return draft[:match.end()].rstrip() + "\n" + signature

    return draft.rstrip() + "\n\n" + signature


def extract_subject_and_body(draft: str, subject: str, country: str) -> Tuple[str, str]:
    """Ensure subject is populated, extracting an inline 'Subject:' line or using fallback."""
    clean_subject = (subject or "").strip()
    clean_draft = (draft or "").strip()

    if not clean_subject:
        lines = [ln.strip() for ln in clean_draft.splitlines() if ln.strip()]
        if lines and lines[0].lower().startswith("subject:"):
            clean_subject = lines[0].split(":", 1)[1].strip()
            clean_draft = "\n\n".join(lines[1:]).strip()
        else:
            is_usa = (country or "").lower().strip() in ["usa", "us", "united states"]
            degree_str = "PhD" if is_usa else "Master's"
            clean_subject = f"Exploring {degree_str} Research Opportunities – Forhad Uddin Ahmed"

    return clean_subject, clean_draft


def build_outreach_email(
    subject: str,
    draft: str,
    to_email: str,
    from_email: str,
    signature_text: str = "",
    signature_html: str = "",
    attachments: Optional[List[Path]] = None,
) -> EmailMultiAlternatives:
    """Build a multipart outreach email with plain text, HTML signature, and attachments."""
    final_body = merge_signature(draft, signature_text)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=final_body,
        from_email=from_email,
        to=[to_email],
    )

    if signature_html:
        body_without_signoff = strip_signoff(draft)
        paragraphs = [
            p.strip().replace("\n", "<br/>")
            for p in body_without_signoff.split("\n\n")
            if p.strip()
        ]
        html_paragraphs = "".join(
            f"<p style='margin: 0 0 16px 0; font-family: Arial, Helvetica, sans-serif; "
            f"font-size: 14px; line-height: 1.6; color: #222222;'>{p}</p>"
            for p in paragraphs
        )
        full_html = f"<div dir='ltr'>{html_paragraphs}{signature_html}</div>"
        msg.attach_alternative(full_html, "text/html")

    for att in attachments or []:
        msg.attach_file(str(att))

    return msg


def open_outreach_worksheet(creds_path: str, sheet_url: str, ws_name: str):
    """Open the configured Google Sheet worksheet using service account credentials."""
    gc = gspread.service_account(filename=creds_path)
    sh = gc.open_by_url(sheet_url)
    try:
        return sh.worksheet(ws_name)
    except Exception:
        return sh.get_worksheet(0)


def resolve_sheet_columns(header_values: List[str]) -> Dict[str, int]:
    """Map standard outreach column names to 0-based column indices."""
    header_map = {col.strip(): idx for idx, col in enumerate(header_values)}

    def find_col_idx(candidates: List[str]) -> int:
        for candidate in candidates:
            for name, idx in header_map.items():
                if name.lower().strip() == candidate.lower().strip():
                    return idx
        return -1

    return {
        "status": find_col_idx(["Pipeline Status", "Status", "Pipeline"]),
        "email": find_col_idx(["Professor Email", "Email", "Contact Email"]),
        "name": find_col_idx(["Professor Name", "Name"]),
        "draft": find_col_idx(["Email Draft", "Draft Email", "LLM Draft Email", "Draft"]),
        "subject": find_col_idx(["Email Subject", "Subject"]),
        "university": find_col_idx(["University", "Institution"]),
        "country": find_col_idx(["Country", "Location", "Nation"]),
        "timezone": find_col_idx(["Target Timezone", "Timezone", "TZ"]),
        "first_contact": find_col_idx(["First Contact Date", "Contact Date"]),
        "last_contact": find_col_idx(["Last Contact Date"]),
        "group": find_col_idx(["Contact Group (Lock)", "Contact Group", "Group", "Lock"]),
    }


def collect_sheet_candidates(
    all_values: List[List[str]],
    col_map: Dict[str, int],
    target_statuses: Set[str],
    target_row: Optional[int] = None,
    country_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter Google Sheet data rows by status, optional row number, and optional country."""
    data_rows = all_values[1:]
    status_idx = col_map["status"]
    email_idx = col_map["email"]
    name_idx = col_map["name"]
    draft_idx = col_map["draft"]
    subject_idx = col_map["subject"]
    uni_idx = col_map["university"]
    country_idx = col_map["country"]
    tz_idx = col_map["timezone"]

    normalized_statuses = {s.strip().lower() for s in target_statuses if s.strip()}
    match_all = "all" in normalized_statuses
    country_target = (country_filter or "").strip().lower()

    candidates: List[Dict[str, Any]] = []
    for idx, row in enumerate(data_rows):
        sheet_row_num = idx + 2
        if target_row and sheet_row_num != target_row:
            continue

        status_val = row[status_idx].strip() if len(row) > status_idx else ""
        if not match_all and status_val.lower() not in normalized_statuses:
            continue

        country = row[country_idx].strip() if (country_idx >= 0 and len(row) > country_idx) else ""
        if country_target and country.lower() != country_target:
            continue

        prof_email = row[email_idx].strip() if len(row) > email_idx else ""
        prof_name = row[name_idx].strip() if (name_idx >= 0 and len(row) > name_idx) else f"Row {sheet_row_num}"
        subject = row[subject_idx].strip() if (subject_idx >= 0 and len(row) > subject_idx) else ""
        draft = row[draft_idx].strip() if len(row) > draft_idx else ""
        uni = row[uni_idx].strip() if (uni_idx >= 0 and len(row) > uni_idx) else ""
        tz_hint = row[tz_idx].strip() if (tz_idx >= 0 and len(row) > tz_idx) else ""

        subject, draft = extract_subject_and_body(draft, subject, country)

        candidates.append({
            "row_num": sheet_row_num,
            "name": prof_name,
            "university": uni,
            "country": country,
            "tz_hint": tz_hint,
            "email": prof_email,
            "subject": subject,
            "draft": draft,
            "status": status_val,
        })

    return candidates
