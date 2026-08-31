from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Professor
from .locking import ContactGroupLockManager


@admin.register(Professor)
class ProfessorAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "university",
        "contact_group",
        "group_lock_status",
        "pipeline_status",
        "priority",
        "fit_score",
        "email",
        "funding_status",
        "last_contact_date",
        "deadline",
    )
    list_filter = (
        "pipeline_status",
        "contact_group",
        "priority",
        "funding_status",
        "country",
    )
    search_fields = (
        "name",
        "university",
        "department",
        "email",
        "research_area",
        "contact_group",
    )
    list_editable = (
        "pipeline_status",
        "priority",
    )
    readonly_fields = ("created_at", "updated_at", "last_synced_at")

    @admin.display(description="Group Lock")
    def group_lock_status(self, obj):
        if not obj.contact_group:
            return "-"
        is_locked = ContactGroupLockManager.is_group_locked(obj.contact_group)
        if is_locked:
            active_prof = ContactGroupLockManager.get_active_professor_in_group(obj.contact_group)
            if active_prof and active_prof.id == obj.id:
                return mark_safe('<span style="color: #b78103; font-weight: bold;">🔒 Active (This)</span>')
            return mark_safe('<span style="color: #d9534f; font-weight: bold;">🔒 Locked</span>')
        return mark_safe('<span style="color: #5cb85c; font-weight: bold;">🔓 Available</span>')


    fieldsets = (
        (
            "Contact Identification",
            {
                "fields": (
                    "name",
                    "university",
                    "country",
                    "department",
                    "contact_group",
                    "email",
                )
            },
        ),
        (
            "Web Presence & URLs",
            {
                "classes": ("collapse",),
                "fields": (
                    "profile_url",
                    "lab_website_url",
                ),
            },
        ),
        (
            "Research & Academic Profile",
            {
                "fields": (
                    "research_area",
                    "recent_publications",
                    ("h_index", "citations"),
                    "funding_status",
                )
            },
        ),
        (
            "Pipeline & Outreach Tracking",
            {
                "fields": (
                    ("pipeline_status", "priority"),
                    "email_subject",
                    ("first_contact_date", "last_contact_date"),
                    ("follow_up_1_date", "follow_up_2_date"),
                    ("response_date", "meeting_scheduled"),
                    ("application_submitted", "deadline"),
                )
            },
        ),
        (
            "LLM Generated Insights & Outreach",
            {
                "classes": ("collapse",),
                "fields": (
                    "fit_score",
                    "llm_research_summary",
                    "llm_alignment_hook",
                    "llm_draft_email",
                ),
            },
        ),
        (
            "Notes & Metadata",
            {
                "fields": (
                    "notes",
                    ("created_at", "updated_at"),
                )
            },
        ),
    )

