import base64
import json
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

from django.core.mail import EmailMultiAlternatives
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Least-privilege scope for creating, listing, updating, and sending Gmail drafts
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


class GmailAuthError(Exception):
    """Raised when Gmail OAuth credentials are missing or invalid for personal Gmail."""


def validate_oauth_client_file(creds_path: Path) -> None:
    """Verify that creds_path points to an OAuth 2.0 client secret JSON, not a service account."""
    if not creds_path.exists():
        raise GmailAuthError(
            f"Gmail OAuth credentials file '{creds_path}' was not found.\n"
            "Setup steps:\n"
            "  1. Open Google Cloud Console -> APIs & Services -> Library -> enable 'Gmail API'.\n"
            "  2. Configure OAuth consent screen (External, add your Gmail under Test users).\n"
            "  3. Create Credentials -> OAuth client ID -> Application type: Desktop app.\n"
            f"  4. Download the JSON and save it as '{creds_path}'."
        )

    try:
        data = json.loads(creds_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GmailAuthError(f"Gmail OAuth credentials file '{creds_path}' is not valid JSON: {exc}") from exc

    if data.get("type") == "service_account":
        raise GmailAuthError(
            f"'{creds_path}' is a Google Service Account key (used for Google Sheets), "
            "which cannot create drafts in a personal @gmail.com account.\n"
            "Please create an OAuth 2.0 Client ID (Desktop app) in Google Cloud Console "
            "and save it to 'gmail_credentials.json'."
        )

    if "installed" not in data and "web" not in data:
        raise GmailAuthError(
            f"'{creds_path}' does not look like a Google OAuth 2.0 client JSON "
            "(expected top-level 'installed' or 'web' key)."
        )


def authenticate_gmail(
    creds_path: Path,
    token_path: Path,
    no_browser: bool = False,
) -> Credentials:
    """Load, refresh, or interactively obtain Gmail OAuth2 user credentials."""
    creds: Optional[Credentials] = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            validate_oauth_client_file(creds_path)
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0, open_browser=not no_browser)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def get_gmail_service(
    creds_path: Path,
    token_path: Path,
    no_browser: bool = False,
):
    """Build and return an authenticated Gmail API v1 service client."""
    creds = authenticate_gmail(creds_path=creds_path, token_path=token_path, no_browser=no_browser)
    return build("gmail", "v1", credentials=creds)


def get_authenticated_email(service: Any, user_id: str = "me") -> str:
    """Return the authenticated user's Gmail address."""
    profile = service.users().getProfile(userId=user_id).execute()
    return profile.get("emailAddress", "")


def normalize_draft_key(to_header: str, subject: str) -> Tuple[str, str]:
    """Normalize (recipient email, subject) for duplicate draft detection."""
    _, addr = parseaddr(to_header or "")
    email_key = (addr or to_header or "").strip().lower()
    subject_key = (subject or "").strip().lower()
    return email_key, subject_key


def list_existing_draft_keys(
    service: Any,
    user_id: str = "me",
    max_pages: int = 10,
) -> Set[Tuple[str, str]]:
    """Collect normalized (to_email, subject) pairs for existing Gmail drafts."""
    keys: Set[Tuple[str, str]] = set()
    page_token: Optional[str] = None
    pages = 0

    while pages < max_pages:
        req_kwargs: Dict[str, Any] = {"userId": user_id, "maxResults": 100}
        if page_token:
            req_kwargs["pageToken"] = page_token
        resp = service.users().drafts().list(**req_kwargs).execute()
        drafts = resp.get("drafts", []) or []

        for draft_stub in drafts:
            draft_id = draft_stub.get("id")
            if not draft_id:
                continue
            detail = service.users().drafts().get(
                userId=user_id,
                id=draft_id,
                format="metadata",
                metadataHeaders=["To", "Subject"],
            ).execute()
            headers = (
                detail.get("message", {})
                .get("payload", {})
                .get("headers", [])
            )
            to_val = ""
            subj_val = ""
            for hdr in headers:
                name = (hdr.get("name") or "").lower()
                if name == "to":
                    to_val = hdr.get("value", "")
                elif name == "subject":
                    subj_val = hdr.get("value", "")
            if to_val or subj_val:
                keys.add(normalize_draft_key(to_val, subj_val))

        page_token = resp.get("nextPageToken")
        pages += 1
        if not page_token:
            break

    return keys


def encode_email_for_gmail(msg: EmailMultiAlternatives) -> str:
    """Serialize a Django EmailMultiAlternatives object to base64url for Gmail API."""
    raw_bytes = msg.message().as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii")


def create_gmail_draft(
    service: Any,
    msg: EmailMultiAlternatives,
    user_id: str = "me",
) -> Dict[str, Any]:
    """Create a draft in the user's Gmail Drafts folder and return the API response."""
    encoded = encode_email_for_gmail(msg)
    return service.users().drafts().create(
        userId=user_id,
        body={"message": {"raw": encoded}},
    ).execute()
