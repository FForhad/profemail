import logging
import os
import time
from pathlib import Path
from typing import Set

from django.conf import settings
from django.core.management.base import BaseCommand

from core.email_utils import (
    build_outreach_email,
    collect_sheet_candidates,
    load_attachments,
    load_signatures,
    open_outreach_worksheet,
    resolve_sheet_columns,
)
from core.gmail_service import (
    GmailAuthError,
    create_gmail_draft,
    get_authenticated_email,
    get_gmail_service,
    list_existing_draft_keys,
    normalize_draft_key,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Create identical outreach drafts (with HTML signature and attachments) directly "
        "in your Gmail Drafts folder via the Gmail API so they appear in the Gmail app."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--auth-only",
            action="store_true",
            default=False,
            help="Authenticate with Gmail API, verify your Gmail address, and exit.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Preview drafts that would be created without calling Gmail API.",
        )
        parser.add_argument(
            "--sheet",
            type=str,
            default=None,
            help="Google Sheet ID or URL (overrides .env).",
        )
        parser.add_argument(
            "--worksheet",
            type=str,
            default=None,
            help="Worksheet name (default: GOOGLE_SHEET_NAME or 'Professors List').",
        )
        parser.add_argument(
            "--status",
            type=str,
            default="Needs Review",
            help="Comma-separated row status filter (default: 'Needs Review'; e.g. 'Approved', 'Needs Review,Approved', or 'all').",
        )
        parser.add_argument(
            "--country",
            type=str,
            default=None,
            help="Optional country filter (e.g. 'USA', 'Germany').",
        )
        parser.add_argument(
            "--row",
            type=int,
            default=None,
            help="Target a specific sheet row number (e.g. --row 15).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of Gmail drafts to create in this run.",
        )
        parser.add_argument(
            "--attachments-dir",
            type=str,
            default="attachments",
            help="Directory containing resume and transcripts (default: attachments).",
        )
        parser.add_argument(
            "--signature-file",
            type=str,
            default="signature.txt",
            help="Path to custom email signature text file (default: signature.txt).",
        )
        parser.add_argument(
            "--gmail-credentials",
            type=str,
            default=None,
            help="Path to OAuth 2.0 client JSON (default: GMAIL_CREDENTIALS_FILE or gmail_credentials.json).",
        )
        parser.add_argument(
            "--token-file",
            type=str,
            default=None,
            help="Path to cached Gmail OAuth token JSON (default: GMAIL_TOKEN_FILE or token.json).",
        )
        parser.add_argument(
            "--allow-duplicates",
            action="store_true",
            default=False,
            help="Create a new Gmail draft even if a draft with the same To and Subject already exists.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.5,
            help="Delay in seconds between Gmail API draft creations (default: 0.5s).",
        )
        parser.add_argument(
            "--no-browser",
            action="store_true",
            default=False,
            help="Print the OAuth authorization URL instead of opening a browser automatically.",
        )

    def handle(self, *args, **options):
        auth_only = options["auth_only"]
        dry_run = options["dry_run"]
        allow_duplicates = options["allow_duplicates"]
        no_browser = options["no_browser"]
        limit = options["limit"]
        target_row = options["row"]
        country_filter = options["country"]
        delay_seconds = max(0.0, float(options["delay"]))

        gmail_creds_path = Path(
            options["gmail_credentials"]
            or getattr(settings, "GMAIL_CREDENTIALS_FILE", None)
            or os.getenv("GMAIL_CREDENTIALS_FILE", "gmail_credentials.json")
        )
        token_path = Path(
            options["token_file"]
            or getattr(settings, "GMAIL_TOKEN_FILE", None)
            or os.getenv("GMAIL_TOKEN_FILE", "token.json")
        )

        self.stdout.write(self.style.MIGRATE_HEADING("=== Gmail API Draft Creator ==="))
        if dry_run:
            self.stdout.write(self.style.WARNING(">>> RUNNING IN DRY-RUN MODE (No Gmail drafts will be created) <<<\n"))

        # 1. Authenticate Gmail API when needed (--auth-only or real draft creation)
        service = None
        authenticated_email = ""
        if auth_only or not dry_run:
            try:
                service = get_gmail_service(
                    creds_path=gmail_creds_path,
                    token_path=token_path,
                    no_browser=no_browser,
                )
                authenticated_email = get_authenticated_email(service)
                self.stdout.write(
                    self.style.SUCCESS(f"Authenticated Gmail account: {authenticated_email}")
                )
            except GmailAuthError as exc:
                self.stderr.write(self.style.ERROR(str(exc)))
                return
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"Gmail API authentication failed: {exc}"))
                logger.exception("Gmail API authentication failed")
                return

            if auth_only:
                self.stdout.write(self.style.SUCCESS(f"Token cached at '{token_path}'. Ready to create drafts."))
                return

        # 2. Load Attachments & Signatures (identical to send_approved)
        attachments_dir_path = Path(options["attachments_dir"])
        signature_path = Path(options["signature_file"])

        attachments = load_attachments(attachments_dir_path)
        if not attachments:
            self.stdout.write(
                self.style.WARNING(
                    f"Warning: No files found in '{attachments_dir_path}'. Drafts will be created without attachments."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"Found {len(attachments)} attachment(s):"))
            for att in attachments:
                self.stdout.write(f"  • {att.name} ({att.stat().st_size / 1024:.1f} KB)")
            self.stdout.write("")

        signature_text, signature_html = load_signatures(signature_path)
        if signature_text:
            self.stdout.write(self.style.SUCCESS(f"Loaded text signature from '{signature_path}'."))
        if signature_html:
            self.stdout.write(self.style.SUCCESS(f"Loaded HTML signature from '{signature_path.with_suffix('.html')}'.\n"))
        elif signature_text:
            self.stdout.write("")

        # 3. Read Google Sheet Candidates
        sheet_creds_path = getattr(settings, "GOOGLE_SHEETS_CREDENTIALS_PATH", "credentials.json")
        sheet_url = options["sheet"] or getattr(settings, "GOOGLE_SHEET_URL", None) or os.getenv("GOOGLE_SHEET_URL", "")
        ws_name = options["worksheet"] or os.getenv("GOOGLE_SHEET_NAME", "Professors List")

        if not os.path.exists(sheet_creds_path):
            self.stderr.write(self.style.ERROR(f"Google Sheets credentials file '{sheet_creds_path}' not found."))
            return
        if not sheet_url:
            self.stderr.write(self.style.ERROR("GOOGLE_SHEET_URL is not configured in .env or --sheet."))
            return

        ws = open_outreach_worksheet(sheet_creds_path, sheet_url, ws_name)
        header_values = ws.row_values(1)
        col_map = resolve_sheet_columns(header_values)

        if col_map["status"] == -1 or col_map["email"] == -1 or col_map["draft"] == -1:
            self.stderr.write(
                self.style.ERROR(
                    f"Google Sheet is missing required columns (Status, Email, Draft). Found: {header_values}"
                )
            )
            return

        target_statuses: Set[str] = {
            s.strip().lower() for s in options["status"].split(",") if s.strip()
        }
        all_values = ws.get_all_values()
        candidates = collect_sheet_candidates(
            all_values=all_values,
            col_map=col_map,
            target_statuses=target_statuses,
            target_row=target_row,
            country_filter=country_filter,
        )

        if not candidates:
            self.stdout.write(
                self.style.NOTICE(
                    f"No rows found matching status '{options['status']}'"
                    + (f" and country '{country_filter}'" if country_filter else "")
                    + "."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"Found {len(candidates)} candidate(s) matching status '{options['status']}':")
        )
        for c in candidates:
            self.stdout.write(
                f"  • [Row {c['row_num']}] {c['name']} ({c['university']}, {c['country']}) -> {c['email']}"
            )
        self.stdout.write("")

        if limit and limit > 0:
            candidates = candidates[:limit]
            self.stdout.write(self.style.NOTICE(f"Limiting execution to first {len(candidates)} candidate(s).\n"))

        # 4. Determine From header & existing Gmail drafts for duplicate protection
        configured_from = getattr(settings, "DEFAULT_FROM_EMAIL", "") or os.getenv("DEFAULT_FROM_EMAIL", "")
        if configured_from and "@" in configured_from:
            from_email = configured_from
        elif authenticated_email:
            candidate_name = getattr(settings, "CANDIDATE_PROFILE", {}).get("name", "Forhad Uddin Ahmed")
            from_email = f"{candidate_name} <{authenticated_email}>"
        else:
            from_email = "me"

        existing_keys = set()
        if not dry_run and not allow_duplicates and service is not None:
            try:
                existing_keys = list_existing_draft_keys(service)
                if existing_keys:
                    self.stdout.write(
                        self.style.NOTICE(f"Found {len(existing_keys)} existing draft(s) in Gmail (duplicate check enabled).\n")
                    )
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(f"Could not inspect existing Gmail drafts for deduplication: {exc}\n")
                )

        # 5. Create Drafts
        created_count = 0
        skipped_count = 0

        for idx, item in enumerate(candidates):
            row_num = item["row_num"]
            name = item["name"]
            to_email = item["email"]
            subject = item["subject"]
            draft = item["draft"]

            if not to_email or "@" not in to_email:
                self.stdout.write(self.style.ERROR(f"Row {row_num} [{name}]: Invalid or missing email '{to_email}'. Skipping."))
                skipped_count += 1
                continue

            if not draft:
                self.stdout.write(self.style.ERROR(f"Row {row_num} [{name}]: Email draft is blank. Skipping."))
                skipped_count += 1
                continue

            draft_key = normalize_draft_key(to_email, subject)
            if not allow_duplicates and draft_key in existing_keys:
                self.stdout.write(
                    self.style.WARNING(
                        f"Row {row_num} [{name}]: Draft already exists in Gmail for {to_email} ({subject}). Skipping."
                    )
                )
                skipped_count += 1
                continue

            msg = build_outreach_email(
                subject=subject,
                draft=draft,
                to_email=to_email,
                from_email=from_email,
                signature_text=signature_text,
                signature_html=signature_html,
                attachments=attachments,
            )

            self.stdout.write(
                self.style.MIGRATE_LABEL(
                    f"--- [{idx + 1}/{len(candidates)}] Row {row_num}: {name} ({item['university']}, {item['country']}) ---"
                )
            )
            self.stdout.write(f"To: {to_email}")
            self.stdout.write(f"Subject: {subject}")
            self.stdout.write(f"Attachments: {len(attachments)} | HTML signature: {'yes' if signature_html else 'no'}")

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f"[DRY-RUN] Would create Gmail draft for {to_email}.\n")
                )
                created_count += 1
                continue

            try:
                resp = create_gmail_draft(service=service, msg=msg)
                draft_id = resp.get("id", "unknown")
                existing_keys.add(draft_key)
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Saved Gmail draft (id={draft_id}) for {to_email}.\n")
                )
                if idx < len(candidates) - 1 and delay_seconds > 0:
                    time.sleep(delay_seconds)
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"Failed to create Gmail draft for Row {row_num} [{name}]: {exc}\n"))
                logger.exception("Gmail draft creation failed for row %s", row_num)

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Finished: Created {created_count} draft(s), skipped {skipped_count}."
            )
        )
