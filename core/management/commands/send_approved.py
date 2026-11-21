import os
import re
import sys
import time
import logging
from datetime import datetime, date, time as dtime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from zoneinfo import ZoneInfo

import gspread
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

# Canonical Country & Region Timezone Mappings
COUNTRY_TIMEZONES: Dict[str, str] = {
    "usa": "America/New_York",
    "united states": "America/New_York",
    "us": "America/New_York",
    "canada": "America/Toronto",
    "germany": "Europe/Berlin",
    "finland": "Europe/Helsinki",
    "sweden": "Europe/Stockholm",
    "uk": "Europe/London",
    "united kingdom": "Europe/London",
    "netherlands": "Europe/Amsterdam",
    "denmark": "Europe/Copenhagen",
    "norway": "Europe/Oslo",
    "switzerland": "Europe/Zurich",
    "australia": "Australia/Melbourne",
    "japan": "Asia/Tokyo",
    "south korea": "Asia/Seoul",
    "korea": "Asia/Seoul",
    "malaysia": "Asia/Kuala_Lumpur",
    "uae": "Asia/Dubai",
    "united arab emirates": "Asia/Dubai",
    "saudi arabia": "Asia/Riyadh",
    "saudi": "Asia/Riyadh",
    "china": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "singapore": "Asia/Singapore",
}

# University / Institutional Overrides for Specific Regional Timezones
UNIV_TIMEZONE_OVERRIDES: Dict[str, str] = {
    "calgary": "America/Edmonton",
    "alberta": "America/Edmonton",
    "british columbia": "America/Vancouver",
    "simon fraser": "America/Vancouver",
    "ubc": "America/Vancouver",
    "sfu": "America/Vancouver",
    "victoria": "America/Vancouver",
    "berkeley": "America/Los_Angeles",
    "stanford": "America/Los_Angeles",
    "washington": "America/Los_Angeles",
    "ucla": "America/Los_Angeles",
    "ucsd": "America/Los_Angeles",
    "usc": "America/Los_Angeles",
    "uiuc": "America/Chicago",
    "illinois": "America/Chicago",
    "texas": "America/Chicago",
    "austin": "America/Chicago",
    "wisconsin": "America/Chicago",
    "madison": "America/Chicago",
    "northwestern": "America/Chicago",
    "purdue": "America/Indiana/Indianapolis",
    "michigan": "America/Detroit",
    "waterloo": "America/Toronto",
    "toronto": "America/Toronto",
    "mcgill": "America/Montreal",
    "concordia": "America/Montreal",
}

# Standard Abbreviation Mappings
TZ_ABBR_MAP: Dict[str, str] = {
    "est": "America/New_York",
    "edt": "America/New_York",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "mst": "America/Edmonton",
    "mdt": "America/Edmonton",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "cet": "Europe/Berlin",
    "cest": "Europe/Berlin",
    "eet": "Europe/Helsinki",
    "eest": "Europe/Helsinki",
    "gmt": "Europe/London",
    "bst": "Europe/London",
    "jst": "Asia/Tokyo",
    "kst": "Asia/Seoul",
    "myt": "Asia/Kuala_Lumpur",
    "gst": "Asia/Dubai",
    "ast": "Asia/Riyadh",
    "aest": "Australia/Melbourne",
    "aedt": "Australia/Melbourne",
}


class Command(BaseCommand):
    help = (
        "Cold Outreach Dispatcher: Finds professors marked as 'Approved', "
        "calculates university local starting time (8:30 AM) with 2-minute staggering per region, "
        "appends custom signature, attaches documents, and sends via Gmail SMTP."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Simulate sending without dispatching emails or updating Google Sheet.",
        )
        parser.add_argument(
            "--schedule",
            action="store_true",
            default=False,
            help="Schedule and automatically dispatch emails matching university local starting times with 2-minute staggering.",
        )
        parser.add_argument(
            "--schedule-plan",
            action="store_true",
            default=False,
            help="Preview the calculated university-local send timetable without sending.",
        )
        parser.add_argument(
            "--start-time",
            type=str,
            default="08:30",
            help="Target university local workday start time in HH:MM format (default: 08:30).",
        )
        parser.add_argument(
            "--gap-minutes",
            type=int,
            default=2,
            help="Stagger interval in minutes between consecutive emails in the same region (default: 2 minutes).",
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
            help="Delay in seconds between sending consecutive emails when not using --schedule (default: 15s).",
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
            "--status",
            type=str,
            default="Approved",
            help="Filter by row status (default: 'Approved', or specify 'Needs Review', 'all').",
        )
        parser.add_argument(
            "--worksheet",
            type=str,
            default=None,
            help="Worksheet name (default: Professors List).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        do_schedule = options["schedule"]
        schedule_plan_only = options["schedule_plan"]
        target_start_time = options["start_time"]
        gap_minutes = options["gap_minutes"]
        limit = options["limit"]
        target_row = options["row"]
        delay_seconds = options["delay"]
        target_status = options.get("status", "Approved").strip().lower()
        attachments_dir_path = Path(options["attachments_dir"])
        signature_path = Path(options["signature_file"])

        self.stdout.write(self.style.MIGRATE_HEADING("=== Cold Outreach Email Dispatcher & Scheduler ==="))
        if dry_run:
            self.stdout.write(self.style.WARNING(">>> RUNNING IN DRY-RUN MODE (No emails will be sent) <<<\n"))

        if not dry_run and not schedule_plan_only and target_status != "approved":
            self.stderr.write(
                self.style.ERROR(
                    f"Safety guard: Real email dispatch is restricted to rows with status 'Approved'. "
                    f"You specified --status '{options.get('status')}'. "
                    f"Use --dry-run or --schedule-plan to preview or simulate other statuses."
                )
            )
            return

        # 1. Verify SMTP / Email Configuration
        email_user = getattr(settings, "EMAIL_HOST_USER", None) or os.getenv("EMAIL_HOST_USER", "")
        email_password = getattr(settings, "EMAIL_HOST_PASSWORD", None) or os.getenv("EMAIL_HOST_PASSWORD", "")
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or os.getenv("DEFAULT_FROM_EMAIL", email_user)

        if not dry_run and not schedule_plan_only and (not email_user or not email_password):
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
        try:
            ws = sh.worksheet(ws_name)
        except Exception:
            ws = sh.get_worksheet(0)

        # 5. Read headers and build flexible index map
        header_values = ws.row_values(1)
        header_map = {col.strip(): idx for idx, col in enumerate(header_values)}

        def find_col_idx(candidates: List[str]) -> int:
            for c in candidates:
                for name, idx in header_map.items():
                    if name.lower().strip() == c.lower().strip():
                        return idx
            return -1

        status_col_idx = find_col_idx(["Pipeline Status", "Status", "Pipeline"])
        email_col_idx = find_col_idx(["Professor Email", "Email", "Contact Email"])
        name_col_idx = find_col_idx(["Professor Name", "Name"])
        draft_col_idx = find_col_idx(["Email Draft", "Draft Email", "LLM Draft Email", "Draft"])
        subject_col_idx = find_col_idx(["Email Subject", "Subject"])
        uni_col_idx = find_col_idx(["University", "Institution"])
        country_col_idx = find_col_idx(["Country", "Location", "Nation"])
        tz_col_idx = find_col_idx(["Target Timezone", "Timezone", "TZ"])
        first_contact_idx = find_col_idx(["First Contact Date", "Contact Date"])
        last_contact_idx = find_col_idx(["Last Contact Date"])

        if status_col_idx == -1 or email_col_idx == -1 or draft_col_idx == -1:
            self.stderr.write(
                self.style.ERROR(
                    f"Google Sheet is missing required columns. Need Status, Email, and Draft. "
                    f"Found headers: {header_values}"
                )
            )
            return

        all_values = ws.get_all_values()
        data_rows = all_values[1:]  # Exclude header row

        # 6. Find Approved Rows (or Needs Review if specifically requested in SearchProf)
        approved_candidates: List[Dict[str, Any]] = []
        for idx, row in enumerate(data_rows):
            sheet_row_num = idx + 2
            if target_row and sheet_row_num != target_row:
                continue

            status_val = row[status_col_idx].strip() if len(row) > status_col_idx else ""
            if target_status == "all" or status_val.lower() == target_status:
                prof_email = row[email_col_idx].strip() if len(row) > email_col_idx else ""
                prof_name = row[name_col_idx].strip() if len(row) > name_col_idx else f"Row {sheet_row_num}"
                subject = row[subject_col_idx].strip() if (subject_col_idx >= 0 and len(row) > subject_col_idx) else ""
                draft = row[draft_col_idx].strip() if len(row) > draft_col_idx else ""
                uni = row[uni_col_idx].strip() if (uni_col_idx >= 0 and len(row) > uni_col_idx) else ""
                country = row[country_col_idx].strip() if (country_col_idx >= 0 and len(row) > country_col_idx) else ""
                tz_hint = row[tz_col_idx].strip() if (tz_col_idx >= 0 and len(row) > tz_col_idx) else ""

                # Auto-generate subject if missing, or extract from draft if prepended
                if not subject:
                    lines = [ln.strip() for ln in draft.splitlines() if ln.strip()]
                    if lines and lines[0].lower().startswith("subject:"):
                        subject = lines[0].split(":", 1)[1].strip()
                        # Clean draft body so "Subject: ..." is not in the email body
                        draft = "\n\n".join(lines[1:]).strip()
                    else:
                        is_usa = country.lower().strip() in ["usa", "us", "united states"]
                        degree_str = "PhD" if is_usa else "Master's"
                        subject = f"Exploring {degree_str} Research Opportunities – Forhad Uddin Ahmed"

                approved_candidates.append({
                    "row_num": sheet_row_num,
                    "name": prof_name,
                    "university": uni,
                    "country": country,
                    "tz_hint": tz_hint,
                    "email": prof_email,
                    "subject": subject,
                    "draft": draft,
                })

        if not approved_candidates:
            self.stdout.write(self.style.NOTICE(f"No professors found with Status == '{options.get('status', 'Approved')}'."))
            self.stdout.write(self.style.NOTICE("Tip: Review drafts and change status from 'Needs Review' to 'Approved' in your sheet to enable dispatch."))
            return

        status_display = options.get("status", "Approved")
        self.stdout.write(self.style.SUCCESS(f"Found {len(approved_candidates)} professor(s) matching status '{status_display}':\n"))
        for c in approved_candidates:
            self.stdout.write(f"  • [Row {c['row_num']}] {c['name']} ({c['university']}, {c['country']}) -> {c['email']}")
        self.stdout.write("")

        if limit and limit > 0:
            approved_candidates = approved_candidates[:limit]
            self.stdout.write(self.style.NOTICE(f"Limiting execution to first {len(approved_candidates)} candidate(s).\n"))

        # -------------------------------------------------------------
        # 7. Timezone Resolution & Schedule Calculation
        # -------------------------------------------------------------
        bd_tz = ZoneInfo("Asia/Dhaka")
        now_bd = datetime.now(bd_tz)
        region_counts: Dict[str, int] = {}

        scheduled_queue = []
        for c in approved_candidates:
            tz = self._resolve_timezone(c["university"], c["country"], c["tz_hint"])
            sched_local, sched_bd = self._calculate_scheduled_time(
                tz=tz,
                start_time_str=target_start_time,
                gap_minutes=gap_minutes,
                region_counts=region_counts,
            )
            time_until = sched_bd - now_bd
            hours_until = time_until.total_seconds() / 3600.0

            c_copy = dict(c)
            c_copy.update({
                "tz": tz,
                "sched_local": sched_local,
                "sched_bd": sched_bd,
                "hours_until": hours_until,
            })
            scheduled_queue.append(c_copy)

        # Chronological ordering by dispatch time
        scheduled_queue.sort(key=lambda x: x["sched_bd"])

        # Enforce minimum gap between consecutive emails in Bangladesh time:
        # If any email has the same BD time as a previous one (or less than gap_minutes),
        # automatically maintain a minimum gap between them.
        for k in range(1, len(scheduled_queue)):
            prev_bd = scheduled_queue[k - 1]["sched_bd"]
            curr_bd = scheduled_queue[k]["sched_bd"]
            min_bd = prev_bd + timedelta(minutes=gap_minutes)
            if curr_bd < min_bd:
                diff = min_bd - curr_bd
                scheduled_queue[k]["sched_bd"] = min_bd
                scheduled_queue[k]["sched_local"] = scheduled_queue[k]["sched_local"] + diff
                time_until = min_bd - now_bd
                scheduled_queue[k]["hours_until"] = time_until.total_seconds() / 3600.0

        # Display Schedule Timetable
        self.stdout.write(self.style.MIGRATE_HEADING("=== Calculated Dispatch Timetable ==="))
        self.stdout.write(f"Current Bangladesh Time: {now_bd.strftime('%A, %b %d %Y, %I:%M %p %Z')}\n")
        self.stdout.write(f"{'#':<3} {'Professor':<26} {'Country':<14} {'Local University Time':<24} {'BD Send Time':<22} {'In (Hours)':<10}")
        self.stdout.write("-" * 105)
        for idx, item in enumerate(scheduled_queue):
            loc_str = item["sched_local"].strftime("%a %b %d, %I:%M %p %Z")
            bd_str = item["sched_bd"].strftime("%a %b %d, %I:%M %p")
            hrs = item["hours_until"]
            p_name = item["name"][:24]
            c_name = item["country"][:12]
            self.stdout.write(f"{idx+1:<3} {p_name:<26} {c_name:<14} {loc_str:<24} {bd_str:<22} {hrs:>5.1f} hrs")
        self.stdout.write("-" * 105 + "\n")

        if schedule_plan_only:
            self.stdout.write(self.style.SUCCESS("Schedule plan preview complete. Pass --schedule to execute this dispatch."))
            return

        # -------------------------------------------------------------
        # 8. Execution Dispatcher Loop
        # -------------------------------------------------------------
        today_str = date.today().isoformat()
        sent_count = 0

        for i, item in enumerate(scheduled_queue):
            row_num = item["row_num"]
            to_email = item["email"]
            subject = item["subject"]
            draft = item["draft"]
            name = item["name"]
            sched_bd = item["sched_bd"]

            # Basic Validation
            if not to_email or "@" not in to_email:
                self.stdout.write(self.style.ERROR(f"Row {row_num} [{name}]: Invalid or missing email '{to_email}'. Skipping."))
                continue

            if not draft:
                self.stdout.write(self.style.ERROR(f"Row {row_num} [{name}]: Email draft is blank. Skipping."))
                continue

            final_body = self._merge_signature(draft, signature_text)

            self.stdout.write(self.style.MIGRATE_LABEL(f"\n--- [{i+1}/{len(scheduled_queue)}] Row {row_num}: {name} ({item['university']}, {item['country']}) ---"))
            self.stdout.write(f"To: {to_email}")
            self.stdout.write(f"Subject: {subject}")
            self.stdout.write(f"Scheduled Send Time: {item['sched_local'].strftime('%I:%M %p %Z')} ({sched_bd.strftime('%a %b %d, %I:%M %p BD Time')})")

            # If running in --schedule mode, wait until the scheduled timestamp arrives
            if do_schedule and not dry_run:
                now_check = datetime.now(bd_tz)
                wait_seconds = (sched_bd - now_check).total_seconds()
                if wait_seconds > 0:
                    wait_minutes = wait_seconds / 60.0
                    wait_hours = wait_seconds / 3600.0
                    self.stdout.write(
                        self.style.NOTICE(
                            f"Waiting {wait_hours:.2f} hours ({wait_minutes:.1f} mins) until scheduled window ({sched_bd.strftime('%I:%M %p BD')})..."
                        )
                    )
                    # Sleep in manageable intervals to allow monitoring
                    while wait_seconds > 0:
                        sleep_chunk = min(wait_seconds, 30.0)
                        time.sleep(sleep_chunk)
                        wait_seconds = (sched_bd - datetime.now(bd_tz)).total_seconds()

            if dry_run:
                self.stdout.write(self.style.WARNING(f"[DRY-RUN] Would send email to {to_email} and set Row {row_num} status to 'Applied'."))
                sent_count += 1
                continue

            # Real Sending via Django SMTP
            try:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=final_body,
                    from_email=from_email,
                    to=[to_email],
                )

                if signature_html:
                    body_without_signoff = self._strip_signoff(draft)
                    paragraphs = [p.strip().replace("\n", "<br/>") for p in body_without_signoff.split("\n\n") if p.strip()]
                    html_paragraphs = "".join(
                        f"<p style='margin: 0 0 16px 0; font-family: Arial, Helvetica, sans-serif; font-size: 14px; line-height: 1.6; color: #222222;'>{p}</p>"
                        for p in paragraphs
                    )
                    full_html = f"<div dir='ltr'>{html_paragraphs}{signature_html}</div>"
                    msg.attach_alternative(full_html, "text/html")

                for att in attachments:
                    msg.attach_file(str(att))

                msg.send(fail_silently=False)
                self.stdout.write(self.style.SUCCESS(f" Successfully sent email to {to_email}"))

                # Update Google Sheet: Status -> 'Applied'
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

                # Polite delay between consecutive immediate sends if not scheduling
                if not do_schedule and i < len(scheduled_queue) - 1 and delay_seconds > 0:
                    self.stdout.write(self.style.NOTICE(f"Sleeping {delay_seconds}s before next send..."))
                    time.sleep(delay_seconds)

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Failed to send email for Row {row_num} [{name}]: {e}"))
                logger.exception("Email dispatch failed for row %s", row_num)

        self.stdout.write(self.style.MIGRATE_HEADING(f"\nFinished: Processed {sent_count}/{len(scheduled_queue)} emails successfully."))

    def _resolve_timezone(self, univ: str, country: str, tz_hint: str) -> ZoneInfo:
        """Resolves canonical IANA ZoneInfo based on university, country, or sheet hint."""
        # Check explicit abbreviation hint
        if tz_hint:
            hint_clean = tz_hint.lower().strip()
            if hint_clean in TZ_ABBR_MAP:
                return ZoneInfo(TZ_ABBR_MAP[hint_clean])
            try:
                return ZoneInfo(tz_hint)
            except Exception:
                pass

        # Check university overrides
        u_lower = (univ or "").lower()
        for key, tz_name in UNIV_TIMEZONE_OVERRIDES.items():
            if key in u_lower:
                return ZoneInfo(tz_name)

        # Check country mapping
        c_lower = (country or "").lower().strip()
        tz_name = COUNTRY_TIMEZONES.get(c_lower, "UTC")
        return ZoneInfo(tz_name)

    def _calculate_scheduled_time(
        self,
        tz: ZoneInfo,
        start_time_str: str = "08:30",
        gap_minutes: int = 2,
        region_counts: Dict[str, int] = None,
    ) -> Tuple[datetime, datetime]:
        """Calculates next university workday start time (skipping weekends) with regional gap offset."""
        if region_counts is None:
            region_counts = {}

        now_local = datetime.now(tz)
        target_hour, target_min = map(int, start_time_str.split(":"))

        region_key = str(tz)
        offset_index = region_counts.get(region_key, 0)
        region_counts[region_key] = offset_index + 1

        # Check if local morning start time has already passed today
        target_today = datetime.combine(now_local.date(), dtime(target_hour, target_min), tzinfo=tz)
        if now_local >= target_today:
            target_date = now_local.date() + timedelta(days=1)
        else:
            target_date = now_local.date()

        # Skip weekends: 5 = Saturday, 6 = Sunday -> shift to Monday
        while target_date.weekday() in (5, 6):
            target_date += timedelta(days=1)

        sched_local = datetime.combine(target_date, dtime(target_hour, target_min), tzinfo=tz) + timedelta(minutes=offset_index * gap_minutes)

        bd_tz = ZoneInfo("Asia/Dhaka")
        sched_bd = sched_local.astimezone(bd_tz)
        return sched_local, sched_bd

    def _strip_signoff(self, draft: str) -> str:
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
        if not signature:
            return draft

        sign_off_patterns = [
            r"Sincerely,\s*Forhad Uddin Ahmed",
            r"Best regards,\s*Forhad Uddin Ahmed",
            r"Warm regards,\s*Forhad Uddin Ahmed",
            r"Regards,\s*Forhad Uddin Ahmed",
            r"Sincerely,",
            r"Best regards,",
        ]
        sig_starts_with_signoff = any(signature.lower().startswith(p) for p in ["sincerely", "best regards", "regards", "warm regards"])

        for pat in sign_off_patterns:
            match = re.search(pat, draft, re.IGNORECASE)
            if match:
                if sig_starts_with_signoff:
                    return draft[:match.start()].rstrip() + "\n\n" + signature
                else:
                    return draft[:match.end()].rstrip() + "\n" + signature

        return draft.rstrip() + "\n\n" + signature
