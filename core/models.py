from django.db import models


class Professor(models.Model):
    """
    Professor model mirroring the 28 columns of the Outreach / Application Google Sheet.
    Includes URLs and LLM summaries stored as TextFields.
    """

    # --- 1. Basic & Institutional Info ---
    # Col 1: Name
    name = models.CharField(
        max_length=255,
        verbose_name="Professor Name",
        help_text="Full name of the professor",
    )
    # Col 2: University
    university = models.CharField(
        max_length=255,
        verbose_name="University",
        help_text="Institution or university name",
    )
    # Col 3: Country
    country = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Country",
    )
    # Col 4: Department / Lab
    department = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Department / Lab",
    )
    # Col 5: Contact Group
    contact_group = models.CharField(
        max_length=150,
        blank=True,
        db_index=True,
        verbose_name="Contact Group",
        help_text="Categorization tag (e.g., AI/ML Group, Systems, Fall 2026 Batch)",
    )

    # --- 2. Contact Details & Web Presence (URLs as TextFields) ---
    # Col 6: Professor Email
    email = models.EmailField(
        blank=True,
        verbose_name="Professor Email",
    )
    # Col 7: Email Subject
    email_subject = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Email Subject",
        help_text="Customized email subject line for outreach",
    )
    # Col 8: Professor Profile URL (TextField)
    profile_url = models.TextField(
        blank=True,
        verbose_name="Professor Profile URL",
        help_text="Faculty page or personal homepage URL",
    )
    # Col 9: Lab / Website URL (TextField)
    lab_website_url = models.TextField(
        blank=True,
        verbose_name="Lab / University Website URL",
        help_text="Research laboratory or department portal URL",
    )

    # --- 3. Academic & Research Profile ---
    # Col 10: Research Area
    research_area = models.TextField(
        blank=True,
        verbose_name="Research Area",
        help_text="Core research fields, topics, and keywords",
    )
    # Col 11: Recent Publications
    recent_publications = models.TextField(
        blank=True,
        verbose_name="Recent Publications",
        help_text="Selected recent papers or conference proceedings",
    )
    # Col 12: h-index
    h_index = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="h-index",
    )
    # Col 13: Citations
    citations = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Citations",
    )
    # Col 14: Funding Status
    funding_status = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Funding Status",
        help_text="e.g. Fully Funded, RA/TA Available, Self-funded",
    )

    # --- 4. Pipeline & Outreach Status ---
    PIPELINE_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("researching", "Researching"),
        ("needs_review", "Needs Review"),
        ("approved", "Approved"),
        ("applied", "Applied"),
        ("identified", "Identified / Backlog"),
        ("researched", "Researched / Qualified"),
        ("email_drafted", "Email Drafted"),
        ("contacted", "First Contact Sent"),
        ("follow_up_1", "Follow-up #1 Sent"),
        ("follow_up_2", "Follow-up #2 Sent"),
        ("discussion", "In Discussion / Replied"),
        ("meeting_scheduled", "Meeting Scheduled"),
        ("interviewed", "Interviewed"),
        ("accepted", "Accepted / Offer"),
        ("declined", "Declined / Closed"),
        ("no_response", "No Response / Expired"),
    ]
    # Col 15: Pipeline Status
    pipeline_status = models.CharField(
        max_length=50,
        choices=PIPELINE_STATUS_CHOICES,
        default="pending",
        db_index=True,
        verbose_name="Pipeline Status",
    )

    PRIORITY_CHOICES = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]
    # Col 16: Priority
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default="medium",
        db_index=True,
        verbose_name="Priority",
    )

    # Col 17: First Contact Date
    first_contact_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="First Contact Date",
    )
    # Col 18: Last Contact Date
    last_contact_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Last Contact Date",
    )
    # Col 19: Follow-up #1 Date
    follow_up_1_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Follow-up #1 Date",
    )
    # Col 20: Follow-up #2 Date
    follow_up_2_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Follow-up #2 Date",
    )
    # Col 21: Response Date
    response_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Response Date",
    )
    # Col 22: Meeting Scheduled
    meeting_scheduled = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Meeting Scheduled",
        help_text="Status or date/time of scheduled meeting",
    )
    # Col 23: Application Submitted
    application_submitted = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Application Submitted",
        help_text="e.g. Yes / No / In Progress",
    )
    # Col 24: Application Deadline
    deadline = models.DateField(
        null=True,
        blank=True,
        verbose_name="Deadline",
    )

    # --- 5. LLM Summaries & Content Generation (TextFields) ---
    # Col 25: LLM Research Summary (TextField)
    llm_research_summary = models.TextField(
        blank=True,
        verbose_name="LLM Research Summary",
        help_text="AI-generated summary of professor's work, methodology, and key focus areas",
    )
    # Col 26: LLM Alignment Hook (TextField)
    llm_alignment_hook = models.TextField(
        blank=True,
        verbose_name="LLM Alignment Hook",
        help_text="AI-synthesized explanation of alignment between candidate background and lab work",
    )
    # Col 27: LLM Draft Email (TextField)
    llm_draft_email = models.TextField(
        blank=True,
        verbose_name="LLM Draft Email",
        help_text="AI-generated personalized outreach email draft",
    )
    # Fit Score (1-10)
    fit_score = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Fit Score (1-10)",
        help_text="AI-calculated alignment score between 1 and 10",
    )

    # --- 6. Notes & Actions ---
    # Col 28: Notes & Next Action
    notes = models.TextField(
        blank=True,
        verbose_name="Notes & Next Action",
        help_text="Action items, reminders, interview notes, or general context",
    )

    # Timestamps & Sync Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Last Synced to Sheet At",
        help_text="Timestamp when changes were last pushed to Google Sheet",
    )
    sheet_row_index = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Sheet Row Index",
        help_text="1-based row number in Google Sheet for direct updates",
    )

    def clean(self):
        super().clean()
        from core.locking import ContactGroupLockManager
        ContactGroupLockManager.validate_professor_transition(
            self, self.pipeline_status, self.contact_group
        )

    class Meta:
        verbose_name = "Professor"
        verbose_name_plural = "Professors"
        ordering = ["priority", "name"]

    def __str__(self):
        return f"{self.name} - {self.university} ({self.get_pipeline_status_display()})"

