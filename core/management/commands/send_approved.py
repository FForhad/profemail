import os
import re
import sys
import time
import logging
from datetime import date
from pathlib import Path
from typing import Dict, Any, List, Optional

import gspread
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Cold Outreach Dispatcher: Finds professors in Google Sheet marked as 'Approved', "
        "appends custom signature, attaches documents from attachments/ folder, "
        "sends email via configured SMTP (Gmail), and updates sheet status to 'Applied'."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Simulate sending without dispatching emails or updating Google Sheet.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of approved emails to send in this run (default: all approved).",
        )
        parser.add_argument(
            "--row",
            type=int,
            default=None,
            help="Target a specific sheet row number (e.g. --row 15).",
        )
        parser.add_argument(
            "--delay",
            type=int,
            default=15,
            help="Delay in seconds between sending consecutive emails (default: 15s).",
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
            "--sheet",
            type=str,
            default=None,
            help="Google Sheet ID or URL (overrides .env).",
        )
        parser.add_argument(
            "--worksheet",
            type=str,
            default=None,
            help="Worksheet name (default: Professors List).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]
        target_row = options["row"]
        delay_seconds = options["delay"]
        attachments_dir_path = Path(options["attachments_dir"])
        signature_path = Path(options["signature_file"])

        self.stdout.write(self.style.MIGRATE_HEADING("=== Cold Outreach Email Dispatcher ==="))
        if dry_run:
            self.stdout.write(self.style.WARNING(">>> RUNNING IN DRY-RUN MODE (No emails will be sent) <<<\n"))

        # 1. Verify SMTP / Email Configuration
        email_user = getattr(settings, "EMAIL_HOST_USER", None) or os.getenv("EMAIL_HOST_USER", "")
        email_password = getattr(settings, "EMAIL_HOST_PASSWORD", None) or os.getenv("EMAIL_HOST_PASSWORD", "")
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or os.getenv("DEFAULT_FROM_EMAIL", email_user)

        if not dry_run and (not email_user or not email_password):
            self.stderr.write(
                self.style.ERROR(
                    "Error: EMAIL_HOST_USER or EMAIL_HOST_PASSWORD is not set in .env!\n"
                    "Please set your Gmail address and 16-character App Password in .env before sending."
                )
            )
            return

        # 2. Check Attachments
        attachments: List[Path] = []
        if attachments_dir_path.exists() and attachments_dir_path.is_dir():
            attachments = [f for f in attachments_dir_path.iterdir() if f.is_file() and not f.name.startswith(".")]
            attachments.sort(key=lambda p: p.name)

        if not attachments:
            self.stdout.write(
                self.style.WARNING(
                    f"Warning: No files found in '{attachments_dir_path}'. Emails will be sent without attachments."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"Found {len(attachments)} attachment(s):"))
            for att in attachments:
                size_kb = att.stat().st_size / 1024
                self.stdout.write(f"  • {att.name} ({size_kb:.1f} KB)")
            self.stdout.write("")

        # 3. Load Signature
        signature_text = ""
        if signature_path.exists():
            signature_text = signature_path.read_text(encoding="utf-8").strip()
            self.stdout.write(self.style.SUCCESS(f"Loaded text signature from '{signature_path}'."))

        html_sig_path = signature_path.with_suffix(".html")
        signature_html = ""
        if html_sig_path.exists():
            signature_html = html_sig_path.read_text(encoding="utf-8").strip()
            self.stdout.write(self.style.SUCCESS(f"Loaded HTML signature from '{html_sig_path}'.\n"))
        else:
            self.stdout.write("")

        # 4. Authenticate Google Sheet
        creds_path = getattr(settings, "GOOGLE_SHEETS_CREDENTIALS_PATH", "credentials.json")
        sheet_url = options["sheet"] or getattr(settings, "GOOGLE_SHEET_URL", None) or os.getenv("GOOGLE_SHEET_URL", "")
        ws_name = options["worksheet"] or os.getenv("GOOGLE_SHEET_NAME", "Professors List")

        if not os.path.exists(creds_path):
            self.stderr.write(self.style.ERROR(f"Credentials file '{creds_path}' not found."))
            return

        gc = gspread.service_account(filename=creds_path)
        sh = gc.open_by_url(sheet_url)
        ws = sh.worksheet(ws_name)

        # 5. Read headers and data
        header_values = ws.row_values(1)
        header_map = {col.strip(): idx for idx, col in enumerate(header_values)}

        required_cols = ["Professor Name", "Pipeline Status", "Email Subject", "Professor Email", "Email Draft"]
        missing_cols = [c for c in required_cols if c not in header_map]
        if missing_cols:
            self.stderr.write(self.style.ERROR(f"Google Sheet is missing required columns: {missing_cols}"))
            return

        status_col_idx = header_map["Pipeline Status"]
        email_col_idx = header_map["Professor Email"]
        subject_col_idx = header_map["Email Subject"]
        draft_col_idx = header_map["Email Draft"]
        name_col_idx = header_map["Professor Name"]
        uni_col_idx = header_map.get("University", -1)
        first_contact_idx = header_map.get("First Contact Date", -1)
        last_contact_idx = header_map.get("Last Contact Date", -1)

        all_values = ws.get_all_values()
        data_rows = all_values[1:]  # Exclude header

        # 6. Find Approved Rows
        approved_candidates: List[Dict[str, Any]] = []
        for idx, row in enumerate(data_rows):
            sheet_row_num = idx + 2
            if target_row and sheet_row_num != target_row:
                continue

            status_val = row[status_col_idx].strip() if len(row) > status_col_idx else ""
            if status_val.lower() == "approved":
                prof_email = row[email_col_idx].strip() if len(row) > email_col_idx else ""
                prof_name = row[name_col_idx].strip() if len(row) > name_col_idx else ""
                subject = row[subject_col_idx].strip() if len(row) > subject_col_idx else ""
                draft = row[draft_col_idx].strip() if len(row) > draft_col_idx else ""
                uni = row[uni_col_idx].strip() if (uni_col_idx >= 0 and len(row) > uni_col_idx) else ""

                approved_candidates.append({
                    "row_num": sheet_row_num,
                    "name": prof_name,
                    "university": uni,
                    "email": prof_email,
                    "subject": subject,
                    "draft": draft,
                })

        if not approved_candidates:
            self.stdout.write(self.style.NOTICE("No professors found with Pipeline Status == 'Approved'."))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {len(approved_candidates)} professor(s) with status 'Approved':\n"))
        for c in approved_candidates:
            self.stdout.write(f"  [Row {c['row_num']}] {c['name']} ({c['university']}) -> {c['email']}")
        self.stdout.write("")

        if limit and limit > 0:
            approved_candidates = approved_candidates[:limit]
            self.stdout.write(self.style.NOTICE(f"Limiting execution to first {len(approved_candidates)} candidate(s).\n"))

        # 7. Process & Send Emails
        today_str = date.today().isoformat()
        sent_count = 0

        for i, candidate in enumerate(approved_candidates):
            row_num = candidate["row_num"]
            to_email = candidate["email"]
            subject = candidate["subject"]
            draft = candidate["draft"]
            name = candidate["name"]

            # Basic Email Validation
            if not to_email or "@" not in to_email:
                self.stdout.write(self.style.ERROR(f"Row {row_num} [{name}]: Invalid or missing email address '{to_email}'. Skipping."))
                continue

            if not subject:
                self.stdout.write(self.style.ERROR(f"Row {row_num} [{name}]: Email subject is blank. Skipping."))
                continue

            if not draft:
                self.stdout.write(self.style.ERROR(f"Row {row_num} [{name}]: Email draft is blank. Skipping."))
                continue

            # Assemble Body with Signature
            final_body = self._merge_signature(draft, signature_text)

            self.stdout.write(self.style.MIGRATE_LABEL(f"\n--- [{i+1}/{len(approved_candidates)}] Processing Row {row_num}: {name} ---"))
            self.stdout.write(f"To: {to_email}")
            self.stdout.write(f"Subject: {subject}")
            self.stdout.write(f"Body Preview:\n{final_body[:160]}...\n")

            if dry_run:
                self.stdout.write(self.style.WARNING(f"[DRY-RUN] Would send email to {to_email} and set Row {row_num} status to 'Applied'."))
                sent_count += 1
                continue

            # Real Sending
            try:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=final_body,
                    from_email=from_email,
                    to=[to_email],
                )

                # Attach HTML alternative if HTML signature is available
                if signature_html:
                    body_without_signoff = self._strip_signoff(draft)
                    paragraphs = [p.strip().replace("\n", "<br/>") for p in body_without_signoff.split("\n\n") if p.strip()]
                    html_paragraphs = "".join(
                        f"<p style='margin: 0 0 16px 0; font-family: Arial, Helvetica, sans-serif; font-size: 14px; line-height: 1.6; color: #222222;'>{p}</p>"
                        for p in paragraphs
                    )
                    full_html = f"<div dir='ltr'>{html_paragraphs}{signature_html}</div>"
                    msg.attach_alternative(full_html, "text/html")

                # Attach documents
                for att in attachments:
                    msg.attach_file(str(att))

                msg.send(fail_silently=False)
                self.stdout.write(self.style.SUCCESS(f" Successfully sent email to {to_email}"))

                # Update Google Sheet: Status -> Applied, Dates -> today
                # 1-based column coordinates: col_idx + 1
                cells_to_update = [
                    gspread.Cell(row_num, status_col_idx + 1, "Applied")
                ]
                if first_contact_idx >= 0:
                    cells_to_update.append(gspread.Cell(row_num, first_contact_idx + 1, today_str))
                if last_contact_idx >= 0:
                    cells_to_update.append(gspread.Cell(row_num, last_contact_idx + 1, today_str))

                ws.update_cells(cells_to_update, value_input_option="USER_ENTERED")
                self.stdout.write(self.style.SUCCESS(f" Google Sheet Row {row_num} updated -> 'Applied' (Contact Date: {today_str})"))

                sent_count += 1

                # Polite delay between sends (skip delay on last item)
                if i < len(approved_candidates) - 1 and delay_seconds > 0:
                    self.stdout.write(self.style.NOTICE(f"Sleeping {delay_seconds}s before next send to respect rate limits..."))
                    time.sleep(delay_seconds)

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Failed to send email for Row {row_num} [{name}]: {e}"))
                logger.exception("Email dispatch failed for row %s", row_num)

        self.stdout.write(self.style.MIGRATE_HEADING(f"\nFinished: Processed {sent_count}/{len(approved_candidates)} emails successfully."))

    def _strip_signoff(self, draft: str) -> str:
        """
        Strips trailing sign-off lines from the draft body before attaching HTML signature.
        """
        sign_off_patterns = [
            r"Sincerely,\s*Forhad Uddin Ahmed",
            r"Best regards,\s*Forhad Uddin Ahmed",
            r"Warm regards,\s*Forhad Uddin Ahmed",
            r"Regards,\s*Forhad Uddin Ahmed",
            r"Sincerely,",
            r"Best regards,",
        ]
        for pat in sign_off_patterns:
            match = re.search(pat, draft, re.IGNORECASE)
            if match:
                return draft[:match.start()].rstrip()
        return draft.rstrip()

    def _merge_signature(self, draft: str, signature: str) -> str:
        """
        Cleanly blends custom signature into the drafted email without duplicating sign-off phrases.
        """
        if not signature:
            return draft

        # Check if draft already has a common sign-off
        sign_off_patterns = [
            r"Sincerely,\s*Forhad Uddin Ahmed",
            r"Best regards,\s*Forhad Uddin Ahmed",
            r"Warm regards,\s*Forhad Uddin Ahmed",
            r"Regards,\s*Forhad Uddin Ahmed",
            r"Sincerely,",
            r"Best regards,",
        ]

        # If the custom signature starts with 'Sincerely' or 'Best regards', replace draft sign-off
        sig_starts_with_signoff = any(signature.lower().startswith(p) for p in ["sincerely", "best regards", "regards", "warm regards"])

        for pat in sign_off_patterns:
            match = re.search(pat, draft, re.IGNORECASE)
            if match:
                if sig_starts_with_signoff:
                    # Replace sign-off onwards with signature
                    return draft[:match.start()].rstrip() + "\n\n" + signature
                else:
                    # Append signature after sign-off
                    return draft[:match.end()].rstrip() + "\n" + signature

        # Fallback: Just append signature
        return draft.rstrip() + "\n\n" + signature
