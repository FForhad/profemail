from datetime import date, timedelta
from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone

from core.models import Professor
from core.services import GoogleSheetSyncService


class GoogleSheetSyncServiceTests(TestCase):
    def setUp(self):
        self.service = GoogleSheetSyncService(sheet_key_or_url="dummy_test_key")

    def test_fetch_pending_creates_records(self):
        """Test fetch_pending filters rows with Pipeline Status = 'Pending' and stores in DB."""
        mock_worksheet = MagicMock()
        mock_worksheet.get_all_records.return_value = [
            {
                "Professor Name": "Dr. Alice Smith",
                "University": "Stanford University",
                "Country": "USA",
                "Department/Lab": "AI Lab",
                "Contact Group": "AI / ML",
                "Professor Email": "alice@cs.stanford.edu",
                "Pipeline Status": "Pending",
                "Priority": "High",
                "Research Area": "Generative Models, Diffusion",
                "Professor Profile URL": "https://stanford.edu/~alice",
                "h-index": "42",
                "Citations": "8500",
            },
            {
                "Professor Name": "Dr. Bob Jones",
                "University": "MIT",
                "Country": "USA",
                "Department/Lab": "CSAIL",
                "Contact Group": "Robotics",
                "Professor Email": "bob@csail.mit.edu",
                "Pipeline Status": "Identified",
                "Priority": "Medium",
                "Research Area": "Autonomous Robotics",
                "Professor Profile URL": "https://mit.edu/~bob",
            },
        ]

        saved = self.service.fetch_pending(worksheet=mock_worksheet)

        self.assertEqual(len(saved), 1)
        prof = saved[0]
        self.assertEqual(prof.name, "Dr. Alice Smith")
        self.assertEqual(prof.university, "Stanford University")
        self.assertEqual(prof.pipeline_status, "pending")
        self.assertEqual(prof.priority, "high")
        self.assertEqual(prof.h_index, 42)
        self.assertEqual(prof.citations, 8500)
        self.assertEqual(prof.sheet_row_index, 2)

        # Ensure non-pending row was not saved
        self.assertFalse(Professor.objects.filter(email="bob@csail.mit.edu").exists())

    def test_push_updates_updates_modified_fields(self):
        """Test push_updates pushes updated status, notes, and LLM drafts to sheet."""
        # Create professor that was previously synced
        last_sync = timezone.now() - timedelta(hours=2)
        prof = Professor.objects.create(
            name="Dr. Alice Smith",
            university="Stanford University",
            email="alice@cs.stanford.edu",
            pipeline_status="email_drafted",
            priority="high",
            llm_draft_email="Dear Professor Alice, I am writing to express my strong interest...",
            llm_research_summary="Pioneering work in diffusion models.",
            notes="Follow up next Monday",
            sheet_row_index=2,
            last_synced_at=last_sync,
        )

        mock_worksheet = MagicMock()
        mock_worksheet.row_values.return_value = [
            "Professor Name",
            "University",
            "Professor Email",
            "Pipeline Status",
            "Priority",
            "LLM Draft Email",
            "LLM Research Summary",
            "Notes & Next Action",
        ]
        mock_worksheet.get_all_records.return_value = [
            {
                "Professor Name": "Dr. Alice Smith",
                "University": "Stanford University",
                "Professor Email": "alice@cs.stanford.edu",
                "Pipeline Status": "Pending",
                "Priority": "High",
                "LLM Draft Email": "",
                "LLM Research Summary": "",
                "Notes & Next Action": "",
            }
        ]

        count = self.service.push_updates(worksheet=mock_worksheet)

        self.assertEqual(count, 1)
        mock_worksheet.update_cells.assert_called_once()
        updated_cells = mock_worksheet.update_cells.call_args[0][0]
        cell_values = {c.col: c.value for c in updated_cells}

        # Verify pipeline status display value was pushed
        self.assertIn("Email Drafted", cell_values.values())
        self.assertIn(prof.llm_draft_email, cell_values.values())

        # Check that professor last_synced_at has updated
        prof.refresh_from_db()
        self.assertGreater(prof.last_synced_at, last_sync)


class ContactGroupLockingTests(TestCase):
    def setUp(self):
        # Create groups and professors
        # Group "NLP Lab"
        self.nlp_active = Professor.objects.create(
            name="Prof. Manning",
            university="Stanford",
            contact_group="NLP Lab",
            pipeline_status="researching",  # Active! Locks NLP Lab
            priority="high",
        )
        self.nlp_pending = Professor.objects.create(
            name="Prof. Jurafsky",
            university="Stanford",
            contact_group="NLP Lab",
            pipeline_status="pending",
            priority="high",
        )

        # Group "Systems Lab" - Currently unlocked
        self.sys_p1 = Professor.objects.create(
            name="Prof. Ousterhout",
            university="Stanford",
            contact_group="Systems Lab",
            pipeline_status="pending",
            priority="medium",
        )
        self.sys_p2 = Professor.objects.create(
            name="Prof. Lamport",
            university="Stanford",
            contact_group="Systems Lab",
            pipeline_status="pending",
            priority="low",
        )

        # Group "Robotics" - Currently unlocked, high priority
        self.robotics_p1 = Professor.objects.create(
            name="Prof. Thrun",
            university="Stanford",
            contact_group="Robotics",
            pipeline_status="pending",
            priority="high",
        )

    def test_group_locked_identification(self):
        """ContactGroupLockManager correctly identifies active locked groups."""
        from core.locking import ContactGroupLockManager

        self.assertTrue(ContactGroupLockManager.is_group_locked("NLP Lab"))
        self.assertFalse(ContactGroupLockManager.is_group_locked("Systems Lab"))
        self.assertFalse(ContactGroupLockManager.is_group_locked("Robotics"))

        locked_groups = ContactGroupLockManager.get_locked_contact_groups()
        self.assertIn("NLP Lab", locked_groups)
        self.assertNotIn("Systems Lab", locked_groups)

    def test_validation_prevents_multiple_active_professors_in_same_group(self):
        """Model validation prevents activating another professor in an already locked group."""
        from core.locking import ContactGroupLockedException

        # Attempting to activate prof in already locked group should fail
        self.nlp_pending.pipeline_status = "approved"
        with self.assertRaises(ContactGroupLockedException):
            self.nlp_pending.clean()

    def test_get_next_eligible_professors_filters_locked_groups_and_sorts_by_priority(self):
        """get_next_eligible_professors returns highest-priority pending professors in unlocked groups."""
        from core.locking import get_next_eligible_professors

        eligible = get_next_eligible_professors()

        # 1. nlp_pending must be excluded because 'NLP Lab' is locked by nlp_active
        eligible_ids = [p.id for p in eligible]
        self.assertNotIn(self.nlp_pending.id, eligible_ids)

        # 2. Priority check: Robotics (High) must come before Systems Lab (Medium)
        self.assertEqual(eligible[0].id, self.robotics_p1.id)
        self.assertEqual(eligible[1].id, self.sys_p1.id)

        # 3. Maximum ONE professor per contact group in the returned batch
        group_names = [p.contact_group for p in eligible]
        self.assertEqual(len(group_names), len(set(group_names)))
        self.assertNotIn(self.sys_p2.id, eligible_ids)  # sys_p1 was chosen for Systems Lab

    def test_unlocking_group_makes_pending_professors_eligible(self):
        """When an active professor moves out of active status (e.g. to accepted/declined/no_response), the group unlocks."""
        from core.locking import get_next_eligible_professors

        # Move active professor to accepted
        self.nlp_active.pipeline_status = "accepted"
        self.nlp_active.save()

        eligible = get_next_eligible_professors()
        eligible_names = [p.name for p in eligible]

        # Now Prof. Jurafsky (High priority in NLP Lab) is eligible and should be at the top!
        self.assertIn("Prof. Jurafsky", eligible_names)
        self.assertEqual(eligible[0].name, "Prof. Jurafsky")


class DiscoverProfsCommandTests(TestCase):
    def test_deobfuscate_emails(self):
        from core.management.commands.discover_profs import deobfuscate_emails

        txt = "Send CV to minghui[dot]cheng[at]miami[dot]edu or admin@phdfinder.com or jane(at)mit.edu."
        self.assertEqual(
            deobfuscate_emails(txt),
            ["minghui.cheng@miami.edu", "jane@mit.edu"],
        )

    def test_parse_linkedin_post_html_extracts_jsonld_and_age(self):
        from core.management.commands.discover_profs import parse_linkedin_post_html

        html = """
        <html><head>
        <meta property="og:title" content="Jane Doe | 10 likes | LinkedIn"/>
        <meta property="og:description" content="Recruiting a fully funded PhD student in Machine Learning for Fall 2027. Email jane.doe@stanford.edu."/>
        <script type="application/ld+json">
        {"@type": "SocialMediaPosting", "datePublished": "2026-11-21T10:00:00Z", "author": {"name": "Jane Doe"}}
        </script>
        </head><body></body></html>
        """
        parsed = parse_linkedin_post_html(html, "https://www.linkedin.com/posts/test", today=date(2026, 11, 24))
        self.assertEqual(parsed["author_name"], "Jane Doe")
        self.assertEqual(parsed["post_age_days"], 3)
        self.assertEqual(parsed["emails"], ["jane.doe@stanford.edu"])
        self.assertIn("Machine Learning", parsed["post_text"])

    def test_validate_and_format_candidate_skips_duplicates_and_locks(self):
        from unittest.mock import patch
        from core.management.commands.discover_profs import Command

        cmd = Command()
        cand = {
            "professor_name": "Prof. Jane Doe",
            "university": "Stanford University",
            "country": "USA",
            "department": "Computer Science",
            "email": "jane@stanford.edu",
            "post_age": 2,
            "post_text": "Recruiting PhD students in Machine Learning for Fall 2027.",
            "linkedin_url": "https://www.linkedin.com/posts/test",
            "funding": "Fully funded",
            "intake": "Fall 2027",
        }
        with patch.object(cmd, "_verify_recent_publications", return_value=("https://openalex.org/A1", ["2026: Paper"])):
            # Locked group skips
            row_locked = cmd._validate_and_format_candidate(
                cand, set(), set(), {"stan-compscie"}, None, False
            )
            self.assertIsNone(row_locked)

            # Duplicate email skips
            row_dup = cmd._validate_and_format_candidate(
                cand, set(), {"jane@stanford.edu"}, set(), None, False
            )
            self.assertIsNone(row_dup)

            # Clean unlocked candidate succeeds
            row_ok = cmd._validate_and_format_candidate(
                cand, set(), set(), set(), None, False
            )
            self.assertIsNotNone(row_ok)
            self.assertEqual(row_ok[9], "Pending")
            self.assertEqual(row_ok[7], "2")


class DraftNextContextTests(TestCase):
    def test_infer_intake_and_required_subject_and_salutation(self):
        from core.management.commands.draft_next import Command

        self.assertEqual(
            Command._infer_intake_from_context("Summer/Fall 2027.", "Start date is Summer or Fall 2027"),
            "Summer/Fall 2027",
        )
        self.assertEqual(
            Command._infer_intake_from_context("Fully funded PhD, Fall 2027.", ""),
            "Fall 2027",
        )
        self.assertEqual(
            Command._extract_required_subject('Required subject format: "CAE PhD Application – Your Name"', ""),
            "CAE PhD Application – Forhad Uddin Ahmed",
        )
        self.assertEqual(
            Command._extract_required_subject("", 'Email with the subject line "Fall 2027 PhD Application – [Your Name]"'),
            "Fall 2027 PhD Application – Forhad Uddin Ahmed",
        )
        self.assertEqual(
            Command._format_salutation("Asst. Prof. Omar AL-Buraiki"),
            "Dear Assistant Professor Omar AL-Buraiki,",
        )
        self.assertEqual(
            Command._format_salutation("Prof. Dr. Jan Jürjens"),
            "Dear Prof. Dr. Jan Jürjens,",
        )
        papers = Command._extract_papers_from_notes(
            "Funding: Full | Verified recent papers: 2026: Agentic AI; 2025: Robust ML | Source: url"
        )
        self.assertIn('Title: "Agentic AI" | Year: 2026', papers)
        stripped = Command._strip_speculative_opening_question(
            "Dear Dr. X,\n\nI read your post. Do you expect to have funded PhD opportunities for Fall 2027? I have attached my resume.",
            "Fall 2027",
        )
        self.assertNotIn("Do you expect to have", stripped)
        self.assertIn("discuss my fit for this Fall 2027 opening", stripped)


class GmailDraftIntegrationTests(TestCase):
    def test_build_outreach_email_includes_html_signature_and_attachment(self):
        import tempfile
        from pathlib import Path
        from core.email_utils import build_outreach_email, extract_subject_and_body

        subject, body = extract_subject_and_body(
            "Subject: Exploring PhD Research – Test\n\nDear Dr. Smith,\n\nI would love to join your lab.\n\nSincerely,\nForhad Uddin Ahmed",
            "",
            "USA",
        )
        self.assertEqual(subject, "Exploring PhD Research – Test")
        self.assertTrue(body.startswith("Dear Dr. Smith,"))

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "Resume.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")

            msg = build_outreach_email(
                subject=subject,
                draft=body,
                to_email="smith@stanford.edu",
                from_email="Forhad <forhad.uddin892@gmail.com>",
                signature_text="Sincerely,\nForhad Uddin Ahmed\nAI Researcher",
                signature_html="<div class='gmail_signature'>Sincerely,<br/><b>Forhad Uddin Ahmed</b></div>",
                attachments=[pdf_path],
            )
            self.assertEqual(msg.to, ["smith@stanford.edu"])
            self.assertEqual(msg.subject, "Exploring PhD Research – Test")
            self.assertIn("AI Researcher", msg.body)
            self.assertEqual(len(msg.alternatives), 1)
            html_content, mime_type = msg.alternatives[0]
            self.assertEqual(mime_type, "text/html")
            self.assertIn("gmail_signature", html_content)
            self.assertEqual(len(msg.attachments), 1)

    def test_validate_oauth_client_file_rejects_service_account_and_accepts_installed(self):
        import json
        import tempfile
        from pathlib import Path
        from core.gmail_service import GmailAuthError, validate_oauth_client_file

        with tempfile.TemporaryDirectory() as tmpdir:
            sa_file = Path(tmpdir) / "credentials.json"
            sa_file.write_text(json.dumps({"type": "service_account", "client_email": "x@y.iam.gserviceaccount.com"}))
            with self.assertRaises(GmailAuthError) as ctx:
                validate_oauth_client_file(sa_file)
            self.assertIn("Service Account", str(ctx.exception))

            oauth_file = Path(tmpdir) / "gmail_credentials.json"
            oauth_file.write_text(json.dumps({"installed": {"client_id": "123", "client_secret": "sec"}}))
            validate_oauth_client_file(oauth_file)

    def test_create_gmail_draft_encodes_raw_and_dedupes(self):
        import base64
        from email import message_from_bytes
        from email.header import decode_header, make_header
        from core.email_utils import build_outreach_email
        from core.gmail_service import create_gmail_draft, list_existing_draft_keys

        msg = build_outreach_email(
            subject="Exploring PhD Research – Forhad",
            draft="Dear Prof. Lee,\n\nTesting Gmail draft encoding.",
            to_email="lee@mit.edu",
            from_email="forhad.uddin892@gmail.com",
        )

        mock_service = MagicMock()
        mock_service.users.return_value.drafts.return_value.create.return_value.execute.return_value = {"id": "draft_123"}
        resp = create_gmail_draft(mock_service, msg)
        self.assertEqual(resp["id"], "draft_123")

        call_kwargs = mock_service.users.return_value.drafts.return_value.create.call_args.kwargs
        raw_b64 = call_kwargs["body"]["message"]["raw"]
        decoded = message_from_bytes(base64.urlsafe_b64decode(raw_b64.encode("ascii")))
        self.assertEqual(decoded["To"], "lee@mit.edu")
        self.assertEqual(str(make_header(decode_header(decoded["Subject"]))), "Exploring PhD Research – Forhad")

        mock_service.users.return_value.drafts.return_value.list.return_value.execute.return_value = {
            "drafts": [{"id": "d1"}]
        }
        mock_service.users.return_value.drafts.return_value.get.return_value.execute.return_value = {
            "message": {
                "payload": {
                    "headers": [
                        {"name": "To", "value": "Prof. Lee <lee@mit.edu>"},
                        {"name": "Subject", "value": "Exploring PhD Research – Forhad"},
                    ]
                }
            }
        }
        keys = list_existing_draft_keys(mock_service)
        self.assertIn(("lee@mit.edu", "exploring phd research – forhad"), keys)

    def test_create_gmail_drafts_command_creates_and_skips_duplicates(self):
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command

        mock_ws = MagicMock()
        mock_ws.row_values.return_value = [
            "Professor Name",
            "University",
            "Country",
            "Professor Email",
            "Pipeline Status",
            "Email Subject",
            "Email Draft",
        ]
        mock_ws.get_all_values.return_value = [
            mock_ws.row_values.return_value,
            [
                "Dr. Alice Smith",
                "Stanford",
                "USA",
                "alice@stanford.edu",
                "Needs Review",
                "Exploring PhD Research – Forhad",
                "Dear Dr. Alice Smith,\n\nI am excited about your work.",
            ],
            [
                "Dr. Bob Jones",
                "MIT",
                "USA",
                "bob@mit.edu",
                "Needs Review",
                "Exploring PhD Research – Bob",
                "Dear Dr. Bob Jones,\n\nI am excited about your robotics work.",
            ],
        ]

        mock_service = MagicMock()
        out = StringIO()
        with (
            patch("os.path.exists", return_value=True),
            patch("core.management.commands.create_gmail_drafts.get_gmail_service", return_value=mock_service),
            patch("core.management.commands.create_gmail_drafts.get_authenticated_email", return_value="forhad.uddin892@gmail.com"),
            patch("core.management.commands.create_gmail_drafts.open_outreach_worksheet", return_value=mock_ws),
            patch(
                "core.management.commands.create_gmail_drafts.list_existing_draft_keys",
                return_value={("alice@stanford.edu", "exploring phd research – forhad")},
            ),
            patch("core.management.commands.create_gmail_drafts.create_gmail_draft", return_value={"id": "r_bob"}) as mock_create,
        ):
            call_command(
                "create_gmail_drafts",
                sheet="https://docs.google.com/spreadsheets/d/dummy/edit",
                status="Needs Review",
                delay=0,
                stdout=out,
            )

        output = out.getvalue()
        self.assertEqual(mock_create.call_count, 1)
        self.assertIn("Draft already exists in Gmail for alice@stanford.edu", output)
        self.assertIn("Saved Gmail draft (id=r_bob) for bob@mit.edu", output)
        self.assertIn("Created 1 draft(s), skipped 1", output)


class DiscoverProfsExpansionTests(TestCase):
    def test_keyword_resolution_and_matching(self):
        from core.management.commands.discover_profs import Command, text_matches_keywords

        search_kws, rel_kws = Command._resolve_keywords(None, "graph neural networks, agentic ai")
        self.assertIn("graph neural networks", search_kws)
        self.assertIn("agentic ai", rel_kws)
        self.assertIn("explainable ai", rel_kws)

        hits = text_matches_keywords("Research on Graph Neural Networks and XAI for EHR forecasting.", rel_kws)
        self.assertIn("xai", hits)
        self.assertIn("ehr", hits)
        self.assertIn("forecasting", hits)
        self.assertEqual(text_matches_keywords("Studies on ancient ceramic vessels.", rel_kws), [])

    def test_prioritize_emails_and_infer_name_from_email(self):
        from core.management.commands.discover_profs import infer_name_from_email, prioritize_emails

        ordered = prioritize_emails(["hr@uni.edu", "mohamed.soliman@uni-paderborn.de", "recruitment@uni.edu"])
        self.assertEqual(ordered[0], "mohamed.soliman@uni-paderborn.de")
        self.assertEqual(infer_name_from_email("mohamed.soliman@uni-paderborn.de"), "Prof. Mohamed Soliman")
        self.assertEqual(infer_name_from_email("recruitment@uni.edu"), "")

    def test_extract_euraxess_key_facts(self):
        from core.management.commands.discover_profs import extract_euraxess_key_facts

        html = """
        <html><body><main>
        <h1>Funded Master Research Assistant in Machine Learning</h1>
        <p>Posted on: 24 November 2026</p>
        <div>Organisation/Company TU Wien Department Institute of Logic and Computation
        Research Field Computer science Positions Master Positions
        Application Deadline 15 Dec 2026 Country Austria
        Offer Starting Date 1 Mar 2027
        Offer Description We seek an MSc student working on Explainable AI and LLMs.
        Contact Prof. Jane Doe (jane.doe@tuwien.ac.at) or hr@tuwien.ac.at.
        Work Location Vienna</div>
        </main></body></html>
        """
        parsed = extract_euraxess_key_facts(html, "https://euraxess.ec.europa.eu/jobs/999", today=date(2026, 11, 24))
        self.assertEqual(parsed["post_age_days"], 0)
        self.assertEqual(parsed["university"], "TU Wien")
        self.assertEqual(parsed["country"], "Austria")
        self.assertEqual(parsed["emails"][0], "jane.doe@tuwien.ac.at")
        self.assertIn("Jane Doe", parsed["supervisor"])


class SheetStatusTests(TestCase):
    def test_summarize_worksheet_respects_locks_and_cooldown(self):
        from core.management.commands.sheet_status import summarize_worksheet

        rows = [
            [
                "Professor Name",
                "University",
                "Country",
                "Contact Group (Lock)",
                "Pipeline Status",
                "First Contact Date",
            ],
            ["Prof. A", "CMU", "USA", "CMU-CS", "Applied", "2026-11-24"],
            ["Prof. B", "CMU", "USA", "CMU-CS", "Pending", ""],
            ["Prof. C", "MIT", "USA", "MIT-EECS", "Applied", "2026-11-10"],
            ["Prof. D", "MIT", "USA", "MIT-EECS", "Pending", ""],
            ["Prof. E", "MIT", "USA", "MIT-EECS", "Pending", ""],
            ["Prof. F", "TUM", "Germany", "TUM-CS", "Needs Review", ""],
            ["Prof. G", "TUM", "Germany", "TUM-CS", "Pending", ""],
        ]

        summary_9d = summarize_worksheet(rows, cooldown_days=9, today=date(2026, 11, 28))
        self.assertEqual(summary_9d["total_rows"], 7)
        self.assertEqual(summary_9d["locked_groups"], {"CMU-CS", "TUM-CS"})
        self.assertEqual(summary_9d["total_ready_groups"], 1)
        self.assertEqual(summary_9d["total_ready_rows"], 2)
        self.assertEqual(summary_9d["ready_groups_by_country"], {"USA": 1})

        summary_4d = summarize_worksheet(rows, cooldown_days=4, today=date(2026, 11, 28))
        self.assertEqual(summary_4d["locked_groups"], {"TUM-CS"})
        self.assertEqual(summary_4d["total_ready_groups"], 2)
        self.assertEqual(summary_4d["total_ready_rows"], 3)

    def test_sheet_status_command_outputs_report_and_json(self):
        import json
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command

        mock_ws_main = MagicMock()
        mock_ws_main.title = "Professors List"
        mock_ws_main.get_all_values.return_value = [
            ["Professor Name", "Country", "Contact Group (Lock)", "Pipeline Status", "First Contact Date"],
            ["Prof. A", "USA", "MIT-EECS", "Pending", ""],
            ["Prof. B", "Germany", "TUM-CS", "Applied", "2026-10-01"],
            ["Prof. C", "Germany", "TUM-CS", "Pending", ""],
        ]

        mock_ws_search = MagicMock()
        mock_ws_search.title = "SearchProf"
        mock_ws_search.get_all_values.return_value = [
            ["Professor Name", "Country", "Contact Group (Lock)", "Status"],
            ["Prof. D", "Sweden", "KTH-CS", "Needs Review"],
        ]

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheets.return_value = [mock_ws_main, mock_ws_search]

        out = StringIO()
        with (
            patch("os.path.exists", return_value=True),
            patch("core.management.commands.sheet_status._open_spreadsheet", return_value=mock_spreadsheet),
        ):
            call_command(
                "sheet_status",
                sheet="https://docs.google.com/spreadsheets/d/dummy/edit",
                stdout=out,
            )

        text = out.getvalue()
        self.assertIn("[Professors List] Total rows: 3", text)
        self.assertIn("Ready to draft: 2 (2 unlocked Pending)", text)
        self.assertIn("[SearchProf] Total rows: 1", text)
        self.assertIn("Total unique locked Contact Groups across sheets: 1", text)

        out_json = StringIO()
        with (
            patch("os.path.exists", return_value=True),
            patch("core.management.commands.sheet_status._open_spreadsheet", return_value=mock_spreadsheet),
        ):
            call_command(
                "sheet_status",
                sheet="https://docs.google.com/spreadsheets/d/dummy/edit",
                json=True,
                stdout=out_json,
            )
        parsed = json.loads(out_json.getvalue())
        self.assertEqual(parsed["total_unique_locked_groups"], 1)
        self.assertEqual(parsed["worksheets"]["Professors List"]["total_ready_groups"], 2)







