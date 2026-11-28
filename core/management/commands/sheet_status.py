import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set

import gspread
from django.conf import settings
from django.core.management.base import BaseCommand

from core.email_utils import resolve_sheet_columns

DATE_FORMATS = ("%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y")
HARD_LOCK_STATUSES = {"researching", "needs review", "approved"}
DEFAULT_WORKSHEETS = ("Professors List", "SearchProf")


def parse_contact_date(val: str) -> Optional[date]:
    """Parse common sheet contact date formats into a date object."""
    text = str(val or "").strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        from dateutil import parser

        return parser.parse(text).date()
    except Exception:
        return None


def _cell(row: List[str], idx: int) -> str:
    """Safely read and strip a 0-based cell from a sheet row."""
    if idx < 0 or idx >= len(row):
        return ""
    return str(row[idx]).strip()


def _country_matches(country_val: str, country_filter: Optional[str]) -> bool:
    """Match country filter with USA aliases consistent with draft_next."""
    if not country_filter:
        return True
    target = country_filter.strip().lower()
    val = country_val.strip().lower()
    if target in {"usa", "us", "united states"}:
        return val in {"usa", "us", "united states"}
    return target in val


def summarize_worksheet(
    all_values: List[List[str]],
    cooldown_days: int = 9,
    country_filter: Optional[str] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Compute status counts, country breakdown, active locks, and draft readiness."""
    ref_today = today or date.today()
    if not all_values:
        return {
            "total_rows": 0,
            "status_counts": {},
            "country_breakdown": {},
            "locked_groups": set(),
            "ready_groups_by_country": {},
            "ready_rows_by_country": {},
            "total_ready_groups": 0,
            "total_ready_rows": 0,
        }

    headers = all_values[0]
    col_map = resolve_sheet_columns(headers)
    status_idx = col_map["status"]
    country_idx = col_map["country"]
    group_idx = col_map["group"]
    name_idx = col_map["name"]
    first_date_idx = col_map["first_contact"]
    last_date_idx = col_map["last_contact"]

    data_rows = all_values[1:]

    # Compute locked groups across the entire worksheet first (mirrors draft_next locking).
    locked_groups: Set[str] = set()
    for row in data_rows:
        group = _cell(row, group_idx)
        if not group:
            continue
        norm_status = _cell(row, status_idx).lower().replace("_", " ")
        if norm_status in HARD_LOCK_STATUSES:
            locked_groups.add(group)
        elif norm_status == "applied":
            date_str = _cell(row, first_date_idx) or _cell(row, last_date_idx)
            c_date = parse_contact_date(date_str)
            if not c_date or (ref_today - c_date).days < cooldown_days:
                locked_groups.add(group)

    status_counts: Counter = Counter()
    country_breakdown: Dict[str, Counter] = defaultdict(Counter)
    ready_groups_by_country: Dict[str, Set[str]] = defaultdict(set)
    ready_rows_by_country: Counter = Counter()
    matched_rows = 0

    for row in data_rows:
        country = _cell(row, country_idx) or "(Blank)"
        if country_filter and not _country_matches(country, country_filter):
            continue

        matched_rows += 1
        raw_status = _cell(row, status_idx) or "(Blank)"
        norm_status = raw_status.lower().replace("_", " ")
        status_counts[raw_status] += 1
        country_breakdown[country][raw_status] += 1

        prof_name = _cell(row, name_idx)
        group = _cell(row, group_idx)
        if (
            norm_status == "pending"
            and prof_name
            and "@" not in prof_name
            and group not in locked_groups
        ):
            ready_rows_by_country[country] += 1
            ready_groups_by_country[country].add(group or f"__row_{matched_rows}")

    return {
        "total_rows": matched_rows,
        "status_counts": dict(status_counts),
        "country_breakdown": {c: dict(cnt) for c, cnt in sorted(country_breakdown.items())},
        "locked_groups": locked_groups,
        "ready_groups_by_country": {c: len(g) for c, g in sorted(ready_groups_by_country.items())},
        "ready_rows_by_country": dict(sorted(ready_rows_by_country.items())),
        "total_ready_groups": sum(len(g) for g in ready_groups_by_country.values()),
        "total_ready_rows": sum(ready_rows_by_country.values()),
    }


def _open_spreadsheet(creds_path: str, sheet_identifier: str):
    """Open a Google Spreadsheet by URL, key, or title."""
    gc = gspread.service_account(filename=creds_path)
    if sheet_identifier.startswith("http://") or sheet_identifier.startswith("https://"):
        return gc.open_by_url(sheet_identifier)
    try:
        return gc.open_by_key(sheet_identifier)
    except Exception:
        return gc.open(sheet_identifier)


class Command(BaseCommand):
    help = (
        "Inspect live Google Sheet outreach status across worksheets: row counts, "
        "country breakdown, active Contact Group locks, and professors ready to draft."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--sheet",
            type=str,
            default=None,
            help="Google Sheet ID, URL, or Title (overrides .env).",
        )
        parser.add_argument(
            "--worksheet",
            type=str,
            default=None,
            help="Single worksheet name to inspect (default: both 'Professors List' and 'SearchProf').",
        )
        parser.add_argument(
            "--credentials",
            type=str,
            default=None,
            help="Path to credentials.json (default: credentials.json).",
        )
        parser.add_argument(
            "--country",
            type=str,
            default=None,
            help="Optional country filter (e.g. USA, Germany).",
        )
        parser.add_argument(
            "--cooldown-days",
            type=int,
            default=9,
            help="Department cooldown window in days for 'Applied' locks (default: 9).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            default=False,
            help="Output summary as JSON.",
        )

    def handle(self, *args, **options):
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
            self.stderr.write(self.style.ERROR("No Google Sheet ID or URL provided."))
            return

        cooldown_days = int(options.get("cooldown_days", 9))
        country_filter = options.get("country")
        ws_opt = options.get("worksheet")
        as_json = bool(options.get("json"))

        try:
            spreadsheet = _open_spreadsheet(creds_path, sheet_identifier)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Failed to open Google Sheet: {exc}"))
            return

        target_names = [ws_opt] if ws_opt else list(DEFAULT_WORKSHEETS)
        available_titles = {ws.title: ws for ws in spreadsheet.worksheets()}

        results: Dict[str, Dict[str, Any]] = {}
        all_locked: Set[str] = set()

        for name in target_names:
            ws = available_titles.get(name)
            if ws is None:
                if ws_opt:
                    self.stderr.write(self.style.ERROR(f"Worksheet '{name}' not found."))
                    return
                continue
            summary = summarize_worksheet(
                ws.get_all_values(),
                cooldown_days=cooldown_days,
                country_filter=country_filter,
            )
            results[name] = summary
            all_locked.update(summary["locked_groups"])

        if as_json:
            payload = {
                "date": date.today().isoformat(),
                "cooldown_days": cooldown_days,
                "country_filter": country_filter,
                "total_unique_locked_groups": len(all_locked),
                "worksheets": {
                    name: {
                        **data,
                        "locked_groups_count": len(data["locked_groups"]),
                        "locked_groups": sorted(data["locked_groups"]),
                    }
                    for name, data in results.items()
                },
            }
            self.stdout.write(json.dumps(payload, indent=2))
            return

        self._print_report(results, all_locked, cooldown_days, country_filter)

    def _print_report(
        self,
        results: Dict[str, Dict[str, Any]],
        all_locked: Set[str],
        cooldown_days: int,
        country_filter: Optional[str],
    ) -> None:
        header_note = f" | Country: {country_filter}" if country_filter else ""
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"=== Google Sheet Outreach Status (Cooldown: {cooldown_days}d{header_note}) ==="
            )
        )

        for ws_name, data in results.items():
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{ws_name}] Total rows: {data['total_rows']} | "
                    f"Locked groups: {len(data['locked_groups'])} | "
                    f"Ready to draft: {data['total_ready_groups']} "
                    f"({data['total_ready_rows']} unlocked Pending)"
                )
            )
            status_str = ", ".join(
                f"{k}: {v}" for k, v in sorted(data["status_counts"].items())
            )
            self.stdout.write(f"  Statuses: {status_str or 'None'}")

            if data["country_breakdown"]:
                self.stdout.write(
                    f"  {'Country':<18} {'Total':>6} {'Applied':>8} {'Approved':>9} "
                    f"{'Review':>7} {'Pending':>8} {'Ready':>6} {'UnlkPend':>9}"
                )
                self.stdout.write("  " + "-" * 77)
                for country, counts in data["country_breakdown"].items():
                    total = sum(counts.values())
                    applied = counts.get("Applied", 0)
                    approved = counts.get("Approved", 0)
                    review = counts.get("Needs Review", 0)
                    pending = counts.get("Pending", 0)
                    ready = data["ready_groups_by_country"].get(country, 0)
                    unlk_pend = data["ready_rows_by_country"].get(country, 0)
                    self.stdout.write(
                        f"  {country:<18} {total:>6} {applied:>8} {approved:>9} "
                        f"{review:>7} {pending:>8} {ready:>6} {unlk_pend:>9}"
                    )

        if len(results) > 1:
            self.stdout.write("")
            self.stdout.write(
                self.style.NOTICE(
                    f"Total unique locked Contact Groups across sheets: {len(all_locked)}"
                )
            )
