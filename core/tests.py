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


