import logging
import os
from datetime import datetime, date
from typing import Optional, List, Dict, Any

import gspread
import pandas as pd
from django.conf import settings
from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone
from google.oauth2.service_account import Credentials

from core.models import Professor

logger = logging.getLogger(__name__)


class GoogleSheetSyncService:
    """
    Service class to synchronize professor data bidirectionally between
    the Django `Professor` database model and a Google Sheet.

    Uses `gspread` for Google Sheets API communication and `pandas` for
    efficient tabular parsing, cleaning, filtering, and diffing.
    """

    DEFAULT_SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    # Mapping between Google Sheet header names and Django model field names
    COLUMN_MAPPING = {
        "Professor Name": "name",
        "Name": "name",
        "University": "university",
        "Country": "country",
        "Department/Lab": "department",
        "Department": "department",
        "Contact Group": "contact_group",
        "Professor Email": "email",
        "Email": "email",
        "Email Subject": "email_subject",
        "Professor Profile URL": "profile_url",
        "Profile URL": "profile_url",
        "Lab / University Website URL": "lab_website_url",
        "Lab Website URL": "lab_website_url",
        "Research Area": "research_area",
        "Recent Publications": "recent_publications",
        "h-index": "h_index",
        "Citations": "citations",
        "Funding Status": "funding_status",
        "Pipeline Status": "pipeline_status",
        "Priority": "priority",
        "First Contact Date": "first_contact_date",
        "Last Contact Date": "last_contact_date",
        "Follow-up #1 Date": "follow_up_1_date",
        "Follow-up #2 Date": "follow_up_2_date",
        "Response Date": "response_date",
        "Meeting Scheduled": "meeting_scheduled",
        "Application Submitted": "application_submitted",
        "Deadline": "deadline",
        "LLM Research Summary": "llm_research_summary",
        "LLM Alignment Hook": "llm_alignment_hook",
        "LLM Draft Email": "llm_draft_email",
        "Notes & Next Action": "notes",
        "Notes": "notes",
    }

    # Reverse mapping: model field -> preferred canonical sheet header
    FIELD_TO_SHEET_COLUMN = {
        "name": "Professor Name",
        "university": "University",
        "country": "Country",
        "department": "Department/Lab",
        "contact_group": "Contact Group",
        "email": "Professor Email",
        "email_subject": "Email Subject",
        "profile_url": "Professor Profile URL",
        "lab_website_url": "Lab / University Website URL",
        "research_area": "Research Area",
        "recent_publications": "Recent Publications",
        "h_index": "h-index",
        "citations": "Citations",
        "funding_status": "Funding Status",
        "pipeline_status": "Pipeline Status",
        "priority": "Priority",
        "first_contact_date": "First Contact Date",
        "last_contact_date": "Last Contact Date",
        "follow_up_1_date": "Follow-up #1 Date",
        "follow_up_2_date": "Follow-up #2 Date",
        "response_date": "Response Date",
        "meeting_scheduled": "Meeting Scheduled",
        "application_submitted": "Application Submitted",
        "deadline": "Deadline",
        "llm_research_summary": "LLM Research Summary",
        "llm_alignment_hook": "LLM Alignment Hook",
        "llm_draft_email": "LLM Draft Email",
        "notes": "Notes & Next Action",
    }

    def __init__(
        self,
        sheet_key_or_url: Optional[str] = None,
        worksheet_name_or_index: Any = 0,
        credentials_path: Optional[str] = None,
        client: Optional[gspread.Client] = None,
    ):
        """
        Initialize GoogleSheetSyncService.

        :param sheet_key_or_url: Google Sheet ID or full spreadsheet URL.
        :param worksheet_name_or_index: Sheet title (str) or index (int). Defaults to 0.
        :param credentials_path: Path to service account json key file.
        :param client: Optional pre-configured gspread client.
        """
        self.sheet_key_or_url = (
            sheet_key_or_url
            or getattr(settings, "GOOGLE_SHEET_KEY", None)
            or getattr(settings, "GOOGLE_SHEET_URL", None)
            or os.environ.get("GOOGLE_SHEET_KEY")
            or os.environ.get("GOOGLE_SHEET_URL")
        )
        self.worksheet_name_or_index = worksheet_name_or_index
        self.credentials_path = (
            credentials_path
            or getattr(settings, "GOOGLE_SHEETS_CREDENTIALS_PATH", None)
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        )
        self._client = client
        self._worksheet = None

    def get_client(self) -> gspread.Client:
        """Obtain or authenticate gspread Client using service account credentials."""
        if self._client is not None:
            return self._client

        if self.credentials_path and os.path.exists(self.credentials_path):
            credentials = Credentials.from_service_account_file(
                self.credentials_path, scopes=self.DEFAULT_SCOPES
            )
            self._client = gspread.authorize(credentials)
        else:
            try:
                self._client = gspread.service_account(
                    filename=self.credentials_path or "credentials.json",
                    scopes=self.DEFAULT_SCOPES,
                )
            except Exception as exc:
                raise ValueError(
                    f"Unable to authenticate with Google Sheets API: {exc}. "
                    "Please set GOOGLE_APPLICATION_CREDENTIALS or provide credentials_path."
                ) from exc

        return self._client

    def get_worksheet(self) -> gspread.Worksheet:
        """Retrieve target Worksheet instance."""
        if self._worksheet is not None:
            return self._worksheet

        if not self.sheet_key_or_url:
            raise ValueError(
                "No sheet key or URL provided. Pass sheet_key_or_url or configure GOOGLE_SHEET_KEY."
            )

        client = self.get_client()
        if self.sheet_key_or_url.startswith("http"):
            spreadsheet = client.open_by_url(self.sheet_key_or_url)
        else:
            spreadsheet = client.open_by_key(self.sheet_key_or_url)

        if isinstance(self.worksheet_name_or_index, int):
            self._worksheet = spreadsheet.get_worksheet(self.worksheet_name_or_index)
        else:
            self._worksheet = spreadsheet.worksheet(str(self.worksheet_name_or_index))

        return self._worksheet

    def _clean_date(self, val: Any) -> Optional[date]:
        """Safely parse date values using pandas."""
        if pd.isna(val) or val is None:
            return None
        val_str = str(val).strip()
        if not val_str:
            return None
        try:
            parsed = pd.to_datetime(val_str, errors="coerce")
            if pd.isna(parsed):
                return None
            return parsed.date()
        except Exception:
            return None

    def _clean_int(self, val: Any) -> Optional[int]:
        """Safely parse integer values."""
        if pd.isna(val) or val is None:
            return None
        try:
            val_float = float(val)
            if pd.isna(val_float):
                return None
            return int(val_float)
        except (ValueError, TypeError):
            return None

    def _clean_str(self, val: Any) -> str:
        """Safely clean text values."""
        if pd.isna(val) or val is None:
            return ""
        return str(val).strip()

    def _map_pipeline_status(self, val: str) -> str:
        """Normalize raw sheet pipeline status strings into model choice codes."""
        val_clean = val.lower().replace("_", " ").replace("-", " ").strip()
        if "pending" in val_clean:
            return "pending"
        elif "identif" in val_clean or "backlog" in val_clean:
            return "identified"
        elif "research" in val_clean or "qualif" in val_clean:
            return "researched"
        elif "draft" in val_clean:
            return "email_drafted"
        elif "contact" in val_clean or "sent" in val_clean:
            return "contacted"
        elif "follow" in val_clean and "1" in val_clean:
            return "follow_up_1"
        elif "follow" in val_clean and "2" in val_clean:
            return "follow_up_2"
        elif "discuss" in val_clean or "repli" in val_clean:
            return "discussion"
        elif "meeting" in val_clean:
            return "meeting_scheduled"
        elif "interview" in val_clean:
            return "interviewed"
        elif "appl" in val_clean:
            return "applied"
        elif "accept" in val_clean or "offer" in val_clean:
            return "accepted"
        elif "declin" in val_clean or "reject" in val_clean or "closed" in val_clean:
            return "declined"
        elif "no response" in val_clean or "expired" in val_clean:
            return "no_response"
        return "pending"

    def _map_priority(self, val: str) -> str:
        """Normalize priority strings or numbers into 'high', 'medium', 'low'."""
        val_clean = val.lower().strip()
        if "high" in val_clean or "urgent" in val_clean:
            return "high"
        elif "low" in val_clean:
            return "low"
        try:
            num = float(val_clean)
            if num <= 3:
                return "high"
            elif num <= 7:
                return "medium"
            else:
                return "low"
        except (ValueError, TypeError):
            pass
        return "medium"

    # =========================================================================
    # 1) fetch_pending()
    # =========================================================================
    def fetch_pending(self, worksheet: Optional[gspread.Worksheet] = None) -> List[Professor]:
        """
        Downloads all rows from the Google Sheet, uses pandas to filter rows
        where 'Pipeline Status' is 'Pending' (case-insensitive), and saves
        or updates them in the Django database.

        :param worksheet: Optional worksheet override (for testing/mocking).
        :return: List of created or updated Professor model instances.
        """
        ws = worksheet or self.get_worksheet()
        all_records = ws.get_all_records()
        if not all_records:
            logger.info("fetch_pending: Google Sheet is empty.")
            return []

        df = pd.DataFrame(all_records)

        status_col = None
        for col in df.columns:
            if str(col).strip().lower() in ["pipeline status", "pipeline_status", "status"]:
                status_col = col
                break

        if not status_col:
            logger.warning("fetch_pending: 'Pipeline Status' column not found in sheet.")
            return []

        pending_mask = df[status_col].astype(str).str.strip().str.lower() == "pending"
        pending_df = df[pending_mask]

        if pending_df.empty:
            logger.info("fetch_pending: No rows with Pipeline Status = 'Pending' found.")
            return []

        saved_professors: List[Professor] = []

        with transaction.atomic():
            for idx, row in pending_df.iterrows():
                sheet_row_num = int(idx) + 2

                field_data: Dict[str, Any] = {}
                for col_name, val in row.items():
                    norm_col = str(col_name).strip()
                    if norm_col in self.COLUMN_MAPPING:
                        field_key = self.COLUMN_MAPPING[norm_col]
                        field_data[field_key] = val

                name = self._clean_str(field_data.get("name", ""))
                university = self._clean_str(field_data.get("university", ""))
                email = self._clean_str(field_data.get("email", ""))

                if not name and not email:
                    continue

                model_attrs = {
                    "name": name or "Unknown",
                    "university": university,
                    "country": self._clean_str(field_data.get("country", "")),
                    "department": self._clean_str(field_data.get("department", "")),
                    "contact_group": self._clean_str(field_data.get("contact_group", "")),
                    "email": email,
                    "email_subject": self._clean_str(field_data.get("email_subject", "")),
                    "profile_url": self._clean_str(field_data.get("profile_url", "")),
                    "lab_website_url": self._clean_str(field_data.get("lab_website_url", "")),
                    "research_area": self._clean_str(field_data.get("research_area", "")),
                    "recent_publications": self._clean_str(field_data.get("recent_publications", "")),
                    "h_index": self._clean_int(field_data.get("h_index")),
                    "citations": self._clean_int(field_data.get("citations")),
                    "funding_status": self._clean_str(field_data.get("funding_status", "")),
                    "pipeline_status": "pending",
                    "priority": self._map_priority(self._clean_str(field_data.get("priority", "medium"))),
                    "first_contact_date": self._clean_date(field_data.get("first_contact_date")),
                    "last_contact_date": self._clean_date(field_data.get("last_contact_date")),
                    "follow_up_1_date": self._clean_date(field_data.get("follow_up_1_date")),
                    "follow_up_2_date": self._clean_date(field_data.get("follow_up_2_date")),
                    "response_date": self._clean_date(field_data.get("response_date")),
                    "meeting_scheduled": self._clean_str(field_data.get("meeting_scheduled", "")),
                    "application_submitted": self._clean_str(field_data.get("application_submitted", "")),
                    "deadline": self._clean_date(field_data.get("deadline")),
                    "llm_research_summary": self._clean_str(field_data.get("llm_research_summary", "")),
                    "llm_alignment_hook": self._clean_str(field_data.get("llm_alignment_hook", "")),
                    "llm_draft_email": self._clean_str(field_data.get("llm_draft_email", "")),
                    "notes": self._clean_str(field_data.get("notes", "")),
                    "sheet_row_index": sheet_row_num,
                }

                professor = None
                if email:
                    professor = Professor.objects.filter(email__iexact=email).first()
                if not professor and name and university:
                    professor = Professor.objects.filter(
                        name__iexact=name, university__iexact=university
                    ).first()

                if professor:
                    for k, v in model_attrs.items():
                        setattr(professor, k, v)
                    professor.save()
                else:
                    professor = Professor.objects.create(**model_attrs)

                saved_professors.append(professor)

        logger.info(
            f"fetch_pending: Successfully imported/synced {len(saved_professors)} pending professors."
        )
        return saved_professors

    # =========================================================================
    # 2) push_updates()
    # =========================================================================
    def push_updates(
        self,
        modified_since: Optional[datetime] = None,
        worksheet: Optional[gspread.Worksheet] = None,
    ) -> int:
        """
        Pushes status changes or LLM drafts back to the Google Sheet.
        Selects records where updated_at > last_synced_at (or updated_at >= modified_since).

        Uses pandas to match records against sheet columns and batch updates
        cells via gspread for optimal network performance.

        :param modified_since: Optional timestamp cutoff to filter updated records.
        :param worksheet: Optional worksheet override (for testing/mocking).
        :return: Number of professors pushed to the Google Sheet.
        """
        ws = worksheet or self.get_worksheet()

        query = Q(last_synced_at__isnull=True) | Q(updated_at__gt=F("last_synced_at"))
        if modified_since is not None:
            query = query & Q(updated_at__gte=modified_since)

        candidates = Professor.objects.filter(query)
        if not candidates.exists():
            logger.info("push_updates: No modified professors to push.")
            return 0

        headers = ws.row_values(1)
        if not headers:
            logger.warning("push_updates: Sheet has no header row.")
            return 0

        header_indices = {h.strip(): idx + 1 for idx, h in enumerate(headers)}
        sheet_records = ws.get_all_records()
        sheet_df = pd.DataFrame(sheet_records) if sheet_records else pd.DataFrame(columns=headers)

        cells_to_update: List[gspread.Cell] = []
        rows_to_append: List[List[Any]] = []
        synced_professors: List[Professor] = []
        now = timezone.now()

        for prof in candidates:
            target_row = prof.sheet_row_index

            if not target_row or target_row > len(sheet_df) + 1:
                match_idx = None
                if prof.email:
                    email_cols = [
                        c for c in sheet_df.columns if "email" in str(c).lower()
                    ]
                    for ec in email_cols:
                        matches = sheet_df[sheet_df[ec].astype(str).str.strip().str.lower() == prof.email.lower()]
                        if not matches.empty:
                            match_idx = matches.index[0]
                            break

                if match_idx is None and prof.name:
                    name_cols = [c for c in sheet_df.columns if "name" in str(c).lower()]
                    for nc in name_cols:
                        matches = sheet_df[sheet_df[nc].astype(str).str.strip().str.lower() == prof.name.lower()]
                        if not matches.empty:
                            match_idx = matches.index[0]
                            break

                if match_idx is not None:
                    target_row = int(match_idx) + 2
                    prof.sheet_row_index = target_row

            row_updates: Dict[str, Any] = {
                self.FIELD_TO_SHEET_COLUMN["pipeline_status"]: prof.get_pipeline_status_display(),
                self.FIELD_TO_SHEET_COLUMN["priority"]: prof.get_priority_display(),
                self.FIELD_TO_SHEET_COLUMN["llm_research_summary"]: prof.llm_research_summary,
                self.FIELD_TO_SHEET_COLUMN["llm_alignment_hook"]: prof.llm_alignment_hook,
                self.FIELD_TO_SHEET_COLUMN["llm_draft_email"]: prof.llm_draft_email,
                self.FIELD_TO_SHEET_COLUMN["notes"]: prof.notes,
            }
            if prof.first_contact_date:
                row_updates[self.FIELD_TO_SHEET_COLUMN["first_contact_date"]] = str(prof.first_contact_date)
            if prof.last_contact_date:
                row_updates[self.FIELD_TO_SHEET_COLUMN["last_contact_date"]] = str(prof.last_contact_date)
            if prof.response_date:
                row_updates[self.FIELD_TO_SHEET_COLUMN["response_date"]] = str(prof.response_date)
            if prof.meeting_scheduled:
                row_updates[self.FIELD_TO_SHEET_COLUMN["meeting_scheduled"]] = prof.meeting_scheduled
            if prof.application_submitted:
                row_updates[self.FIELD_TO_SHEET_COLUMN["application_submitted"]] = prof.application_submitted

            if target_row and target_row <= len(sheet_df) + 1:
                for col_name, value in row_updates.items():
                    col_idx = header_indices.get(col_name)
                    if not col_idx:
                        for h, idx_val in header_indices.items():
                            if h.lower() == col_name.lower():
                                col_idx = idx_val
                                break
                    if col_idx:
                        cell_val = "" if value is None else str(value)
                        cells_to_update.append(
                            gspread.Cell(row=target_row, col=col_idx, value=cell_val)
                        )
            else:
                new_row: List[Any] = []
                for h in headers:
                    h_clean = h.strip()
                    field_name = self.COLUMN_MAPPING.get(h_clean)
                    val = getattr(prof, field_name, "") if field_name else ""
                    if isinstance(val, (date, datetime)):
                        val = str(val)
                    elif val is None:
                        val = ""
                    new_row.append(str(val))
                rows_to_append.append(new_row)
                target_row = len(sheet_df) + 2 + len(rows_to_append) - 1
                prof.sheet_row_index = target_row

            prof.last_synced_at = now
            synced_professors.append(prof)

        if cells_to_update:
            ws.update_cells(cells_to_update)

        if rows_to_append:
            ws.append_rows(rows_to_append)

        Professor.objects.bulk_update(
            synced_professors, ["last_synced_at", "sheet_row_index"]
        )

        logger.info(f"push_updates: Pushed updates for {len(synced_professors)} professors.")
        return len(synced_professors)
